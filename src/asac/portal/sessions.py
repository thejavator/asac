"""Server-side sessions. The cookie holds only an opaque random id; data stays on the server."""

from __future__ import annotations

import json
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any


class SessionStore:
    def __init__(self, path: Path | str, ttl: int = 8 * 3600) -> None:
        self.ttl = ttl
        self._lock = threading.Lock()  # FastAPI runs sync handlers in a thread pool
        self._db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        with self._lock:
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, data TEXT, expires REAL)"
            )

    def create(self, data: dict[str, Any] | None = None) -> str:
        sid = secrets.token_urlsafe(32)
        self.save(sid, data or {})
        return sid

    def save(self, sid: str, data: dict[str, Any]) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO sessions VALUES (?, ?, ?)",
                (sid, json.dumps(data), time.time() + self.ttl),
            )

    def load(self, sid: str | None) -> dict[str, Any] | None:
        if not sid:
            return None
        with self._lock:
            row = self._db.execute(
                "SELECT data, expires FROM sessions WHERE id = ?", (sid,)
            ).fetchone()
        if row is None:
            return None
        if row[1] < time.time():
            self.delete(sid)
            return None
        loaded = json.loads(row[0])
        return loaded if isinstance(loaded, dict) else None

    def delete(self, sid: str) -> None:
        self._db.execute("DELETE FROM sessions WHERE id = ?", (sid,))


class RateLimiter:
    """Sliding window per key, in memory. Enough for login and approval endpoints.

    Keys are client addresses: behind a reverse proxy, every client shares one address
    unless the proxy is configured as trusted. Deploy with the proxy's address handling.
    """

    MAX_KEYS = 10_000

    def __init__(self, limit: int, window: float) -> None:
        self.limit, self.window = limit, window
        self._hits: dict[str, list[float]] = {}

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        if len(self._hits) > self.MAX_KEYS:  # bounded memory: forget keys with no recent hit
            self._hits = {k: v for k, v in self._hits.items() if v and now - v[-1] < self.window}
        hits = [t for t in self._hits.get(key, []) if now - t < self.window]
        if len(hits) >= self.limit:
            self._hits[key] = hits
            return False
        hits.append(now)
        self._hits[key] = hits
        return True
