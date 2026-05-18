"""MCP server exposing lead/note/proposal operations to AI agents.

The server is mounted at /mcp by routes/mcp.py. Auth is enforced by an ASGI
middleware in routes/mcp.py — tools here trust that the caller is authenticated.
"""
from typing import Optional
import json

from sqlmodel import Session, select

from mcp.server.fastmcp import FastMCP

from database import engine
from app.domains.leads import service as leads_service
from app.domains.proposals import service as proposals_service
from services.proposals import (
    create_proposal as create_proposal_svc,
    mark_proposal_sent as mark_proposal_sent_svc,
)

mcp = FastMCP(name="Vibe Lead Manager", streamable_http_path="/")

# Schritt 7 (MCP-Entdopplung): the Lead/Note/Proposal tools below are thin —
# they own only the Session(engine) lifecycle (the caller-owned session of the
# Scaffold-/Service-Vertrag) and delegate construction/query/serialization to
# the owning domain service (app/domains/{leads,proposals}/service.py). The
# previously duplicated `Lead(...)`/`Note(...)` construction and the
# `_lead_dict`/`_note_dict`/`_proposal_dict` serializers moved there
# byte-for-byte (ARCHITECTURE.md Struktur-Schuld 4). `create_proposal`/
# `mark_proposal_sent` keep calling the clean shared, untouched
# `services/proposals.py` directly (it was never the duplicate) and only
# attach `proposals_service.serialize_proposal`. The enums used in the
# tool signatures are referenced via the service modules so this interface
# does not import `domains/*/models` (import-linter rule, this step). Invoice
# tools are unchanged — finalize/storno already route Billing through the
# `BillingOrder` contract (Schritt 5); the billing-MCP facade + the web/api
# interface edge rows + the `models`-shim death are Schritt 8.
LeadSource = leads_service.LeadSource
LeadStage = leads_service.LeadStage
BantValue = leads_service.BantValue
ReadinessLevel = leads_service.ReadinessLevel
ProposalStatus = proposals_service.ProposalStatus
DEFAULT_SERVICES = proposals_service.DEFAULT_SERVICES


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
    with Session(engine) as session:
        return leads_service.mcp_create_lead(
            session,
            name=name,
            company=company,
            email=email,
            phone=phone,
            salutation=salutation,
            source=source,
            notes=notes,
            tags=tags,
            agent_metadata=agent_metadata,
            snooze_until=snooze_until,
            bant_budget=bant_budget,
            bant_authority=bant_authority,
            bant_need=bant_need,
            bant_timing=bant_timing,
            ai_readiness=ai_readiness,
            pain_points=pain_points,
            next_action=next_action,
            next_action_date=next_action_date,
        )


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
        return leads_service.mcp_list_leads(
            session, stage=stage, source=source, show_snoozed=show_snoozed, limit=limit
        )


@mcp.tool()
def get_lead(lead_id: int) -> dict:
    """Get a single lead by ID."""
    with Session(engine) as session:
        return leads_service.mcp_get_lead(session, lead_id)


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
        return leads_service.mcp_update_lead(
            session,
            lead_id,
            name=name,
            company=company,
            email=email,
            phone=phone,
            stage=stage,
            notes=notes,
            snooze_until=snooze_until,
            bant_budget=bant_budget,
            bant_authority=bant_authority,
            bant_need=bant_need,
            bant_timing=bant_timing,
            ai_readiness=ai_readiness,
            pain_points=pain_points,
            next_action=next_action,
            next_action_date=next_action_date,
        )


# ── note tools ──────────────────────────────────────────────────────────────

@mcp.tool()
def add_note(lead_id: int, body: str) -> dict:
    """Append a note to a lead."""
    with Session(engine) as session:
        return leads_service.mcp_add_note(session, lead_id, body)


@mcp.tool()
def list_notes(lead_id: int) -> list[dict]:
    """List notes attached to a lead, newest first."""
    with Session(engine) as session:
        return leads_service.mcp_list_notes(session, lead_id)


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
        return proposals_service.serialize_proposal(proposal)


@mcp.tool()
def list_proposals(
    lead_id: Optional[int] = None,
    status: Optional[ProposalStatus] = None,
) -> list[dict]:
    """List proposals, newest first. Optionally filter by lead and/or status."""
    with Session(engine) as session:
        return proposals_service.list_proposals(session, lead_id=lead_id, status=status)


@mcp.tool()
def get_proposal(proposal_id: int) -> dict:
    """Get a single proposal with all fields and a pdf_url for browser download."""
    with Session(engine) as session:
        return proposals_service.get_proposal(session, proposal_id)


@mcp.tool()
def mark_proposal_sent(proposal_id: int) -> dict:
    """Mark a proposal as sent and stamp sent_at."""
    with Session(engine) as session:
        try:
            proposal = mark_proposal_sent_svc(session, proposal_id)
        except LookupError as e:
            raise LookupError(str(e))
        return proposals_service.serialize_proposal(proposal)


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
from app.domains.leads.billing_export import (
    build_billing_customer as _build_billing_customer,
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
                options=_FinalizeOptions(
                    renderer=_render_document,
                    archiver=_archive_document,
                    # Schritt 5: CRM builds the BillingOrder customer snapshot.
                    customer_resolver=lambda lead_id: _build_billing_customer(s, lead_id),
                ),
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
