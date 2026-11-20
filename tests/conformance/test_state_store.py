"""Conformance suite for the StateStore port. Add an adapter to ``ADAPTERS`` to test it."""

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from asac.adapters.state_sqlite import SqliteStateStore
from asac.ports.state import (
    EvidenceExists,
    GateError,
    GateRecord,
    NotFound,
    RunExists,
    StateStore,
)

AT = "2026-01-01T00:00:00Z"
ADAPTERS: dict[str, Callable[[Path], StateStore]] = {
    "sqlite": lambda tmp: SqliteStateStore(tmp / "state.db"),
}


@pytest.fixture(
    params=[
        "sqlite",
        pytest.param("postgres", marks=[pytest.mark.integration, pytest.mark.enable_socket]),
    ]
)
def store(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[StateStore]:
    if request.param == "postgres":
        from tests.conformance.postgres_fixture import fresh_postgres_store

        s: StateStore = fresh_postgres_store()
    else:
        s = ADAPTERS[request.param](tmp_path)
    s.create_run("r1", "feature", AT)
    yield s


def _gate(gid: str = "g1") -> GateRecord:
    return GateRecord(gid, "r1", "requirements", "human", "product_owner", "pending", AT, None)


def test_duplicate_run_rejected(store: StateStore) -> None:
    with pytest.raises(RunExists):
        store.create_run("r1", "feature", AT)


def test_unknown_run(store: StateStore) -> None:
    with pytest.raises(NotFound):
        store.get_run("nope")


def test_step_status_roundtrip(store: StateStore) -> None:
    assert store.get_step_status("r1", "s") is None
    store.set_step_status("r1", "s", "running")
    store.set_step_status("r1", "s", "completed")
    assert store.list_steps("r1") == {"s": "completed"}


def test_evidence_is_append_only(store: StateStore) -> None:
    store.add_evidence("r1", "spec_reviewed", "requirements", AT)
    assert store.has_evidence("r1", "spec_reviewed")
    with pytest.raises(EvidenceExists):
        store.add_evidence("r1", "spec_reviewed", "other", AT)
    assert len(store.list_evidence("r1")) == 1


def test_evidence_requires_run(store: StateStore) -> None:
    with pytest.raises(NotFound):
        store.add_evidence("missing", "e", "s", AT)


def test_bootstrapped_flag(store: StateStore) -> None:
    store.add_evidence("r1", "e", "bootstrap", AT, approved_by="me", bootstrapped=True)
    (rec,) = store.list_evidence("r1")
    assert rec.bootstrapped and rec.approved_by == "me"


def test_gate_transitions(store: StateStore) -> None:
    store.open_gate(_gate())
    assert store.get_gate("g1").status == "pending"
    done = store.decide_gate("g1", "approved", "alice", AT, "ok")
    assert (done.status, done.decided_by, done.comment) == ("approved", "alice", "ok")
    with pytest.raises(GateError):
        store.decide_gate("g1", "rejected", "bob", AT, None)


def test_gate_ids_unique_and_filterable(store: StateStore) -> None:
    store.open_gate(_gate("g1"))
    store.open_gate(_gate("g2"))
    with pytest.raises(GateError):
        store.open_gate(_gate("g1"))
    store.decide_gate("g2", "rejected", "bob", AT, None)
    assert [g.gate_id for g in store.list_gates("pending")] == ["g1"]


def test_unknown_gate(store: StateStore) -> None:
    with pytest.raises(NotFound):
        store.decide_gate("zz", "approved", "a", AT, None)


def test_audit_is_ordered(store: StateStore) -> None:
    store.append_audit("r1", "a", "one", AT)
    store.append_audit("r1", "a", "two", AT, step_id="s")
    assert [r.action for r in store.audit("r1")] == ["one", "two"]


def test_reopen_only_rejected(store: StateStore) -> None:
    store.open_gate(_gate("g1"))
    with pytest.raises(GateError):
        store.reopen_gate("g1")  # still pending
    store.decide_gate("g1", "rejected", "bob", AT, "no")
    again = store.reopen_gate("g1")
    assert (again.status, again.decided_by, again.comment) == ("pending", None, None)
    with pytest.raises(NotFound):
        store.reopen_gate("zz")


def test_decide_gate_has_a_single_winner(store: StateStore) -> None:
    """Two deciders racing on one gate: exactly one succeeds, the other gets GateError."""
    from concurrent.futures import ThreadPoolExecutor

    store.open_gate(_gate("g1"))
    if not hasattr(store, "_conn") or type(store).__name__ != "PostgresStateStore":
        pytest.skip("concurrency is exercised through the shared-server adapter")
    from tests.conformance.postgres_fixture import second_connection_to

    other = second_connection_to(store)

    def decide(s: StateStore, who: str) -> str:
        try:
            s.decide_gate("g1", "approved", who, AT, None)
            return "won"
        except GateError:
            return "lost"

    with ThreadPoolExecutor(2) as pool:
        results = sorted(pool.map(lambda a: decide(*a), [(store, "a"), (other, "b")]))
    assert results == ["lost", "won"]


def test_append_only_is_enforced_by_the_store(store: StateStore) -> None:
    store.add_evidence("r1", "e", "s", AT)
    store.append_audit("r1", "a", "x", AT)
    raw = getattr(store, "_conn", None)
    if raw is None:
        pytest.skip("adapter has no SQL connection to attack")
    marker = "%s" if type(store).__name__ == "PostgresStateStore" else "?"
    for sql in (
        f"UPDATE evidence SET produced_by = {marker}",
        "DELETE FROM evidence",
        f"UPDATE audit SET actor = {marker}",
        "DELETE FROM audit",
    ):
        args = ("x",) if marker in sql else ()
        with pytest.raises(Exception, match="append-only"):
            raw.execute(sql, args)
    assert len(store.list_evidence("r1")) == 1
