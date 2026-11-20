"""Built-in catalogue: names the spec provides, resolved without files on disk."""

from __future__ import annotations

from asac.ports.harness import HarnessDescriptor

HARNESSES: dict[str, HarnessDescriptor] = {
    d.id: d
    for d in (
        HarnessDescriptor("claude-code", interactive=True, headless=True, mcp=True, streaming=True),
        HarnessDescriptor("copilot", interactive=True, headless=False, mcp=True, streaming=False),
        HarnessDescriptor("cursor", interactive=True, headless=True, mcp=True, streaming=False),
        HarnessDescriptor("codex", interactive=True, headless=True, mcp=True, streaming=True),
        HarnessDescriptor(
            "antigravity", interactive=True, headless=False, mcp=True, streaming=False
        ),
        HarnessDescriptor("bob", interactive=True, headless=True, mcp=True, streaming=False),
    )
}

# Policy names defined by the spec; they need no .rego file in the repository.
BUILTIN_POLICIES: frozenset[str] = frozenset({"no_regression"})
