"""Web UI für die Rechnungs-Verwaltung."""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from database import get_session
from models import (
    Invoice,
    InvoiceKind,
    InvoiceLineItem,
    InvoiceStatus,
    IssuerProfile,
    Lead,
    User,
    UserRole,
    ViesAuditEntry,
    ViesResponseStatus,
)
from app.domains.leads.billing_export import build_billing_customer
from app.shared.labels import INVOICE_STATUS_LABELS
from services.auth import require_editor, require_login
from services.invoicing.archive import archive_document
from services.invoicing.document import render_document
from services.invoicing.finalize import (
    FinalizeError,
    FinalizeOptions,
    InvoiceValidationError,
    create_storno,
    finalize_invoice,
    mark_paid,
    mark_sent,
)
from services.invoicing.state_machine import InvoiceStateError
from services.invoicing.vies import (
    ViesBlockedError,
    ViesGateOptions,
    make_vies_gate,
)

router = APIRouter()
templates = Jinja2Templates(directory="templates")
templates.env.globals["INVOICE_STATUS_LABELS"] = INVOICE_STATUS_LABELS
templates.env.globals["InvoiceStatus"] = InvoiceStatus
templates.env.globals["InvoiceKind"] = InvoiceKind


# ── List + detail + new ─────────────────────────────────────────────────────


@router.get("/invoices/", response_class=HTMLResponse)
def invoice_list(
    request: Request,
    year: Optional[int] = None,
    status: Optional[str] = None,
    session: Session = Depends(get_session),
    _=Depends(require_login),
):
    query = select(Invoice).order_by(Invoice.created_at.desc())
    if year:
        query = query.where(Invoice.fiscal_year == year)
    if status:
        query = query.where(Invoice.status == status)
    invoices = list(session.exec(query).all())
    return templates.TemplateResponse("invoices/list.html", {
        "request": request,
        "invoices": invoices,
        "filter_year": year,
        "filter_status": status,
    })


@router.get("/invoices/new", response_class=HTMLResponse)
def invoice_new(
    request: Request,
    lead_id: Optional[int] = None,
    session: Session = Depends(get_session),
    _=Depends(require_editor),
):
    issuer = session.get(IssuerProfile, 1)
    if issuer is None:
        return RedirectResponse(
            "/admin/issuer?msg=Bitte+vor+der+ersten+Rechnung+die+Aussteller-Daten+pflegen.",
            status_code=303,
        )
    lead = session.get(Lead, lead_id) if lead_id else None
    return templates.TemplateResponse("invoices/edit.html", {
        "request": request,
        "invoice": None,
        "lead": lead,
        "lines": [],
        "action": "/invoices/",
    })


@router.post("/invoices/", response_class=RedirectResponse)
def invoice_create(
    lead_id: Optional[int] = Form(None),
    title: str = Form(""),
    intro_text: str = Form(""),
    customer_reference: str = Form(""),
    leistungsdatum: str = Form(""),
    payment_terms_text: str = Form(""),
    # Customer override fields (optional — Lead snapshot wins if these are blank)
    cust_legal_name: str = Form(""),
    cust_company: str = Form(""),
    cust_street: str = Form(""),
    cust_postal_code: str = Form(""),
    cust_city: str = Form(""),
    cust_country_code: str = Form(""),
    cust_vat_id: str = Form(""),
    session: Session = Depends(get_session),
    _=Depends(require_editor),
):
    inv = Invoice(
        status=InvoiceStatus.draft,
        kind=InvoiceKind.invoice,
        lead_id=lead_id or None,
        title=title or None,
        intro_text=intro_text or None,
        customer_reference=customer_reference or None,
        payment_terms_text=payment_terms_text or None,
        leistungsdatum=_parse_date(leistungsdatum),
        cust_legal_name=cust_legal_name or None,
        cust_company=cust_company or None,
        cust_street=cust_street or None,
        cust_postal_code=cust_postal_code or None,
        cust_city=cust_city or None,
        cust_country_code=cust_country_code or None,
        cust_vat_id=cust_vat_id or None,
    )
    session.add(inv)
    session.commit()
    session.refresh(inv)
    return RedirectResponse(f"/invoices/{inv.id}/edit", status_code=303)


@router.get("/invoices/{invoice_id}", response_class=HTMLResponse)
def invoice_detail(
    request: Request,
    invoice_id: int,
    session: Session = Depends(get_session),
    _=Depends(require_login),
):
    invoice = session.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(404)
    lines = list(session.exec(
        select(InvoiceLineItem)
        .where(InvoiceLineItem.invoice_id == invoice.id)
        .order_by(InvoiceLineItem.position)
    ).all())
    lead = session.get(Lead, invoice.lead_id) if invoice.lead_id else None
    related = session.get(Invoice, invoice.related_invoice_id) if invoice.related_invoice_id else None
    storno = None
    if invoice.kind == InvoiceKind.invoice:
        storno = session.exec(
            select(Invoice).where(Invoice.related_invoice_id == invoice.id).where(Invoice.kind == InvoiceKind.storno)
        ).first()
    return templates.TemplateResponse("invoices/detail.html", {
        "request": request,
        "invoice": invoice,
        "lines": lines,
        "lead": lead,
        "related": related,
        "storno": storno,
    })


