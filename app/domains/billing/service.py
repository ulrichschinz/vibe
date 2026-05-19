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
    IssuerProfile,
    ViesAuditEntry,  # noqa: F401  re-exported for app.interfaces (T2b indirect-import seam)
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


# ── Web/REST construction (T2a — one logic, three clients) ─────────────────
#
# Invoice/InvoiceLineItem/IssuerProfile construction that lived inline in the
# web/REST handlers moves here verbatim (the MCP shape is ``create_draft``/
# ``add_line`` above). Decimal/`_to_decimal` parsing, position queries,
# net/vat math and the HTTP guards (404/409) stay in the handler (the seam) —
# callers pass the final values; the body is byte-identical to the old inline
# ctor + ``session`` calls. ``services/invoicing/`` is untouched
# (move-not-rewrite): this is billing-domain draft construction, not the
# finalize compliance core.


def create_invoice_web(
    session: Session,
    *,
    lead_id: Optional[int],
    title: Optional[str],
    intro_text: Optional[str],
    customer_reference: Optional[str],
    payment_terms_text: Optional[str],
    leistungsdatum: Optional[date],
    cust_legal_name: Optional[str],
    cust_company: Optional[str],
    cust_street: Optional[str],
    cust_postal_code: Optional[str],
    cust_city: Optional[str],
    cust_country_code: Optional[str],
    cust_vat_id: Optional[str],
) -> Invoice:
    inv = Invoice(
        status=InvoiceStatus.draft,
        kind=InvoiceKind.invoice,
        lead_id=lead_id,
        title=title,
        intro_text=intro_text,
        customer_reference=customer_reference,
        payment_terms_text=payment_terms_text,
        leistungsdatum=leistungsdatum,
        cust_legal_name=cust_legal_name,
        cust_company=cust_company,
        cust_street=cust_street,
        cust_postal_code=cust_postal_code,
        cust_city=cust_city,
        cust_country_code=cust_country_code,
        cust_vat_id=cust_vat_id,
    )
    session.add(inv)
    session.commit()
    session.refresh(inv)
    return inv


def add_invoice_line_web(
    session: Session,
    *,
    invoice_id: int,
    position: int,
    description: str,
    quantity: Decimal,
    unit: str,
    unit_price_net: Decimal,
    vat_rate: Decimal,
    line_net: Decimal,
    line_vat: Decimal,
) -> None:
    ln = InvoiceLineItem(
        invoice_id=invoice_id,
        position=position,
        description=description,
        quantity=quantity,
        unit=unit,
        unit_price_net=unit_price_net,
        vat_rate=vat_rate,
        vat_code="S",
        line_net=line_net,
        line_vat=line_vat,
        line_gross=line_net + line_vat,
    )
    session.add(ln)
    session.commit()


def create_draft_api(session: Session, payload: dict) -> Invoice:
    leistungsdatum = payload.get("leistungsdatum")
    inv = Invoice(
        status=InvoiceStatus.draft,
        kind=InvoiceKind.invoice,
        lead_id=payload.get("lead_id"),
        title=payload.get("title"),
        intro_text=payload.get("intro_text"),
        customer_reference=payload.get("customer_reference"),
        leistungsdatum=date.fromisoformat(leistungsdatum) if leistungsdatum else None,
    )
    # Allow direct customer block override.
    cust = payload.get("customer") or {}
    inv.cust_legal_name = cust.get("legal_name")
    inv.cust_company = cust.get("company")
    inv.cust_street = cust.get("street")
    inv.cust_postal_code = cust.get("postal_code")
    inv.cust_city = cust.get("city")
    inv.cust_country_code = cust.get("country_code")
    inv.cust_vat_id = cust.get("vat_id")
    if "is_business" in cust:
        inv.cust_is_business = bool(cust["is_business"])
    session.add(inv)
    session.commit()
    session.refresh(inv)
    return inv


def add_line_api(
    session: Session,
    *,
    invoice_id: int,
    position: int,
    description: str,
    quantity: Decimal,
    unit: str,
    unit_price_net: Decimal,
    vat_rate: Decimal,
    line_net: Decimal,
    line_vat: Decimal,
) -> InvoiceLineItem:
    ln = InvoiceLineItem(
        invoice_id=invoice_id,
        position=position,
        description=description,
        quantity=quantity,
        unit=unit,
        unit_price_net=unit_price_net,
        vat_rate=vat_rate,
        vat_code="S",
        line_net=line_net,
        line_vat=line_vat,
        line_gross=line_net + line_vat,
    )
    session.add(ln)
    session.commit()
    session.refresh(ln)
    return ln


def get_or_create_issuer_web(
    session: Session,
    *,
    legal_name: str,
    street: str,
    postal_code: str,
    city: str,
) -> IssuerProfile:
    issuer = session.get(IssuerProfile, 1)
    if issuer is None:
        issuer = IssuerProfile(
            id=1, legal_name=legal_name, street=street, postal_code=postal_code, city=city
        )
    return issuer
