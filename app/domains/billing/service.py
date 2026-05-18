"""app.domains.billing.service — Billing-MCP-Facade (Schritt 8).

The billing-internal invoice-draft/line/get/list construction + the
serialization dict moved here **byte-for-byte** from
`services/mcp_server.py` (ADR-009 §D). The MCP interface tools now delegate
here instead of constructing `Invoice(...)`/`InvoiceLineItem(...)`
themselves → `interfaces/mcp` no longer constructs domain models
(import-linter, Schritt 8 edge set).

Construction uses billing's **own** models (`app.domains.billing.models` —
allowed intra-domain edge). Finalize/Storno orchestration stays in the MCP
tool calling `services/invoicing/` with the `BillingOrder`
`customer_resolver` wired in the interface (Schritt-5 pattern — the
resolver must NOT be pulled into `services/invoicing/`: forbidden edge +
`.coveragerc` 90 % gate). Caller-owned `Session` (Scaffold-/Service-
Vertrag). `# type: ignore` on the ORM expressions is the documented
Schritt-4/6/7 strict-mypy pattern (no behaviour change).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from sqlmodel import Session, select

from app.domains.billing.models import (
    Invoice,
    InvoiceKind,
    InvoiceLineItem,
    InvoiceStatus,
)


def serialize_invoice(inv: Invoice, lines: list[InvoiceLineItem]) -> dict:
    return {
        "id": inv.id,
        "number": inv.number,
        "status": inv.status.value,
        "kind": inv.kind.value,
        "fiscal_year": inv.fiscal_year,
        "sequence_number": inv.sequence_number,
        "invoice_date": inv.invoice_date.isoformat() if inv.invoice_date else None,
        "leistungsdatum": inv.leistungsdatum.isoformat() if inv.leistungsdatum else None,
        "due_date": inv.due_date.isoformat() if inv.due_date else None,
        "currency": inv.currency,
        "subtotal_net": str(inv.subtotal_net) if inv.subtotal_net is not None else None,
        "vat_total": str(inv.vat_total) if inv.vat_total is not None else None,
        "total_gross": str(inv.total_gross) if inv.total_gross is not None else None,
        "hint_kleinunternehmer": inv.hint_kleinunternehmer,
        "hint_reverse_charge": inv.hint_reverse_charge,
        "hint_third_country": inv.hint_third_country,
        "lead_id": inv.lead_id,
        "related_invoice_id": inv.related_invoice_id,
        "lines": [
            {
                "position": ln.position,
                "description": ln.description,
                "quantity": str(ln.quantity),
                "unit": ln.unit,
                "unit_price_net": str(ln.unit_price_net),
                "vat_rate": str(ln.vat_rate),
                "line_net": str(ln.line_net),
                "line_vat": str(ln.line_vat),
                "line_gross": str(ln.line_gross),
            }
            for ln in lines
        ],
    }


def _load_lines(session: Session, invoice_id: int) -> list[InvoiceLineItem]:
    return list(
        session.exec(
            select(InvoiceLineItem)
            .where(InvoiceLineItem.invoice_id == invoice_id)
            .order_by(InvoiceLineItem.position)  # type: ignore[arg-type]
        ).all()
    )


def serialize_with_lines(session: Session, inv: Invoice) -> dict:
    return serialize_invoice(inv, _load_lines(session, inv.id))  # type: ignore[arg-type]


def create_draft(
    session: Session,
    *,
    lead_id: Optional[int] = None,
    leistungsdatum: Optional[str] = None,
    title: Optional[str] = None,
    intro_text: Optional[str] = None,
    customer_reference: Optional[str] = None,
) -> dict:
    inv = Invoice(
        status=InvoiceStatus.draft,
        kind=InvoiceKind.invoice,
        lead_id=lead_id,
        title=title,
        intro_text=intro_text,
        customer_reference=customer_reference,
        leistungsdatum=date.fromisoformat(leistungsdatum) if leistungsdatum else None,
    )
    session.add(inv)
    session.commit()
    session.refresh(inv)
    return serialize_invoice(inv, [])


def add_line(
    session: Session,
    *,
    invoice_id: int,
    description: str,
    quantity: str,
    unit_price_net: str,
    vat_rate: str = "19",
    unit: str = "Std",
) -> dict:
    inv = session.get(Invoice, invoice_id)
    if inv is None:
        raise ValueError(f"invoice {invoice_id} not found")
    if inv.status != InvoiceStatus.draft:
        raise ValueError("invoice is not draft")
    existing = list(
        session.exec(select(InvoiceLineItem).where(InvoiceLineItem.invoice_id == invoice_id)).all()
    )
    qty = Decimal(quantity)
    price = Decimal(unit_price_net)
    rate = Decimal(vat_rate)
    line_net = (qty * price).quantize(Decimal("0.01"))
    line_vat = (line_net * rate / Decimal(100)).quantize(Decimal("0.01"))
    ln = InvoiceLineItem(
        invoice_id=inv.id,
        position=(max((e.position for e in existing), default=0)) + 1,
        description=description,
        quantity=qty,
        unit=unit,
        unit_price_net=price,
        vat_rate=rate,
        vat_code="S",
        line_net=line_net,
        line_vat=line_vat,
        line_gross=line_net + line_vat,
    )
    session.add(ln)
    session.commit()
    session.refresh(ln)
    return {"position": ln.position, "line_net": str(ln.line_net)}


def get_invoice(session: Session, invoice_id: int) -> dict:
    inv = session.get(Invoice, invoice_id)
    if inv is None:
        raise ValueError(f"invoice {invoice_id} not found")
    return serialize_with_lines(session, inv)


def list_invoices(
    session: Session,
    year: Optional[int] = None,
    status: Optional[str] = None,
) -> list[dict]:
    q = select(Invoice).order_by(Invoice.created_at.desc())  # type: ignore[attr-defined,arg-type]
    if year is not None:
        q = q.where(Invoice.fiscal_year == year)
    if status:
        q = q.where(Invoice.status == status)
    return [serialize_with_lines(session, inv) for inv in session.exec(q).all()]
