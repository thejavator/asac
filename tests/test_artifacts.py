from pathlib import Path

import pytest

from asac.adapters.artifacts_fs import FsArtifactStore
from asac.ports.artifacts import ArtifactError, ArtifactNotFound

AT = "2026-01-01T00:00:00Z"


def test_put_list_read_and_digest(tmp_path: Path) -> None:
    s = FsArtifactStore(tmp_path)
    a = s.put("r1", "dev", "out.txt", b"hello", AT)
    assert a.size == 5 and len(a.sha256) == 64
    assert [x.name for x in s.list("r1")] == ["out.txt"] and s.read("r1", "out.txt") == b"hello"
    assert s.list("other") == []


def test_immutable_and_bounded(tmp_path: Path) -> None:
    s = FsArtifactStore(tmp_path, max_bytes=4)
    s.put("r1", "dev", "a", b"1234", AT)
    with pytest.raises(ArtifactError):
        s.put("r1", "dev", "a", b"x", AT)
    with pytest.raises(ArtifactError):
        s.put("r1", "dev", "b", b"12345", AT)


@pytest.mark.parametrize("name", ["../x", "a/b", ".hidden", "", "a b"])
def test_unsafe_names_refused(tmp_path: Path, name: str) -> None:
    s = FsArtifactStore(tmp_path)
    with pytest.raises(ArtifactError):
        s.put("r1", "dev", name, b"x", AT)
    with pytest.raises(ArtifactError):
        s.read("r1", name)


def test_unlisted_file_is_not_readable(tmp_path: Path) -> None:
    s = FsArtifactStore(tmp_path)
    s.put("r1", "dev", "a", b"x", AT)
    (tmp_path / "r1" / "stray").write_bytes(b"y")
    with pytest.raises(ArtifactNotFound):
        s.read("r1", "stray")
