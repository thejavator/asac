"""Read layers 1 and 2 from disk. Secrets stay as ``${vault...}`` references."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from asac.model import Manifest, VarsFile


class DuplicateKey(ValueError):
    """The same key twice in one mapping: YAML would keep the last one and drop the first."""


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that refuses duplicated keys instead of silently keeping the last one."""


def _no_duplicates(loader: yaml.SafeLoader, node: yaml.MappingNode) -> dict[object, object]:
    seen: dict[object, int] = {}
    for key_node, _ in node.value:
        key = loader.construct_object(key_node)
        if key in seen:
            raise DuplicateKey(
                f"duplicate key '{key}' at line {key_node.start_mark.line + 1} "
                f"(first at line {seen[key]}): YAML would keep only the last one"
            )
        seen[key] = key_node.start_mark.line + 1
    return loader.construct_mapping(node)


_StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicates)


def _read_yaml(path: Path) -> dict[str, object]:
    data = yaml.load(path.read_text(encoding="utf-8"), Loader=_StrictLoader)  # noqa: S506 - safe
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a YAML mapping at the top level")
    return data


def load_manifest(path: Path) -> Manifest:
    return Manifest.model_validate(_read_yaml(path))


def load_vars(path: Path) -> VarsFile:
    return VarsFile.model_validate(_read_yaml(path))


# Features planned for v0.5 (docs/project/roadmap.md): rejected with a clear message.
V05_FEATURES: frozenset[str] = frozenset(
    {"routing", "critic", "monitor", "scope", "arch_conform", "golden_paths"}
)


def describe_validation_error(err: ValidationError) -> list[str]:
    """Human-readable lines; v0.5 keys are reported as 'not in spec v0.4'."""
    lines = []
    for d in err.errors():
        loc = ".".join(str(x) for x in d["loc"])
        last = str(d["loc"][-1]) if d["loc"] else ""
        if d["type"] == "extra_forbidden" and last in V05_FEATURES:
            msg = f"'{last}' is not in spec v0.4 (planned for v0.5)"
        elif d["loc"][-2:] == ("asac", "spec") or (len(d["loc"]) == 2 and last == "spec"):
            msg = f"unsupported spec version (this build supports 0.4): {d['msg']}"
        else:
            msg = d["msg"]
        lines.append(f"error ASAC000 {loc}: {msg}")
    return lines
