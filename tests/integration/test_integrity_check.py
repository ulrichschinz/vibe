"""Phase 8 — Integritäts-Prüf-CLI.

Akzeptanzkriterium für R-12: künstliches Mutieren eines Archive-Bytes muss
durch den Check entdeckt werden.
"""
from __future__ import annotations

import os
import stat
from datetime import date
from pathlib import Path

import pytest
from sqlmodel import Session, select

from app.domains.billing.models import IntegrityCheckResult, IntegrityCheckRun
from services.invoicing.archive import archive_document
from services.invoicing.document import render_document
from services.invoicing.finalize import FinalizeOptions, finalize_invoice
from tests.fixtures.factories import make_draft_invoice, make_issuer, make_lead_de_b2b


@pytest.fixture
def patched_engine(engine, monkeypatch):
    """Point the integrity_check module's engine at the per-test engine."""
    import services.invoicing.integrity_check as ic
    monkeypatch.setattr(ic, "engine", engine)
    return engine


@pytest.mark.integration
@pytest.mark.slow
def test_integrity_check_passes_for_clean_archive(patched_engine, archive_dir):
    with Session(patched_engine) as session:
        make_issuer(session)
        lead = make_lead_de_b2b(session)
        inv = make_draft_invoice(session, lead)
        finalize_invoice(
            session, inv.id,
            options=FinalizeOptions(today=date(2026, 5, 9), renderer=render_document, archiver=archive_document),
        )

    from services.invoicing.integrity_check import run as run_check
    scanned, mismatches = run_check()
    assert scanned == 1
    assert mismatches == []

    with Session(patched_engine) as session:
        latest = session.exec(select(IntegrityCheckRun).order_by(IntegrityCheckRun.id.desc())).first()
        assert latest.result == IntegrityCheckResult.ok


@pytest.mark.integration
@pytest.mark.slow
def test_integrity_check_detects_byte_mutation(patched_engine, archive_dir):
    """R-12 manipulation probe: flip one byte → check must go red."""
    with Session(patched_engine) as session:
        make_issuer(session)
        lead = make_lead_de_b2b(session)
        inv = make_draft_invoice(session, lead)
        f = finalize_invoice(
            session, inv.id,
            options=FinalizeOptions(today=date(2026, 5, 9), renderer=render_document, archiver=archive_document),
        )
        pdf_path = f.archive_path_pdf

    # Mutate a single byte mid-file. The PDF is chmod 0444, so we have to widen
    # permissions first (this is exactly what the WORM strategy is supposed to
    # make annoying — and what an attacker would have to do).
    os.chmod(pdf_path, stat.S_IRUSR | stat.S_IWUSR)
    p = Path(pdf_path)
    data = bytearray(p.read_bytes())
    data[len(data) // 2] = (data[len(data) // 2] + 1) % 256
    p.write_bytes(bytes(data))

    from services.invoicing.integrity_check import run as run_check
    scanned, mismatches = run_check()
    assert scanned == 1
    assert len(mismatches) >= 1
    assert any("hash mismatch" in m.reason for m in mismatches)


@pytest.mark.integration
@pytest.mark.slow
def test_integrity_check_detects_missing_file(patched_engine, archive_dir):
    with Session(patched_engine) as session:
        make_issuer(session)
        lead = make_lead_de_b2b(session)
        inv = make_draft_invoice(session, lead)
        f = finalize_invoice(
            session, inv.id,
            options=FinalizeOptions(today=date(2026, 5, 9), renderer=render_document, archiver=archive_document),
        )
        pdf_path = f.archive_path_pdf

    os.chmod(pdf_path, stat.S_IRUSR | stat.S_IWUSR)
    Path(pdf_path).unlink()

    from services.invoicing.integrity_check import run as run_check
    _, mismatches = run_check()
    assert any("missing" in m.reason for m in mismatches)