@router.get("/invoices/{invoice_id}/edit", response_class=HTMLResponse)
def invoice_edit(
    request: Request,
    invoice_id: int,
    session: Session = Depends(get_session),
    _=Depends(require_editor),
):
    invoice = session.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(404)
    if invoice.status != InvoiceStatus.draft:
        return RedirectResponse(f"/invoices/{invoice_id}", status_code=303)
    lines = list(session.exec(
        select(InvoiceLineItem)
        .where(InvoiceLineItem.invoice_id == invoice.id)
        .order_by(InvoiceLineItem.position)
    ).all())
    lead = session.get(Lead, invoice.lead_id) if invoice.lead_id else None
    return templates.TemplateResponse("invoices/edit.html", {
        "request": request,
        "invoice": invoice,
        "lead": lead,
        "lines": lines,
        "action": f"/invoices/{invoice_id}/update",
    })


@router.post("/invoices/{invoice_id}/update", response_class=RedirectResponse)
def invoice_update(
    invoice_id: int,
    title: str = Form(""),
    intro_text: str = Form(""),
    customer_reference: str = Form(""),
    leistungsdatum: str = Form(""),
    payment_terms_text: str = Form(""),
    cust_legal_name: str = Form(""),
    cust_company: str = Form(""),
    cust_street: str = Form(""),
    cust_postal_code: str = Form(""),
    cust_city: str = Form(""),
    cust_country_code: str = Form(""),
    cust_vat_id: str = Form(""),
    session: Session = Depends(get_session),
    _=Depends(require_editor),
):
    invoice = session.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(404)
    if invoice.status != InvoiceStatus.draft:
        raise HTTPException(409, "Cannot edit non-draft invoice")
    invoice.title = title or None
    invoice.intro_text = intro_text or None
    invoice.customer_reference = customer_reference or None
    invoice.leistungsdatum = _parse_date(leistungsdatum)
    invoice.payment_terms_text = payment_terms_text or None
    invoice.cust_legal_name = cust_legal_name or None
    invoice.cust_company = cust_company or None
    invoice.cust_street = cust_street or None
    invoice.cust_postal_code = cust_postal_code or None
    invoice.cust_city = cust_city or None
    invoice.cust_country_code = cust_country_code or None
    invoice.cust_vat_id = cust_vat_id or None
    invoice.updated_at = datetime.utcnow()
    session.add(invoice)
    session.commit()
    return RedirectResponse(f"/invoices/{invoice_id}/edit", status_code=303)


# ── Line items ──────────────────────────────────────────────────────────────


