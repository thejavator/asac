"""A state store shared by worker threads: every call is serialised by one lock."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any, cast

from asac.ports.state import StateStore


class LockedStore:
    def __init__(self, inner: StateStore) -> None:
        self._inner = inner
        self._lock = threading.RLock()

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._inner, name)
        if not callable(attr):
            return attr
        fn = cast(Callable[..., Any], attr)

        def locked(*args: Any, **kwargs: Any) -> Any:
            with self._lock:
                return fn(*args, **kwargs)

        return locked
