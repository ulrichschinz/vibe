"""Shared by routes/proposals.py (web UI) and services/mcp_server.py (MCP tools)."""
from datetime import datetime
from typing import Optional

from sqlmodel import Session

from app.domains.leads.models import Lead
from app.domains.proposals.models import Proposal, ProposalStatus
from services.numbering import next_proposal_number


def create_proposal(
    session: Session,
    lead_id: int,
    title: str,
    intro_text: Optional[str] = None,
    services_json: str = "[]",
    total_value: Optional[float] = None,
    duration: Optional[str] = None,
    payment_terms: Optional[str] = "50 % bei Projektstart, 50 % bei Abschluss",
    travel_costs: Optional[str] = None,
    validity_days: int = 30,
) -> Proposal:
    if not session.get(Lead, lead_id):
        raise LookupError(f"Lead {lead_id} not found")
    proposal = Proposal(
        lead_id=lead_id,
        number=next_proposal_number(session),
        title=title,
        intro_text=intro_text or None,
        services=services_json,
        total_value=total_value,
        duration=duration or None,
        payment_terms=payment_terms or None,
        travel_costs=travel_costs,
        validity_days=validity_days,
    )
    session.add(proposal)
    session.commit()
    session.refresh(proposal)
    return proposal


def mark_proposal_sent(session: Session, proposal_id: int) -> Proposal:
    proposal = session.get(Proposal, proposal_id)
    if not proposal:
        raise LookupError(f"Proposal {proposal_id} not found")
    now = datetime.utcnow()
    proposal.status = ProposalStatus.sent
    proposal.sent_at = now
    proposal.updated_at = now
    session.add(proposal)
    session.commit()
    session.refresh(proposal)
    return proposal
