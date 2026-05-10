"""MCP server exposing lead/note/proposal operations to AI agents.

The server is mounted at /mcp by routes/mcp.py. Auth is enforced by an ASGI
middleware in routes/mcp.py — tools here trust that the caller is authenticated.
"""
from datetime import datetime, date
from typing import Any, Optional
import json
import os

from sqlalchemy import or_
from sqlmodel import Session, select

from mcp.server.fastmcp import FastMCP

from database import engine
from models import (
    DEFAULT_SERVICES,
    BantValue,
    Lead,
    LeadSource,
    LeadStage,
    Note,
    Proposal,
    ProposalStatus,
    ReadinessLevel,
)
from services.proposals import (
    create_proposal as create_proposal_svc,
    mark_proposal_sent as mark_proposal_sent_svc,
)

mcp = FastMCP(name="Vibe Lead Manager", streamable_http_path="/")


# ── serializers ─────────────────────────────────────────────────────────────

def _lead_dict(lead: Lead) -> dict:
    return {
        "id": lead.id,
        "created_at": lead.created_at.isoformat(),
        "updated_at": lead.updated_at.isoformat(),
        "name": lead.name,
        "company": lead.company,
        "email": lead.email,
        "phone": lead.phone,
        "salutation": lead.salutation,
        "source": lead.source.value if lead.source else None,
        "stage": lead.stage.value if lead.stage else None,
        "notes": lead.notes,
        "tags": lead.get_tags(),
        "agent_metadata": lead.get_agent_metadata(),
        "snooze_until": lead.snooze_until.isoformat() if lead.snooze_until else None,
        "is_snoozed": lead.is_snoozed(),
        "bant_budget": lead.bant_budget,
        "bant_authority": lead.bant_authority,
        "bant_need": lead.bant_need,
        "bant_timing": lead.bant_timing,
        "bant_score": lead.bant_score(),
        "ai_readiness": lead.ai_readiness,
        "pain_points": lead.pain_points,
        "next_action": lead.next_action,
        "next_action_date": lead.next_action_date.isoformat() if lead.next_action_date else None,
    }


def _note_dict(note: Note) -> dict:
    return {
        "id": note.id,
        "lead_id": note.lead_id,
        "body": note.body,
        "created_at": note.created_at.isoformat(),
    }


def _proposal_pdf_url(proposal_id: int) -> str:
    host = os.getenv("APP_HOST", "")
    if host:
        return f"https://{host}/proposals/{proposal_id}/pdf"
    return f"/proposals/{proposal_id}/pdf"


def _proposal_dict(p: Proposal) -> dict:
    return {
        "id": p.id,
        "number": p.number,
        "lead_id": p.lead_id,
        "title": p.title,
        "intro_text": p.intro_text,
        "services": p.get_services(),
        "total_value": p.total_value,
        "duration": p.duration,
        "payment_terms": p.payment_terms,
        "travel_costs": p.travel_costs,
        "validity_days": p.validity_days,
        "status": p.status.value if p.status else None,
        "sent_at": p.sent_at.isoformat() if p.sent_at else None,
        "created_at": p.created_at.isoformat(),
        "updated_at": p.updated_at.isoformat(),
        "pdf_url": _proposal_pdf_url(p.id) if p.id else None,
        "pdf_url_note": "Open in browser while logged in to Vibe; not fetchable with X-API-Key.",
    }


# ── lead tools ──────────────────────────────────────────────────────────────

