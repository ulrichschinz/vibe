"""R-02 race-condition test: parallel finalize must produce dense, unique numbers.

We don't run a full finalize in this test (Phase 5 wires the renderer); instead
we exercise the lock-critical primitive ``assign_next_number`` from N threads
each in their own session — same DB, same engine, same fiscal_year. The
``BEGIN IMMEDIATE`` event hook on the engine + ``busy_timeout=5000`` PRAGMA
should make the calls serialize correctly.
"""
from __future__ import annotations

import threading

import pytest
from sqlmodel import Session, select

from app.domains.billing.models import InvoiceNumberSequence
from services.invoicing.numbering import assign_next_number


@pytest.mark.integration
@pytest.mark.slow
def test_concurrent_assignment_produces_dense_unique_sequence(engine):
    N = 30  # threads
    barrier = threading.Barrier(N)
    results: list[int] = []
    errors: list[Exception] = []
    lock = threading.Lock()

    def worker():
        try:
            barrier.wait()
            with Session(engine) as s:
                seq, _ = assign_next_number(s, 2026)
                s.commit()
            with lock:
                results.append(seq)
        except Exception as exc:  # pragma: no cover — surfaced via assertion below
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(N)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"thread errors: {errors}"
    assert sorted(results) == list(range(1, N + 1)), (
        f"expected dense 1..{N}, got {sorted(results)}"
    )
    assert len(set(results)) == N, f"expected {N} unique, got {len(set(results))}"

    with Session(engine) as s:
        row = s.exec(select(InvoiceNumberSequence).where(InvoiceNumberSequence.fiscal_year == 2026)).one()
        assert row.last_sequence == N
