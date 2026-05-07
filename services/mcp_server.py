"""MCP server exposing lead/note/proposal operations to AI agents.

The server is mounted at /mcp by routes/mcp.py. Auth is enforced by an ASGI
middleware in routes/mcp.py — tools here trust that the caller is authenticated.
"""
from datetime import datetime
from typing import Any, Optional
import json
import os

from sqlmodel import Session, select

from mcp.server.fastmcp import FastMCP

from database import engine
from models import (
    DEFAULT_SERVICES,
    Lead,
    LeadSource,
    LeadStage,
    Note,
    Proposal,
    ProposalStatus,
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
        "duration_months": p.duration_months,
        "payment_terms": p.payment_terms,
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
) -> dict:
    """Create a new lead. Either name or company must be provided.
    `source` defaults to "agent" so leads created via MCP are easy to filter."""
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
        )
        session.add(lead)
        session.commit()
        session.refresh(lead)
        return _lead_dict(lead)


@mcp.tool()
def list_leads(
    stage: Optional[LeadStage] = None,
    source: Optional[LeadSource] = None,
    limit: int = 50,
) -> list[dict]:
    """List leads, newest first. Optionally filter by stage and/or source."""
    with Session(engine) as session:
        query = select(Lead)
        if stage:
            query = query.where(Lead.stage == stage)
        if source:
            query = query.where(Lead.source == source)
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
) -> dict:
    """Patch a lead. Only provided fields are updated."""
    with Session(engine) as session:
        lead = session.get(Lead, lead_id)
        if not lead:
            raise LookupError(f"Lead {lead_id} not found")
        for field, value in {
            "name": name,
            "company": company,
            "email": email,
            "phone": phone,
            "stage": stage,
            "notes": notes,
        }.items():
            if value is not None:
                setattr(lead, field, value)
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
    duration_months: Optional[int] = None,
    payment_terms: Optional[str] = None,
    validity_days: int = 30,
) -> dict:
    """Create a proposal draft for a lead.
    `services` is a list of service objects; if omitted, the standard three
    (Strategie / Change / Tech) from DEFAULT_SERVICES are used."""
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
                duration_months=duration_months,
                payment_terms=payment_terms,
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
