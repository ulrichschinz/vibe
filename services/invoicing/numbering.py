"""Race-safe Rechnungsnummern-Vergabe (R-02).

Format: ``RE-{YYYY}-{NNNN:04d}`` (z. B. ``RE-2026-0001``). Eigener Prefix,
getrennt vom Angebots-Prefix ``AR-``.

Atomarität: Die Vergabe muss innerhalb einer Transaktion stattfinden, die mit
``BEGIN IMMEDIATE`` gestartet wurde. Unsere ``database.engine`` setzt das per
Event-Listener für jede Transaktion automatisch — d. h. jede Session, die
bereits Schreib-Operationen tut, erfüllt die Voraussetzung. Concurrency-Test
in ``tests/integration/test_numbering_concurrency.py``.

Lückenlosigkeit: Der Sequence-Counter wird nur innerhalb einer
Finalize-Transaktion inkrementiert. Schlägt etwas vor dem COMMIT fehl, rollt
SQLite zurück und kein Counter ist verbraucht.
"""
from __future__ import annotations

from datetime import datetime
from typing import Tuple

from sqlmodel import Session, select

from app.domains.billing.models import InvoiceNumberSequence

PREFIX = "RE"


def assign_next_number(session: Session, fiscal_year: int) -> Tuple[int, str]:
    """Inkrementiere den Counter für ``fiscal_year`` und gib (seq, formatted) zurück.

    Muss innerhalb einer aktiven Schreib-Transaktion aufgerufen werden, sonst
    ist Race-Sicherheit nicht gewährleistet. Erste Nutzung eines Jahres legt
    die Sequence-Row implizit an.
    """
    if fiscal_year < 2000 or fiscal_year > 2999:
        raise ValueError(f"Implausible fiscal_year: {fiscal_year}")

    seq = session.exec(
        select(InvoiceNumberSequence).where(InvoiceNumberSequence.fiscal_year == fiscal_year)
    ).one_or_none()
    if seq is None:
        seq = InvoiceNumberSequence(fiscal_year=fiscal_year, last_sequence=0, prefix=PREFIX)
        session.add(seq)
        session.flush()

    seq.last_sequence += 1
    seq.updated_at = datetime.utcnow()
    session.add(seq)
    session.flush()

    formatted = format_number(fiscal_year, seq.last_sequence)
    return seq.last_sequence, formatted


def format_number(fiscal_year: int, sequence: int) -> str:
    return f"{PREFIX}-{fiscal_year}-{sequence:04d}"
