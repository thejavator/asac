"""Kubernetes runner: one pod per delegate step, driven through ``kubectl``.

The pod has no service account token, a read-only root, a non-root user and no capabilities.
Unlike the Docker runner it cannot mount the local project: the image must carry the code,
or ``runner_k8s_pvc`` names a claim mounted read-only at /project. Command lines are built by
pure functions so they are tested without a cluster.
"""

from __future__ import annotations

import json
import shutil
import subprocess

from asac.adapters.runner_local import container_name
from asac.ports.runner import ExecResult


class KubernetesRunner:
    def __init__(
        self,
        image: str,
        namespace: str = "asac",
        kubectl: str | None = None,
        context: str | None = None,
        pvc: str | None = None,
        secret: str | None = None,
        env: dict[str, str] | None = None,
        cpus: str = "1",
        memory: str = "512Mi",
    ) -> None:
        self.image, self.namespace, self.pvc, self.secret = image, namespace, pvc, secret
        self.context, self.cpus, self.memory = context, cpus, memory
        self.env = dict(env or {})
        self.kubectl = kubectl or shutil.which("kubectl")

    def _base(self) -> list[str]:
        cmd = [self.kubectl or "kubectl", "--namespace", self.namespace]
        return [*cmd, "--context", self.context] if self.context else cmd

    def manifest(self, run_id: str, step_id: str) -> dict[str, object]:
        """The pod spec. Env values are never written here: only the names, read from a Secret."""
        name = container_name(run_id, step_id).lower().replace("_", "-").replace(".", "-")
        container: dict[str, object] = {
            "name": "step",
            "image": self.image,
            "command": ["sleep", "3600"],
            "workingDir": "/work",
            "resources": {
                "limits": {"cpu": self.cpus, "memory": self.memory},
                "requests": {"cpu": "100m", "memory": "128Mi"},
            },
            "securityContext": {
                "readOnlyRootFilesystem": True,
                "allowPrivilegeEscalation": False,
                "runAsNonRoot": True,
                "runAsUser": 65534,
                "capabilities": {"drop": ["ALL"]},
            },
            "env": [
                {"name": "ASAC_RUN_ID", "value": run_id},
                {"name": "ASAC_STEP", "value": step_id},
            ],
            "volumeMounts": [{"name": "work", "mountPath": "/work"}],
        }
        if self.secret:  # each listed name is read from the Secret; values never pass here
            container["env"] = [
                *container["env"],  # type: ignore[misc]
                *[
                    {
                        "name": n,
                        "valueFrom": {"secretKeyRef": {"name": self.secret, "key": n}},
                    }
                    for n in sorted(self.env)
                ],
            ]
        volumes: list[dict[str, object]] = [{"name": "work", "emptyDir": {"sizeLimit": "64Mi"}}]
        if self.pvc:
            volumes.append(
                {
                    "name": "project",
                    "persistentVolumeClaim": {"claimName": self.pvc, "readOnly": True},
                }
            )
            container["volumeMounts"] = [
                *container["volumeMounts"],  # type: ignore[misc]
                {"name": "project", "mountPath": "/project", "readOnly": True},
            ]
        return {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {"name": name, "labels": {"app": "asac-step", "asac-run": name[:50]}},
            "spec": {
                "restartPolicy": "Never",
                "automountServiceAccountToken": False,
                "securityContext": {"fsGroup": 65534},  # the scratch volume is writable by the user
                "containers": [container],
                "volumes": volumes,
            },
        }

    def available(self) -> bool:
        if not self.kubectl:
            return False
        try:
            proc = subprocess.run(
                [*self._base(), "auth", "can-i", "create", "pods"],
                capture_output=True, timeout=15, check=False,
            )  # fmt: skip
        except (OSError, subprocess.TimeoutExpired):
            return False
        return proc.returncode == 0

    def start(self, run_id: str, step_id: str) -> str:
        spec = self.manifest(run_id, step_id)
        name = str(spec["metadata"]["name"])  # type: ignore[index]
        made = subprocess.run(
            [*self._base(), "apply", "-f", "-"], input=json.dumps(spec), text=True,
            capture_output=True, timeout=60, check=False,
        )  # fmt: skip
        if made.returncode != 0:
            raise RuntimeError(f"kubectl apply failed: {made.stderr.strip()}")
        ready = subprocess.run(
            [*self._base(), "wait", "--for=condition=Ready", f"pod/{name}", "--timeout=120s"],
            capture_output=True, text=True, timeout=150, check=False,
        )  # fmt: skip
        if ready.returncode != 0:
            self.stop(name)
            raise RuntimeError(f"pod not ready: {ready.stderr.strip()}")
        return name

    def exec(self, handle: str, argv: list[str], timeout: int) -> ExecResult:
        cmd = [*self._base(), "exec", handle, "--", *argv]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout, check=False
            )  # fmt: skip
        except subprocess.TimeoutExpired:
            return ExecResult(124, "", f"timed out after {timeout}s")
        return ExecResult(proc.returncode, self._redact(proc.stdout), self._redact(proc.stderr))

    def _redact(self, text: str) -> str:
        for value in self.env.values():
            if len(value) >= 4:
                text = text.replace(value, "[redacted]")
        return text

    def stop(self, handle: str) -> None:
        subprocess.run(
            [*self._base(), "delete", f"pod/{handle}", "--wait=false", "--ignore-not-found"],
            capture_output=True, timeout=60, check=False,
        )  # fmt: skip
