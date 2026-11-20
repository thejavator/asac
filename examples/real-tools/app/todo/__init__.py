"""Tiny task list: the code the AI tool is asked to extend."""


def add(tasks: list[str], title: str) -> list[str]:
    return [*tasks, title.strip()]


def done(tasks: list[str], title: str) -> list[str]:
    # TODO (use case "feature"): raise ValueError when the title is unknown.
    return [t for t in tasks if t != title]