@mcp.tool()
def create_lead(
    name: Optional[str] = None,
    company: Optional[str] = None,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    salutation: Optional[str] = None,
    source: LeadSource = LeadSource.agent,
    notes: Optional[str] = None,
    tags: Optional[list[str]] = None,
    agent_metadata: Optional[dict] = None,
    snooze_until: Optional[str] = None,
    bant_budget: Optional[BantValue] = None,
    bant_authority: Optional[BantValue] = None,
    bant_need: Optional[BantValue] = None,
    bant_timing: Optional[BantValue] = None,
    ai_readiness: Optional[ReadinessLevel] = None,
    pain_points: Optional[str] = None,
    next_action: Optional[str] = None,
    next_action_date: Optional[str] = None,
) -> dict:
    """Create a new lead. Either name or company must be provided.
    `source` defaults to "agent" so leads created via MCP are easy to filter.
    Date fields (`snooze_until`, `next_action_date`) are ISO-8601 strings (YYYY-MM-DD).
    `bant_*` accept "yes" / "open" / "no". `ai_readiness` accepts "high" / "medium" / "low"."""
    if not name and not company:
        raise ValueError("name or company must be provided")
    with Session(engine) as session:
        lead = Lead(
            name=name,
            company=company,
            email=email,
            phone=phone,
            salutation=salutation,
            source=source,
            notes=notes,
            tags=json.dumps(tags) if tags else None,
            agent_metadata=json.dumps(agent_metadata) if agent_metadata else None,
            snooze_until=date.fromisoformat(snooze_until) if snooze_until else None,
            bant_budget=bant_budget.value if bant_budget else None,
            bant_authority=bant_authority.value if bant_authority else None,
            bant_need=bant_need.value if bant_need else None,
            bant_timing=bant_timing.value if bant_timing else None,
            ai_readiness=ai_readiness.value if ai_readiness else None,
            pain_points=pain_points,
            next_action=next_action,
            next_action_date=date.fromisoformat(next_action_date) if next_action_date else None,
        )
        session.add(lead)
        session.commit()
        session.refresh(lead)
        return _lead_dict(lead)


@mcp.tool()
def list_leads(
    stage: Optional[LeadStage] = None,
    source: Optional[LeadSource] = None,
    show_snoozed: bool = False,
    limit: int = 50,
) -> list[dict]:
    """List leads, newest first. Optionally filter by stage and/or source.
    By default, leads with `snooze_until` in the future are hidden — pass
    `show_snoozed=True` to include them."""
    with Session(engine) as session:
        query = select(Lead)
        if stage:
            query = query.where(Lead.stage == stage)
        if source:
            query = query.where(Lead.source == source)
        if not show_snoozed:
            today = date.today()
            query = query.where(or_(Lead.snooze_until.is_(None), Lead.snooze_until <= today))
        query = query.order_by(Lead.created_at.desc()).limit(max(1, min(limit, 500)))
        return [_lead_dict(l) for l in session.exec(query).all()]


@mcp.tool()
def get_lead(lead_id: int) -> dict:
    """Get a single lead by ID."""
    with Session(engine) as session:
        lead = session.get(Lead, lead_id)
        if not lead:
            raise LookupError(f"Lead {lead_id} not found")
        return _lead_dict(lead)


@mcp.tool()
def update_lead(
    lead_id: int,
    name: Optional[str] = None,
    company: Optional[str] = None,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    stage: Optional[LeadStage] = None,
    notes: Optional[str] = None,
    snooze_until: Optional[str] = None,
    bant_budget: Optional[BantValue] = None,
    bant_authority: Optional[BantValue] = None,
    bant_need: Optional[BantValue] = None,
    bant_timing: Optional[BantValue] = None,
    ai_readiness: Optional[ReadinessLevel] = None,
    pain_points: Optional[str] = None,
    next_action: Optional[str] = None,
    next_action_date: Optional[str] = None,
) -> dict:
    """Patch a lead. Only provided (non-None) fields are updated.
    Pass an empty string for `snooze_until`/`next_action_date` to clear them.
    `bant_*` accept "yes" / "open" / "no"; `ai_readiness` accepts "high" / "medium" / "low"."""
    with Session(engine) as session:
        lead = session.get(Lead, lead_id)
        if not lead:
            raise LookupError(f"Lead {lead_id} not found")
        if name is not None: lead.name = name
        if company is not None: lead.company = company
        if email is not None: lead.email = email
        if phone is not None: lead.phone = phone
        if stage is not None: lead.stage = stage
        if notes is not None: lead.notes = notes
        if snooze_until is not None:
            lead.snooze_until = date.fromisoformat(snooze_until) if snooze_until else None
        if bant_budget is not None: lead.bant_budget = bant_budget.value
        if bant_authority is not None: lead.bant_authority = bant_authority.value
        if bant_need is not None: lead.bant_need = bant_need.value
        if bant_timing is not None: lead.bant_timing = bant_timing.value
        if ai_readiness is not None: lead.ai_readiness = ai_readiness.value
        if pain_points is not None: lead.pain_points = pain_points
        if next_action is not None: lead.next_action = next_action
        if next_action_date is not None:
            lead.next_action_date = date.fromisoformat(next_action_date) if next_action_date else None
        lead.updated_at = datetime.utcnow()
        session.add(lead)
        session.commit()
        session.refresh(lead)
        return _lead_dict(lead)


# ── note tools ──────────────────────────────────────────────────────────────