@router.post("/invoices/{invoice_id}/lines", response_class=RedirectResponse)
def invoice_add_line(
    invoice_id: int,
    description: str = Form(...),
    quantity: str = Form(...),
    unit: str = Form("Std"),
    unit_price_net: str = Form(...),
    vat_rate: str = Form("19"),
    session: Session = Depends(get_session),
    _=Depends(require_editor),
):
    invoice = session.get(Invoice, invoice_id)
    if invoice is None or invoice.status != InvoiceStatus.draft:
        raise HTTPException(409)
    pos_query = select(InvoiceLineItem).where(InvoiceLineItem.invoice_id == invoice.id)
    existing = list(session.exec(pos_query).all())
    next_pos = (max((l.position for l in existing), default=0)) + 1
    qty = _to_decimal(quantity)
    price = _to_decimal(unit_price_net)
    rate = _to_decimal(vat_rate)
    line_net = (qty * price).quantize(Decimal("0.01"))
    line_vat = (line_net * rate / Decimal(100)).quantize(Decimal("0.01"))
    ln = InvoiceLineItem(
        invoice_id=invoice.id,
        position=next_pos,
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
    return RedirectResponse(f"/invoices/{invoice_id}/edit", status_code=303)


@router.post("/invoices/{invoice_id}/lines/{line_id}/delete", response_class=RedirectResponse)
def invoice_delete_line(
    invoice_id: int,
    line_id: int,
    session: Session = Depends(get_session),
    _=Depends(require_editor),
):
    invoice = session.get(Invoice, invoice_id)
    if invoice is None or invoice.status != InvoiceStatus.draft:
        raise HTTPException(409)
    line = session.get(InvoiceLineItem, line_id)
    if line is None or line.invoice_id != invoice.id:
        raise HTTPException(404)
    session.delete(line)
    session.commit()
    return RedirectResponse(f"/invoices/{invoice_id}/edit", status_code=303)


# ── Finalize / transitions ──────────────────────────────────────────────────


@router.post("/invoices/{invoice_id}/finalize", response_class=RedirectResponse)
def invoice_finalize(
    invoice_id: int,
    vies_override: bool = Form(False),
    vies_override_reason: str = Form(""),
    session: Session = Depends(get_session),
    user: User = Depends(require_editor),
):
    invoice = session.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(404)

    # VIES gate is wired up here; non-EU/non-reverse-charge invoices won't trigger it.
    gate = make_vies_gate(ViesGateOptions(
        override=vies_override,
        override_reason=vies_override_reason or None,
        override_user_id=user.id,
    )) if user.role == UserRole.admin else make_vies_gate(ViesGateOptions(
        override_user_id=user.id,
    ))

    options = FinalizeOptions(
        renderer=render_document,
        archiver=archive_document,
        vies_gate=gate,
        # Schritt 5: CRM builds the BillingOrder customer snapshot; billing
        # consumes the contract instead of reading Lead itself.
        customer_resolver=lambda lead_id: build_billing_customer(session, lead_id),
    )
    try:
        finalize_invoice(
            session, invoice_id,
            idempotency_key=str(uuid.uuid4()),
            options=options,
        )
    except (InvoiceValidationError, FinalizeError, InvoiceStateError) as exc:
        return RedirectResponse(
            f"/invoices/{invoice_id}/edit?error={str(exc).replace(' ', '+')}",
            status_code=303,
        )
    except ViesBlockedError as exc:
        return RedirectResponse(
            f"/invoices/{invoice_id}/edit?vies_blocked=1&reason={str(exc).replace(' ', '+')}",
            status_code=303,
        )
    return RedirectResponse(f"/invoices/{invoice_id}", status_code=303)


@router.post("/invoices/{invoice_id}/mark-sent", response_class=RedirectResponse)
def invoice_mark_sent(invoice_id: int, session: Session = Depends(get_session), _=Depends(require_editor)):
    try:
        mark_sent(session, invoice_id)
    except (FinalizeError, InvoiceStateError) as exc:
        raise HTTPException(409, str(exc))
    return RedirectResponse(f"/invoices/{invoice_id}", status_code=303)


@router.post("/invoices/{invoice_id}/mark-paid", response_class=RedirectResponse)
def invoice_mark_paid(invoice_id: int, session: Session = Depends(get_session), _=Depends(require_editor)):
    try:
        mark_paid(session, invoice_id)
    except (FinalizeError, InvoiceStateError) as exc:
        raise HTTPException(409, str(exc))
    return RedirectResponse(f"/invoices/{invoice_id}", status_code=303)


@router.post("/invoices/{invoice_id}/storno", response_class=RedirectResponse)
def invoice_storno(
    invoice_id: int,
    reason: str = Form(""),
    session: Session = Depends(get_session),
    _=Depends(require_editor),
):
    options = FinalizeOptions(
        renderer=render_document,
        archiver=archive_document,
    )
    try:
        storno = create_storno(session, invoice_id, reason=reason or None, options=options)
    except (FinalizeError, InvoiceStateError) as exc:
        raise HTTPException(409, str(exc))
    return RedirectResponse(f"/invoices/{storno.id}", status_code=303)


# ── PDF / XML download ──────────────────────────────────────────────────────


@router.get("/invoices/{invoice_id}/pdf")
def invoice_pdf(invoice_id: int, session: Session = Depends(get_session), _=Depends(require_login)):
    invoice = session.get(Invoice, invoice_id)
    if invoice is None or not invoice.archive_path_pdf:
        raise HTTPException(404)
    path = Path(invoice.archive_path_pdf)
    if not path.exists():
        raise HTTPException(404, "Archive file missing")
    return FileResponse(
        path=str(path),
        media_type="application/pdf",
        filename=f"Rechnung_{invoice.number}.pdf",
    )


@router.get("/invoices/{invoice_id}/xml")
def invoice_xml(invoice_id: int, session: Session = Depends(get_session), _=Depends(require_login)):
    invoice = session.get(Invoice, invoice_id)
    if invoice is None or not invoice.archive_path_xml:
        raise HTTPException(404)
    path = Path(invoice.archive_path_xml)
    if not path.exists():
        raise HTTPException(404, "Archive file missing")
    return FileResponse(
        path=str(path),
        media_type="application/xml",
        filename=f"Rechnung_{invoice.number}.xml",
    )


# ── Helpers ─────────────────────────────────────────────────────────────────


def _parse_date(s: str) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(s.strip())
    except ValueError:
        return None


def _to_decimal(s: str) -> Decimal:
    s = (s or "0").strip().replace(",", ".")
    try:
        return Decimal(s)
    except InvalidOperation:
        return Decimal(0)
