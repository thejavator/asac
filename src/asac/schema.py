"""Export JSON Schema for the published spec (``schemas/``)."""

from __future__ import annotations

import json
from pathlib import Path

from asac.model import Manifest


def export(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "asac-manifest-0.4.schema.json"
    target.write_text(json.dumps(Manifest.model_json_schema(), indent=2) + "\n", encoding="utf-8")
    return target


if __name__ == "__main__":
    print(export(Path("schemas")))
