from pathlib import Path

import pytest

from asac.hooks import HookError, run_hook, run_hooks
from asac.loader.load import load_manifest
from asac.model import Manifest


def manifest_with(project: Path, run: str, on_fail: str = "block") -> Manifest:
    m = load_manifest(project / "asac.yaml")
    assert m.hooks is not None
    m.hooks.definitions["x"].run = run
    m.hooks.definitions["x"].on_fail = on_fail  # type: ignore[assignment]
    return m


def add_hook(project: Path) -> Manifest:
    m = load_manifest(project / "asac.yaml")
    assert m.hooks is not None
    from asac.model.manifest import HookDefinition

    m.hooks.definitions["x"] = HookDefinition(run=".asac/hooks/secret-scan.sh")
    return m


def test_secret_scan_passes_clean_diff_and_fails_secret(sandbox_project: Path) -> None:
    m = load_manifest(sandbox_project / "asac.yaml")
    assert run_hook(m, sandbox_project, "secret-scan", "+print('hi')\n").passed
    bad = run_hook(m, sandbox_project, "secret-scan", '+password = "hunter2"\n')
    assert not bad.passed and "secret" in bad.output


def test_deps_verify_uses_allowlist(sandbox_project: Path) -> None:
    m = load_manifest(sandbox_project / "asac.yaml")
    allowed = (sandbox_project / ".asac/hooks/allowed-deps.txt").read_text().split()[0]
    assert run_hook(m, sandbox_project, "deps-verify", allowed + "\n").passed
    assert not run_hook(m, sandbox_project, "deps-verify", "evil:lib:1.0\n").passed


def test_hook_outside_repo_is_refused(sandbox_project: Path) -> None:
    m = add_hook(sandbox_project)
    m.hooks.definitions["x"].run = "../outside.sh"  # type: ignore[union-attr]
    (sandbox_project.parent / "outside.sh").write_text("exit 0\n")
    with pytest.raises(HookError, match="outside"):
        run_hook(m, sandbox_project, "x")


def test_undeclared_hook_is_never_discovered(sandbox_project: Path) -> None:
    m = load_manifest(sandbox_project / "asac.yaml")
    (sandbox_project / ".asac/hooks/sneaky.sh").write_text("exit 0\n")
    with pytest.raises(HookError, match="not declared"):
        run_hook(m, sandbox_project, "sneaky")


def test_ref_hook_needs_registry(sandbox_project: Path) -> None:
    from asac.model.manifest import HookDefinition

    m = load_manifest(sandbox_project / "asac.yaml")
    m.hooks.definitions["r"] = HookDefinition(ref="registry.example/h@1.0.0")  # type: ignore[union-attr]
    with pytest.raises(HookError, match="registry"):
        run_hook(m, sandbox_project, "r")


def test_environment_is_not_leaked(sandbox_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPER_SECRET_TOKEN", "abc123")
    script = sandbox_project / ".asac/hooks/env.sh"
    script.write_text('echo "token=${SUPER_SECRET_TOKEN:-unset}"; exit 1\n')
    m = add_hook(sandbox_project)
    m.hooks.definitions["x"].run = ".asac/hooks/env.sh"  # type: ignore[union-attr]
    r = run_hook(m, sandbox_project, "x")
    assert "token=unset" in r.output and "abc123" not in r.output


def test_run_hooks_attach_points(sandbox_project: Path) -> None:
    m = load_manifest(sandbox_project / "asac.yaml")
    names = [r.name for r in run_hooks(m, sandbox_project, "post_step", stdin="")]
    assert names == ["deps-verify"]
