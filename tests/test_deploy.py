"""The deployment files stay well formed, and the services expose a liveness probe."""

from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from asac.daemon.app import create_app as create_daemon
from asac.portal.app import PortalSettings, create_app
from asac.portal.oidc import Identity
from tests.seed import seed_single

ROOT = Path(__file__).resolve().parents[1]


def test_kubernetes_manifests_are_well_formed() -> None:
    docs = list(yaml.safe_load_all((ROOT / "deploy/kubernetes/asac.yaml").read_text()))
    kinds = [d["kind"] for d in docs]
    assert kinds.count("Deployment") == 2 and "Ingress" in kinds
    for d in docs:
        if d["kind"] != "Deployment":
            continue
        spec = d["spec"]["template"]["spec"]
        assert spec["securityContext"]["runAsNonRoot"] is True
        for c in spec["containers"]:
            assert c["securityContext"]["allowPrivilegeEscalation"] is False
            assert c["securityContext"]["capabilities"]["drop"] == ["ALL"]
            assert "runAsUser" not in c["securityContext"]  # OpenShift assigns the uid


def test_compose_file_has_the_three_services() -> None:
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text())
    assert set(compose["services"]) == {"postgres", "portal", "daemon"}
    for name in ("portal", "daemon"):
        assert compose["services"][name]["cap_drop"] == ["ALL"]


def test_healthz_on_portal_and_daemon(sandbox_project: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("ASAC_ENV", "dev")
    persona = {"po": Identity("s", "n", frozenset())}
    portal = create_app(
        PortalSettings(
            data_dir=seed_single(
                sandbox_project.parent / "portal-data", sandbox_project / "asac.yaml"
            ),
            dev_personas=persona,
        )
    )
    daemon = create_daemon(sandbox_project / "asac.yaml")
    for app in (portal, daemon):
        r = TestClient(app).get("/healthz")
        assert r.status_code == 200 and r.json() == {"status": "ok"}


def _portal_args(doc: dict) -> list[str]:  # type: ignore[type-arg]
    return list(doc["spec"]["template"]["spec"]["containers"][0]["args"])


def test_the_shipped_portal_writes_its_data_in_the_state_volume_not_in_the_project() -> None:
    """/project is mounted read-only: a portal that keeps its data there cannot start."""
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text())
    cmd = " ".join(compose["services"]["portal"]["command"])
    assert "--data=/state" in cmd
    docs = list(yaml.safe_load_all((ROOT / "deploy/kubernetes/asac.yaml").read_text()))
    portal = next(
        d for d in docs if d["kind"] == "Deployment" and "portal" in d["metadata"]["name"]
    )
    args = _portal_args(portal)
    assert "--data" in args and args[args.index("--data") + 1].startswith("/state")


def test_the_shipped_portal_registers_the_mounted_project_at_startup() -> None:
    """Without a registered project the portal opens empty, which is what a user reported."""
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text())
    assert "--project=" in " ".join(compose["services"]["portal"]["command"])
    docs = list(yaml.safe_load_all((ROOT / "deploy/kubernetes/asac.yaml").read_text()))
    portal = next(
        d for d in docs if d["kind"] == "Deployment" and "portal" in d["metadata"]["name"]
    )
    assert "--project" in _portal_args(portal)