@mcp.tool()
def add_note(lead_id: int, body: str) -> dict:
    """Append a note to a lead."""
    body = (body or "").strip()
    if not body:
        raise ValueError("body must not be empty")
    with Session(engine) as session:
        if not session.get(Lead, lead_id):
            raise LookupError(f"Lead {lead_id} not found")
        note = Note(lead_id=lead_id, body=body)
        session.add(note)
        session.commit()
        session.refresh(note)
        return _note_dict(note)


@mcp.tool()
def list_notes(lead_id: int) -> list[dict]:
    """List notes attached to a lead, newest first."""
    with Session(engine) as session:
        if not session.get(Lead, lead_id):
            raise LookupError(f"Lead {lead_id} not found")
        notes = session.exec(
            select(Note).where(Note.lead_id == lead_id).order_by(Note.created_at.desc())
        ).all()
        return [_note_dict(n) for n in notes]


# ── proposal tools ──────────────────────────────────────────────────────────

@mcp.tool()
def create_proposal(
    lead_id: int,
    title: str,
    intro_text: Optional[str] = None,
    services: Optional[list[dict]] = None,
    total_value: Optional[float] = None,
    duration: Optional[str] = None,
    payment_terms: Optional[str] = None,
    travel_costs: Optional[str] = None,
    validity_days: int = 30,
) -> dict:
    """Create a proposal draft for a lead.
    `services` is a list of service objects; if omitted, the standard three
    (Strategie / Change / Tech) from DEFAULT_SERVICES are used.
    `duration` is a free-text label, e.g. "4–6 Wochen" or "3 Monate"."""
    services_payload = services if services is not None else DEFAULT_SERVICES
    with Session(engine) as session:
        try:
            proposal = create_proposal_svc(
                session,
                lead_id=lead_id,
                title=title,
                intro_text=intro_text,
                services_json=json.dumps(services_payload),
                total_value=total_value,
                duration=duration,
                payment_terms=payment_terms,
                travel_costs=travel_costs,
                validity_days=validity_days,
            )
        except LookupError as e:
            raise LookupError(str(e))
        return _proposal_dict(proposal)


@mcp.tool()
def list_proposals(
    lead_id: Optional[int] = None,
    status: Optional[ProposalStatus] = None,
) -> list[dict]:
    """List proposals, newest first. Optionally filter by lead and/or status."""
    with Session(engine) as session:
        query = select(Proposal)
        if lead_id is not None:
            query = query.where(Proposal.lead_id == lead_id)
        if status:
            query = query.where(Proposal.status == status)
        query = query.order_by(Proposal.created_at.desc())
        return [_proposal_dict(p) for p in session.exec(query).all()]


@mcp.tool()
def get_proposal(proposal_id: int) -> dict:
    """Get a single proposal with all fields and a pdf_url for browser download."""
    with Session(engine) as session:
        proposal = session.get(Proposal, proposal_id)
        if not proposal:
            raise LookupError(f"Proposal {proposal_id} not found")
        return _proposal_dict(proposal)


@mcp.tool()
def mark_proposal_sent(proposal_id: int) -> dict:
    """Mark a proposal as sent and stamp sent_at."""
    with Session(engine) as session:
        try:
            proposal = mark_proposal_sent_svc(session, proposal_id)
        except LookupError as e:
            raise LookupError(str(e))
        return _proposal_dict(proposal)


# ─────────────────────────────────────────────────────────────────────────
# Invoice tools
# ─────────────────────────────────────────────────────────────────────────

from datetime import date as _date
from decimal import Decimal as _D
import uuid as _uuid

from models import (
    Invoice as _Invoice,
    InvoiceLineItem as _InvoiceLineItem,
    InvoiceKind as _InvoiceKind,
    InvoiceStatus as _InvoiceStatus,
)
from services.invoicing.archive import archive_document as _archive_document
from services.invoicing.document import render_document as _render_document
from services.invoicing.finalize import (
    FinalizeError as _FinalizeError,
    FinalizeOptions as _FinalizeOptions,
    InvoiceValidationError as _InvoiceValidationError,
    create_storno as _create_storno,
    finalize_invoice as _finalize_invoice,
)


def _invoice_dict(inv: _Invoice, lines: list[_InvoiceLineItem]) -> dict:
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


