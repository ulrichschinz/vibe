from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy import or_
from sqlmodel import Session, select
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
import hashlib
import json
import uuid

from app.core.config import get_settings
from database import get_session
from models import (
    Lead, LeadCreate, LeadRead, LeadPatch, LeadSource, ApiKey,
    Invoice, InvoiceLineItem, InvoiceStatus, InvoiceKind,
)
from services.invoicing.archive import archive_document
from services.invoicing.document import render_document
from services.invoicing.finalize import (
    FinalizeError, FinalizeOptions, InvoiceValidationError,
    create_storno, finalize_invoice, mark_paid, mark_sent,
)

router = APIRouter(prefix="/api", tags=["agent-api"])


def validate_api_key(key: str, session: Session) -> bool:
    """Pure validation. Used by both the FastAPI dependency and the MCP middleware.

    Updates last_used_at for DB-backed keys. Falls back to the legacy API_KEY env var
    so existing agents keep working.
    """
    if not key:
        return False

    key_hash = hashlib.sha256(key.encode()).hexdigest()
    db_key = session.exec(
        select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.is_active == True)
    ).first()
    if db_key:
        db_key.last_used_at = datetime.utcnow()
        session.add(db_key)
        session.commit()
        return True

    legacy = get_settings().api_key
    if legacy and key == legacy:
        return True

    return False


def verify_api_key(x_api_key: str = Header(default=""), session: Session = Depends(get_session)):
    if not x_api_key:
        raise HTTPException(status_code=401, detail="API key required")
    if not validate_api_key(x_api_key, session):
        raise HTTPException(status_code=401, detail="Invalid API key")


@router.post("/leads", response_model=LeadRead, status_code=201)
def api_create_lead(
    payload: LeadCreate,
    session: Session = Depends(get_session),
    _=Depends(verify_api_key),
):
    if not payload.name and not payload.company:
        raise HTTPException(status_code=422, detail="name oder company muss angegeben sein.")
    lead = Lead(
        name=payload.name,
        company=payload.company,
        email=payload.email,
        phone=payload.phone,
        source=payload.source,
        lead_type=payload.lead_type,
        owner_id=payload.owner_id,
        notes=payload.notes,
        tags=json.dumps(payload.tags) if payload.tags else None,
        agent_metadata=json.dumps(payload.agent_metadata) if payload.agent_metadata else None,
        snooze_until=payload.snooze_until,
        bant_budget=payload.bant_budget.value if payload.bant_budget else None,
        bant_authority=payload.bant_authority.value if payload.bant_authority else None,
        bant_need=payload.bant_need.value if payload.bant_need else None,
        bant_timing=payload.bant_timing.value if payload.bant_timing else None,
        ai_readiness=payload.ai_readiness.value if payload.ai_readiness else None,
        pain_points=payload.pain_points,
        next_action=payload.next_action,
        next_action_date=payload.next_action_date,
    )
    session.add(lead)
    session.commit()
    session.refresh(lead)
    return lead


@router.get("/leads", response_model=list[LeadRead])
def api_list_leads(
    stage: str | None = None,
    source: str | None = None,
    show_snoozed: bool = False,
    session: Session = Depends(get_session),
    _=Depends(verify_api_key),
):
    query = select(Lead)
    if stage:
        query = query.where(Lead.stage == stage)
    if source:
        query = query.where(Lead.source == source)
    if not show_snoozed:
        today = date.today()
        query = query.where(or_(Lead.snooze_until.is_(None), Lead.snooze_until <= today))
    return session.exec(query.order_by(Lead.created_at.desc())).all()


@router.get("/leads/{lead_id}", response_model=LeadRead)
def api_get_lead(
    lead_id: int,
    session: Session = Depends(get_session),
    _=Depends(verify_api_key),
):
    lead = session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@router.patch("/leads/{lead_id}", response_model=LeadRead)
def api_patch_lead(
    lead_id: int,
    payload: LeadPatch,
    session: Session = Depends(get_session),
    _=Depends(verify_api_key),
):
    lead = session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(lead, k, v)
    lead.updated_at = datetime.utcnow()
    session.add(lead)
    session.commit()
    session.refresh(lead)
    return lead


# ─────────────────────────────────────────────────────────────────────────
# Invoice REST API (X-API-Key auth, same as leads)
# ─────────────────────────────────────────────────────────────────────────


def _invoice_to_dict(inv: Invoice, lines: list[InvoiceLineItem]) -> dict:
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
        "lead_id": inv.lead_id,
        "related_invoice_id": inv.related_invoice_id,
        "subtotal_net": str(inv.subtotal_net) if inv.subtotal_net is not None else None,
        "vat_total": str(inv.vat_total) if inv.vat_total is not None else None,
        "total_gross": str(inv.total_gross) if inv.total_gross is not None else None,
        "hint_kleinunternehmer": inv.hint_kleinunternehmer,
        "hint_reverse_charge": inv.hint_reverse_charge,
        "hint_third_country": inv.hint_third_country,
        "customer": {
            "legal_name": inv.cust_legal_name,
            "company": inv.cust_company,
            "street": inv.cust_street,
            "postal_code": inv.cust_postal_code,
            "city": inv.cust_city,
            "country_code": inv.cust_country_code,
            "vat_id": inv.cust_vat_id,
        },
        "lines": [
            {
                "position": ln.position,
                "description": ln.description,
                "quantity": str(ln.quantity),
                "unit": ln.unit,
                "unit_price_net": str(ln.unit_price_net),
                "vat_rate": str(ln.vat_rate),
                "vat_code": ln.vat_code,
                "line_net": str(ln.line_net),
                "line_vat": str(ln.line_vat),
                "line_gross": str(ln.line_gross),
            }
            for ln in lines
        ],
        "hash_sha256": inv.hash_sha256,
    }


