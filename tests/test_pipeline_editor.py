"""Pipeline editor API: drafts, validation, propose through the forge, conflicts, roles."""

import shutil
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from asac.adapters.forge_http import GitHubForge
from asac.portal.app import PortalSettings, create_app
from tests.conformance.fake_forges import Repo, github
from tests.seed import seed_portal
from tests.test_api import FILE, PERSONAS, csrf

BASE = "/api/v1/projects/payments/pipeline"


class World:
    def __init__(self, org: Path) -> None:
        self.manifest = (org.parent / "payments/asac.yaml").read_text()
        self.repo = Repo()
        self.repo.commit("main", {"asac.yaml": self.manifest})
        self.org = org

    def client(self, persona: str | None = None, forge: bool = True) -> TestClient:
        f = GitHubForge("o/r", "tok", "https://api.test", httpx.Client(transport=github(self.repo)))
        settings = PortalSettings(
            data_dir=seed_portal(self.org),
            dev_personas=PERSONAS,
            harness="fake",
            secure_cookie=False,
            forge_factory=(lambda _p: f) if forge else (lambda _p: None),
        )
        c = TestClient(create_app(settings), follow_redirects=False)
        if persona:
            assert c.get(f"/login?persona={persona}").status_code == 303
        return c


@pytest.fixture(autouse=True)
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ASAC_ENV", "dev")
    monkeypatch.setenv("ASAC_FIXED_TIME", "2026-01-01T00:00:00Z")
    monkeypatch.setenv("ASAC_STATE_DIR", str(tmp_path / "state"))


@pytest.fixture
def world(sandbox_project: Path, tmp_path: Path) -> World:
    root = tmp_path / "org"
    for name in ("payments", "billing"):
        shutil.copytree(sandbox_project, root / name)
    (root / "portal-seed.yaml").write_text(FILE)
    return World(root / "portal-seed.yaml")


def hdr(c: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": csrf(c)}


def test_source_is_read_from_the_forge(world: World) -> None:
    body = world.client("alice").get(f"{BASE}/source").json()
    assert body["content"] == world.manifest and body["branch"] == "main"
    assert len(body["commit"]) == 40


def test_no_forge_configured_is_a_clear_409(world: World) -> None:
    r = world.client("alice", forge=False).get(f"{BASE}/source")
    assert r.status_code == 409 and "forge" in r.json()["detail"]


def test_validate_reports_errors_without_saving(world: World) -> None:
    c = world.client("alice")
    bad = c.post(f"{BASE}/validate", json={"content": "a: [unclosed"}).json()
    assert bad["ok"] is False and bad["findings"][0]["severity"] == "error"
    good = c.post(f"{BASE}/validate", json={"content": world.manifest}).json()
    assert good["ok"] is True
    assert c.get(f"{BASE}/drafts").json() == []


def test_draft_then_propose_opens_a_change_request(world: World) -> None:
    c = world.client("alice")
    new = world.manifest + "# edited in the portal\n"
    d = c.post(f"{BASE}/drafts", json={"content": new}, headers=hdr(c))
    assert d.status_code == 201 and "+# edited in the portal" in d.json()["diff"]
    assert list(world.repo.branches) == ["main"]  # nothing written to git yet
    did = d.json()["id"]
    done = c.post(f"{BASE}/drafts/{did}/propose", headers=hdr(c))
    assert done.status_code == 200, done.text
    out = done.json()
    assert out["status"] == "proposed" and out["branch"] == f"asac/pipeline-{did}"
    assert out["change_request_url"].startswith("https://")
    assert world.repo.branches["main"] != world.repo.branches[out["branch"]]  # main untouched
    assert world.repo.prs == [{"head": out["branch"], "base": "main"}]
    assert any(
        e["action"] == "pipeline.proposed"
        for e in world.client("erin").get("/api/v1/admin/events").json()
    )


def test_invalid_draft_cannot_be_proposed(world: World) -> None:
    c = world.client("alice")
    d = c.post(f"{BASE}/drafts", json={"content": "oops: ["}, headers=hdr(c)).json()
    r = c.post(f"{BASE}/drafts/{d['id']}/propose", headers=hdr(c))
    assert r.status_code == 409 and "validation" in r.json()["detail"]


def test_conflict_when_default_branch_changed_the_file(world: World) -> None:
    c = world.client("alice")
    d = c.post(f"{BASE}/drafts", json={"content": world.manifest + "# mine\n"}, headers=hdr(c))
    world.repo.commit("main", {"asac.yaml": world.manifest + "# theirs\n"})
    r = c.post(f"{BASE}/drafts/{d.json()['id']}/propose", headers=hdr(c))
    assert r.status_code == 409 and "+# theirs" in r.json()["diff"] and r.json()["current_sha"]
    assert world.repo.prs == []


def test_unrelated_upstream_commit_does_not_conflict(world: World) -> None:
    c = world.client("alice")
    d = c.post(f"{BASE}/drafts", json={"content": world.manifest + "# mine\n"}, headers=hdr(c))
    world.repo.commit("main", {"README.md": "hello"})
    r = c.post(f"{BASE}/drafts/{d.json()['id']}/propose", headers=hdr(c))
    assert r.status_code == 200, r.text


def test_roles_csrf_and_authorship(world: World) -> None:
    body = {"content": world.manifest + "# x\n"}
    bob = world.client("bob")  # project member without an editing role
    assert bob.post(f"{BASE}/drafts", json=body, headers=hdr(bob)).status_code == 403
    assert world.client("dave").get(f"{BASE}/drafts").status_code == 404
    alice = world.client("alice")
    assert alice.post(f"{BASE}/drafts", json=body).status_code == 403  # no CSRF
    did = alice.post(f"{BASE}/drafts", json=body, headers=hdr(alice)).json()["id"]
    erin = world.client("erin")  # admin may edit, but not take over alice's draft
    assert erin.put(f"{BASE}/drafts/{did}", json=body, headers=hdr(erin)).status_code == 403
    assert erin.post(f"{BASE}/drafts/{did}/propose", headers=hdr(erin)).status_code == 403
    assert world.client("bob").get(f"{BASE}/drafts/{did}").status_code == 200  # members can read


def test_merged_change_request_marks_draft_applied(world: World) -> None:
    c = world.client("alice")
    did = c.post(f"{BASE}/drafts", json={"content": world.manifest + "# y\n"}, headers=hdr(c))
    did = did.json()["id"]
    c.post(f"{BASE}/drafts/{did}/propose", headers=hdr(c))
    assert c.get(f"{BASE}/drafts/{did}").json()["status"] == "proposed"
    # the fake forge reports every change request as open; flip it to merged through the pull
    from tests.conformance import fake_forges

    orig = fake_forges._pr
    fake_forges._pr = lambda n, pr: {**orig(n, pr), "merged_at": "2026-01-01T00:00:00Z"}
    try:
        assert c.get(f"{BASE}/drafts/{did}").json()["status"] == "applied"
    finally:
        fake_forges._pr = orig
    assert c.post(f"{BASE}/drafts/{did}/propose", headers=hdr(c)).status_code == 409


def test_validate_returns_the_graph_for_the_text(world: World) -> None:
    out = world.client("alice").post(f"{BASE}/validate", json={"content": world.manifest}).json()
    names = {p["name"] for p in out["pipelines"]}
    assert "feature" in names
    assert out["pipelines"][0]["steps"][0]["id"]
    assert (
        world.client("alice").post(f"{BASE}/validate", json={"content": "a: ["}).json()["pipelines"]
        == []
    )