@mcp.tool()
def create_invoice_draft(
    lead_id: Optional[int] = None,
    leistungsdatum: Optional[str] = None,
    title: Optional[str] = None,
    intro_text: Optional[str] = None,
    customer_reference: Optional[str] = None,
) -> dict:
    """Create a draft invoice for the given lead. ``leistungsdatum`` must be ISO-8601 (YYYY-MM-DD)."""
    with Session(engine) as s:
        inv = _Invoice(
            status=_InvoiceStatus.draft,
            kind=_InvoiceKind.invoice,
            lead_id=lead_id,
            title=title,
            intro_text=intro_text,
            customer_reference=customer_reference,
            leistungsdatum=_date.fromisoformat(leistungsdatum) if leistungsdatum else None,
        )
        s.add(inv)
        s.commit()
        s.refresh(inv)
        return _invoice_dict(inv, [])


@mcp.tool()
def add_invoice_line(
    invoice_id: int,
    description: str,
    quantity: str,
    unit_price_net: str,
    vat_rate: str = "19",
    unit: str = "Std",
) -> dict:
    """Add a line to a draft invoice. Decimals as strings to avoid float issues."""
    with Session(engine) as s:
        inv = s.get(_Invoice, invoice_id)
        if inv is None:
            raise ValueError(f"invoice {invoice_id} not found")
        if inv.status != _InvoiceStatus.draft:
            raise ValueError("invoice is not draft")
        existing = list(s.exec(select(_InvoiceLineItem).where(_InvoiceLineItem.invoice_id == invoice_id)).all())
        qty = _D(quantity)
        price = _D(unit_price_net)
        rate = _D(vat_rate)
        line_net = (qty * price).quantize(_D("0.01"))
        line_vat = (line_net * rate / _D(100)).quantize(_D("0.01"))
        ln = _InvoiceLineItem(
            invoice_id=inv.id,
            position=(max((l.position for l in existing), default=0)) + 1,
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
        s.add(ln)
        s.commit()
        s.refresh(ln)
        return {"position": ln.position, "line_net": str(ln.line_net)}


@mcp.tool()
def finalize_invoice(invoice_id: int, idempotency_key: Optional[str] = None) -> dict:
    """Finalize the draft invoice — assigns number, renders ZUGFeRD PDF/A-3 + XML, archives, locks."""
    with Session(engine) as s:
        try:
            inv = _finalize_invoice(
                s, invoice_id,
                idempotency_key=idempotency_key or str(_uuid.uuid4()),
                options=_FinalizeOptions(renderer=_render_document, archiver=_archive_document),
            )
        except (_InvoiceValidationError, _FinalizeError) as exc:
            raise ValueError(str(exc))
        lines = list(s.exec(select(_InvoiceLineItem).where(_InvoiceLineItem.invoice_id == inv.id).order_by(_InvoiceLineItem.position)).all())
        return _invoice_dict(inv, lines)


@mcp.tool()
def get_invoice(invoice_id: int) -> dict:
    with Session(engine) as s:
        inv = s.get(_Invoice, invoice_id)
        if inv is None:
            raise ValueError(f"invoice {invoice_id} not found")
        lines = list(s.exec(select(_InvoiceLineItem).where(_InvoiceLineItem.invoice_id == invoice_id).order_by(_InvoiceLineItem.position)).all())
        return _invoice_dict(inv, lines)


@mcp.tool()
def list_invoices(year: Optional[int] = None, status: Optional[str] = None) -> list[dict]:
    with Session(engine) as s:
        q = select(_Invoice).order_by(_Invoice.created_at.desc())
        if year is not None:
            q = q.where(_Invoice.fiscal_year == year)
        if status:
            q = q.where(_Invoice.status == status)
        out = []
        for inv in s.exec(q).all():
            lines = list(s.exec(select(_InvoiceLineItem).where(_InvoiceLineItem.invoice_id == inv.id).order_by(_InvoiceLineItem.position)).all())
            out.append(_invoice_dict(inv, lines))
        return out


@mcp.tool()
def storno_invoice(invoice_id: int, reason: Optional[str] = None) -> dict:
    """Create a storno for ``invoice_id``. The original is marked cancelled and remains intact."""
    with Session(engine) as s:
        try:
            storno = _create_storno(
                s, invoice_id,
                reason=reason,
                options=_FinalizeOptions(renderer=_render_document, archiver=_archive_document),
            )
        except _FinalizeError as exc:
            raise ValueError(str(exc))
        lines = list(s.exec(select(_InvoiceLineItem).where(_InvoiceLineItem.invoice_id == storno.id).order_by(_InvoiceLineItem.position)).all())
        return _invoice_dict(storno, lines)