def _load_lines(inv_id: int, session: Session) -> list[InvoiceLineItem]:
    return list(session.exec(
        select(InvoiceLineItem).where(InvoiceLineItem.invoice_id == inv_id).order_by(InvoiceLineItem.position)
    ).all())


@router.post("/invoices/draft", status_code=201)
def api_create_draft(
    payload: dict,
    session: Session = Depends(get_session),
    _=Depends(verify_api_key),
):
    """Create a draft invoice. Required: leistungsdatum or lead_id (with leistungsdatum optional later)."""
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
    return _invoice_to_dict(inv, [])


@router.post("/invoices/{invoice_id}/lines", status_code=201)
def api_add_line(
    invoice_id: int,
    payload: dict,
    session: Session = Depends(get_session),
    _=Depends(verify_api_key),
):
    inv = session.get(Invoice, invoice_id)
    if inv is None:
        raise HTTPException(404, "invoice not found")
    if inv.status != InvoiceStatus.draft:
        raise HTTPException(409, "invoice is not draft")
    existing = _load_lines(inv.id, session)
    qty = Decimal(str(payload["quantity"]))
    price = Decimal(str(payload["unit_price_net"]))
    rate = Decimal(str(payload.get("vat_rate", "19")))
    line_net = (qty * price).quantize(Decimal("0.01"))
    line_vat = (line_net * rate / Decimal(100)).quantize(Decimal("0.01"))
    ln = InvoiceLineItem(
        invoice_id=inv.id,
        position=(max((l.position for l in existing), default=0)) + 1,
        description=payload["description"],
        quantity=qty,
        unit=payload.get("unit", "Std"),
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
    return {
        "position": ln.position,
        "description": ln.description,
        "quantity": str(ln.quantity),
        "unit_price_net": str(ln.unit_price_net),
    }


@router.post("/invoices/{invoice_id}/finalize")
def api_finalize(
    invoice_id: int,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
    _=Depends(verify_api_key),
):
    options = FinalizeOptions(
        renderer=render_document,
        archiver=archive_document,
    )
    try:
        inv = finalize_invoice(
            session, invoice_id,
            idempotency_key=idempotency_key or str(uuid.uuid4()),
            options=options,
        )
    except InvoiceValidationError as exc:
        raise HTTPException(422, str(exc))
    except FinalizeError as exc:
        raise HTTPException(409, str(exc))
    return _invoice_to_dict(inv, _load_lines(inv.id, session))


@router.post("/invoices/{invoice_id}/storno")
def api_storno(
    invoice_id: int,
    payload: dict | None = None,
    session: Session = Depends(get_session),
    _=Depends(verify_api_key),
):
    options = FinalizeOptions(renderer=render_document, archiver=archive_document)
    try:
        storno = create_storno(
            session, invoice_id,
            reason=(payload or {}).get("reason"),
            options=options,
        )
    except FinalizeError as exc:
        raise HTTPException(409, str(exc))
    return _invoice_to_dict(storno, _load_lines(storno.id, session))


@router.post("/invoices/{invoice_id}/mark-sent")
def api_mark_sent(invoice_id: int, session: Session = Depends(get_session), _=Depends(verify_api_key)):
    try:
        inv = mark_sent(session, invoice_id)
    except FinalizeError as exc:
        raise HTTPException(409, str(exc))
    return _invoice_to_dict(inv, _load_lines(inv.id, session))


@router.post("/invoices/{invoice_id}/mark-paid")
def api_mark_paid(invoice_id: int, session: Session = Depends(get_session), _=Depends(verify_api_key)):
    try:
        inv = mark_paid(session, invoice_id)
    except FinalizeError as exc:
        raise HTTPException(409, str(exc))
    return _invoice_to_dict(inv, _load_lines(inv.id, session))


@router.get("/invoices/{invoice_id}")
def api_get_invoice(invoice_id: int, session: Session = Depends(get_session), _=Depends(verify_api_key)):
    inv = session.get(Invoice, invoice_id)
    if inv is None:
        raise HTTPException(404)
    return _invoice_to_dict(inv, _load_lines(inv.id, session))


@router.get("/invoices")
def api_list_invoices(
    year: Optional[int] = None,
    status: Optional[str] = None,
    session: Session = Depends(get_session),
    _=Depends(verify_api_key),
):
    q = select(Invoice).order_by(Invoice.created_at.desc())
    if year is not None:
        q = q.where(Invoice.fiscal_year == year)
    if status:
        q = q.where(Invoice.status == status)
    return [_invoice_to_dict(inv, _load_lines(inv.id, session)) for inv in session.exec(q).all()]
