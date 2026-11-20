from __future__ import annotations

import subprocess
from typing import Any

import pytest

from asac.adapters.runner_k8s import KubernetesRunner
from asac.adapters.runner_local import runner_from_vars


def test_pod_is_locked_down_and_secrets_are_references() -> None:
    r = KubernetesRunner("img:1", secret="llm", env={"API_KEY": "sk-secret-123"}, pvc="code")
    spec = r.manifest("run 1", "dev")
    text = str(spec)
    assert "sk-secret-123" not in text
    pod = spec["spec"]
    assert pod["automountServiceAccountToken"] is False  # type: ignore[index]
    sc = pod["containers"][0]["securityContext"]  # type: ignore[index]
    assert (
        sc["readOnlyRootFilesystem"]
        and sc["runAsNonRoot"]
        and sc["capabilities"]["drop"] == ["ALL"]
    )
    assert {
        "name": "API_KEY",
        "valueFrom": {"secretKeyRef": {"name": "llm", "key": "API_KEY"}},
    } in pod["containers"][0]["env"]  # type: ignore[index]
    assert pod["volumes"][1]["persistentVolumeClaim"]["readOnly"] is True  # type: ignore[index]


def test_kubectl_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "out sk-secret-123", "")

    monkeypatch.setattr(subprocess, "run", fake)
    r = KubernetesRunner(
        "img", namespace="ns", kubectl="kubectl", context="c", env={"K": "sk-secret-123"}
    )
    name = r.start("r1", "dev")
    res = r.exec(name, ["echo", "hi"], 5)
    r.stop(name)
    assert res.stdout == "out [redacted]"
    assert calls[0][:5] == ["kubectl", "--namespace", "ns", "--context", "c"]
    assert calls[0][-2:] == ["-f", "-"]
    assert calls[2][-4:] == ["--", "echo", "hi"][-4:] or "--" in calls[2]
    assert calls[3][5] == "delete" and "--wait=false" in calls[3]
    assert r.available() is True


def test_unavailable_without_kubectl() -> None:
    assert KubernetesRunner("img", kubectl="").available() is False


def test_from_vars_builds_kubernetes_runner(tmp_path: Any) -> None:
    r = runner_from_vars(
        tmp_path, {"runner_kind": "kubernetes", "runner_image": "i", "runner_k8s_namespace": "x"}
    )
    assert isinstance(r, KubernetesRunner) and r.namespace == "x"
    with pytest.raises(RuntimeError, match="kubernetes"):
        runner_from_vars(tmp_path, {"runner_kind": "nope"})


def test_scratch_volume_is_writable_by_the_step_user() -> None:
    pod = KubernetesRunner("img:1").manifest("r", "s")["spec"]
    user = pod["containers"][0]["securityContext"]["runAsUser"]  # type: ignore[index]
    assert pod["securityContext"]["fsGroup"] == user  # type: ignore[index]
