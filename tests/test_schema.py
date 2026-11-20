from pathlib import Path

from asac.schema import export


def test_committed_schema_is_up_to_date(tmp_path: Path) -> None:
    fresh = export(tmp_path).read_text()
    committed = (
        Path(__file__).resolve().parent.parent / "schemas" / "asac-manifest-0.4.schema.json"
    ).read_text()
    assert fresh == committed, "run: uv run python -m asac.schema"
