"""A throwaway PostgreSQL in a Docker container, shared by the whole test session."""

from __future__ import annotations

import atexit
import shutil
import subprocess
import time
import uuid

import pytest

from asac.adapters.state_postgres import PostgresStateStore

IMAGE = "postgres:16-alpine"
_state: dict[str, str] = {}


def _docker_ok() -> bool:
    if shutil.which("docker") is None:
        return False
    return subprocess.run(["docker", "info"], capture_output=True).returncode == 0


def _start() -> str:
    if "dsn" in _state:
        return _state["dsn"]
    if not _docker_ok():
        pytest.skip("docker is not available; the Postgres conformance run needs it")
    name = f"asac-pg-{uuid.uuid4().hex[:8]}"
    subprocess.run(
        ["docker", "run", "-d", "--rm", "--name", name, "-e", "POSTGRES_PASSWORD=test",
         "-p", "127.0.0.1::5432", IMAGE],
        check=True, capture_output=True,
    )  # fmt: skip
    atexit.register(lambda: subprocess.run(["docker", "rm", "-f", name], capture_output=True))
    port = subprocess.run(
        ["docker", "port", name, "5432/tcp"], check=True, capture_output=True, text=True
    ).stdout.split(":")[-1].strip()  # fmt: skip
    dsn = f"postgresql://postgres:test@127.0.0.1:{port}/postgres"
    import psycopg

    for _ in range(60):
        try:
            psycopg.connect(dsn, connect_timeout=2).close()
            break
        except psycopg.OperationalError:
            time.sleep(0.5)
    else:
        pytest.fail("postgres container did not become ready")
    _state.update(dsn=dsn, name=name)
    return dsn


def fresh_postgres_dsn() -> str:
    """The DSN of a new, empty database on the shared container."""
    import psycopg

    dsn = _start()
    db = f"t_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(f"CREATE DATABASE {db}")  # type: ignore[arg-type]
    own = dsn.rsplit("/", 1)[0] + f"/{db}"
    _state["last_dsn"] = own
    return own


def fresh_postgres_store() -> PostgresStateStore:
    """A store on an empty database: each test gets its own database."""
    return PostgresStateStore(fresh_postgres_dsn())


def second_connection_to(store: PostgresStateStore) -> PostgresStateStore:  # type: ignore[valid-type]
    return PostgresStateStore(_state["last_dsn"])
