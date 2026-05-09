"""Hash-Chain-Helper für Integritäts-Audits (R-12).

Die eigentliche Hash-Berechnung lebt in ``finalize.py`` (Single-Path beim
Finalize), aber der Walker für den Audit-Job sitzt hier.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Iterable

from sqlmodel import Session, select

from models import Invoice, InvoiceStatus


def genesis_hash(fiscal_year: int) -> str:
    return hashlib.sha256(f"genesis-invoice-chain-{fiscal_year}".encode()).hexdigest()


@dataclass(frozen=True)
class ChainMismatch:
    invoice_id: int
    number: str
    reason: str
    expected: str
    actual: str


def list_finalized_in_year(session: Session, fiscal_year: int) -> list[Invoice]:
    return list(session.exec(
        select(Invoice)
        .where(Invoice.fiscal_year == fiscal_year)
        .where(Invoice.status != InvoiceStatus.draft)
        .order_by(Invoice.sequence_number)
    ).all())


def recompute_invoice_hash(invoice: Invoice, pdf_bytes: bytes, xml_bytes: bytes) -> str:
    """Mirror of ``finalize._content_hash``. Kept in lock-step with that function.

    If the algorithm ever needs to change, bump ``hash_algo`` on Invoice and
    fork this branch by version.
    """
    pdf_h = hashlib.sha256(pdf_bytes).hexdigest()
    xml_h = hashlib.sha256(xml_bytes).hexdigest()
    header = {
        "number": invoice.number,
        "fiscal_year": invoice.fiscal_year,
        "sequence_number": invoice.sequence_number,
        "invoice_date": invoice.invoice_date,
        "leistungsdatum": invoice.leistungsdatum,
        "iss_legal_name": invoice.iss_legal_name,
        "iss_ust_id": invoice.iss_ust_id,
        "iss_steuernummer": invoice.iss_steuernummer,
        "cust_legal_name": invoice.cust_legal_name,
        "cust_vat_id": invoice.cust_vat_id,
        "subtotal_net": invoice.subtotal_net,
        "vat_total": invoice.vat_total,
        "total_gross": invoice.total_gross,
    }
    canonical = json.dumps(header, sort_keys=True, default=str).encode("utf-8")
    h = hashlib.sha256()
    h.update(pdf_h.encode("ascii"))
    h.update(b"\n")
    h.update(xml_h.encode("ascii"))
    h.update(b"\n")
    h.update(canonical)
    return h.hexdigest()


def verify_chain(invoices: Iterable[Invoice]) -> list[ChainMismatch]:
    """Walk ``invoices`` (ordered by sequence_number) and verify hash_prev links."""
    mismatches: list[ChainMismatch] = []
    prev_hash: str | None = None
    for inv in invoices:
        expected_prev = prev_hash if prev_hash is not None else genesis_hash(inv.fiscal_year)
        if inv.hash_prev != expected_prev:
            mismatches.append(ChainMismatch(
                invoice_id=inv.id,
                number=inv.number or f"#{inv.id}",
                reason="hash_prev mismatch",
                expected=expected_prev,
                actual=inv.hash_prev or "",
            ))
        prev_hash = inv.hash_sha256
    return mismatches
