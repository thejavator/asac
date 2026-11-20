"""``ArtifactStore`` on the local filesystem: ``<state>/artifacts/<run>/<name>`` plus an index."""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from asac.ports.artifacts import Artifact, ArtifactError, ArtifactNotFound

MAX_BYTES = 10 * 1024 * 1024
_SAFE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _safe(value: str, what: str) -> str:
    if not _SAFE.match(value) or ".." in value:
        raise ArtifactError(f"unsafe {what} '{value}'")
    return value


class FsArtifactStore:
    def __init__(self, base: Path, max_bytes: int = MAX_BYTES) -> None:
        self.base, self.max_bytes = base, max_bytes

    def _dir(self, run_id: str) -> Path:
        return self.base / _safe(run_id, "run id")

    def put(self, run_id: str, step_id: str, name: str, data: bytes, at: str) -> Artifact:
        _safe(name, "artifact name")
        _safe(step_id, "step id")
        if len(data) > self.max_bytes:
            raise ArtifactError(f"artifact '{name}' is larger than {self.max_bytes} bytes")
        d = self._dir(run_id)
        d.mkdir(parents=True, exist_ok=True)
        target = d / name
        try:
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
        except FileExistsError:
            raise ArtifactError(f"artifact '{name}' already exists for run '{run_id}'") from None
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        art = Artifact(run_id, step_id, name, len(data), hashlib.sha256(data).hexdigest(), at)
        with (d / "index.jsonl").open("a", encoding="utf-8") as idx:
            idx.write(json.dumps(art.__dict__, sort_keys=True) + "\n")
        return art

    def list(self, run_id: str) -> list[Artifact]:
        index = self._dir(run_id) / "index.jsonl"
        if not index.is_file():
            return []
        return [Artifact(**json.loads(x)) for x in index.read_text("utf-8").splitlines() if x]

    def read(self, run_id: str, name: str) -> bytes:
        _safe(name, "artifact name")
        if name not in {a.name for a in self.list(run_id)}:
            raise ArtifactNotFound(name)
        return (self._dir(run_id) / name).read_bytes()
