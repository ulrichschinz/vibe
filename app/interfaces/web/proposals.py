"""interfaces.web.proposals — Jinja UI: proposals (Schritt 8, moved verbatim).

Move-not-rewrite from `routes/proposals.py`; only model imports point at
`app.domains.*`/`app.core.*` directly. The AI-draft/merge path still goes
through `app.domains.proposals.service` (Schritt-6 lazy `services.ai` seam
unchanged — frozen char-test seam).
"""

from copy import deepcopy

from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session
from datetime import datetime, timedelta

from database import get_session
from app.core.ai_settings import AiSettings
from app.domains.leads.service import Lead
from app.domains.proposals.service import Proposal, ProposalStatus, DEFAULT_SERVICES
from app.shared.labels import PROPOSAL_STATUS_LABELS
from app.domains.leads import service as leads_service
from app.domains.proposals import service as proposals_service
from services.pdf import generate_proposal_pdf, render_proposal_html
from services.auth import require_login, require_editor
from services.proposals import (
    create_proposal as create_proposal_svc,
    mark_proposal_sent as mark_proposal_sent_svc,
)


def _ai_active(session: Session) -> bool:
    s = session.get(AiSettings, 1)
    return bool(s and s.is_active and s.api_key)


router = APIRouter()
templates = Jinja2Templates(directory="templates")
templates.env.globals["PROPOSAL_STATUS_LABELS"] = PROPOSAL_STATUS_LABELS
templates.env.globals["ProposalStatus"] = ProposalStatus
templates.env.globals["timedelta"] = timedelta


@router.get("/leads/{lead_id}/proposals/new", response_class=HTMLResponse)
def proposal_new(
    request: Request,
    lead_id: int,
    from_plan: bool = False,
    session: Session = Depends(get_session),
    _=Depends(require_editor),
):
    lead = session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404)

    if from_plan:
        ai_settings = session.get(AiSettings, 1)
        ai_ok = bool(ai_settings and ai_settings.is_active and ai_settings.api_key)
        messages = leads_service.planning_messages(session, lead_id) if ai_ok else []
        services, prefill_intro = proposals_service.build_proposal_prefill(
            lead, messages, ai_settings, ai_ok
        )
    else:
        services = deepcopy(DEFAULT_SERVICES)
        prefill_intro = None

    return templates.TemplateResponse(
        "proposals/editor.html",
        {
            "request": request,
            "lead": lead,
            "proposal": None,
            "services": services,
            "action": f"/leads/{lead_id}/proposals",
            "ai_active": _ai_active(session),
            "prefill_intro": prefill_intro,
        },
    )


@router.post("/leads/{lead_id}/proposals", response_class=RedirectResponse)
def proposal_create(
    lead_id: int,
    title: str = Form(...),
    intro_text: str = Form(""),
    services_json: str = Form("[]"),
    total_value: str = Form(""),
    duration: str = Form(""),
    payment_terms: str = Form("50 % bei Projektstart, 50 % bei Abschluss"),
    travel_costs: str = Form(""),
    validity_days: str = Form("30"),
    session: Session = Depends(get_session),
    _=Depends(require_editor),
):
    try:
        proposal = create_proposal_svc(
            session,
            lead_id=lead_id,
            title=title,
            intro_text=intro_text,
            services_json=services_json,
            total_value=float(total_value) if total_value else None,
            duration=duration or None,
            payment_terms=payment_terms,
            travel_costs=travel_costs or None,
            validity_days=int(validity_days) if validity_days else 30,
        )
    except LookupError:
        raise HTTPException(status_code=404)
    return RedirectResponse(f"/proposals/{proposal.id}", status_code=303)


@router.get("/proposals/{proposal_id}", response_class=HTMLResponse)
def proposal_view(
    request: Request,
    proposal_id: int,
    session: Session = Depends(get_session),
    _=Depends(require_login),
):
    proposal = session.get(Proposal, proposal_id)
    if not proposal:
        raise HTTPException(status_code=404)
    lead = session.get(Lead, proposal.lead_id)
    return templates.TemplateResponse(
        "proposals/view.html",
        {
            "request": request,
            "proposal": proposal,
            "lead": lead,
        },
    )


@router.get("/proposals/{proposal_id}/edit", response_class=HTMLResponse)
def proposal_edit(
    request: Request,
    proposal_id: int,
    session: Session = Depends(get_session),
    _=Depends(require_editor),
):
    proposal = session.get(Proposal, proposal_id)
    if not proposal:
        raise HTTPException(status_code=404)
    lead = session.get(Lead, proposal.lead_id)
    return templates.TemplateResponse(
        "proposals/editor.html",
        {
            "request": request,
            "lead": lead,
            "proposal": proposal,
            "services": proposal.get_services(),
            "action": f"/proposals/{proposal_id}/update",
            "ai_active": _ai_active(session),
        },
    )


@router.post("/proposals/{proposal_id}/update", response_class=RedirectResponse)
def proposal_update(
    proposal_id: int,
    title: str = Form(...),
    intro_text: str = Form(""),
    services_json: str = Form("[]"),
    total_value: str = Form(""),
    duration: str = Form(""),
    payment_terms: str = Form(""),
    travel_costs: str = Form(""),
    validity_days: str = Form("30"),
    session: Session = Depends(get_session),
    _=Depends(require_editor),
):
    proposal = session.get(Proposal, proposal_id)
    if not proposal:
        raise HTTPException(status_code=404)
    proposal.title = title
    proposal.intro_text = intro_text or None
    proposal.services = services_json
    proposal.total_value = float(total_value) if total_value else None
    proposal.duration = duration or None
    proposal.payment_terms = payment_terms or None
    proposal.travel_costs = travel_costs or None
    proposal.validity_days = int(validity_days) if validity_days else 30
    proposal.updated_at = datetime.utcnow()
    session.add(proposal)
    session.commit()
    return RedirectResponse(f"/proposals/{proposal_id}", status_code=303)


@router.get("/proposals/{proposal_id}/pdf")
def proposal_pdf(
    proposal_id: int, session: Session = Depends(get_session), _=Depends(require_login)
):
    proposal = session.get(Proposal, proposal_id)
    if not proposal:
        raise HTTPException(status_code=404)
    lead = session.get(Lead, proposal.lead_id)
    pdf_path = generate_proposal_pdf(proposal, lead)
    proposal.pdf_path = str(pdf_path)
    session.add(proposal)
    session.commit()
    filename = f"Angebot_{proposal.number}_{lead.company or lead.name}.pdf"
    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=filename,
    )


@router.get("/proposals/{proposal_id}/document", response_class=HTMLResponse)
def proposal_document(
    proposal_id: int, session: Session = Depends(get_session), _=Depends(require_login)
):
    """Raw HTML document — used as WeasyPrint source and for live preview."""
    proposal = session.get(Proposal, proposal_id)
    if not proposal:
        raise HTTPException(status_code=404)
    lead = session.get(Lead, proposal.lead_id)
    return HTMLResponse(render_proposal_html(proposal, lead, for_print=False))


@router.post("/proposals/{proposal_id}/mark-sent", response_class=RedirectResponse)
def proposal_mark_sent(
    proposal_id: int, session: Session = Depends(get_session), _=Depends(require_editor)
):
    try:
        mark_proposal_sent_svc(session, proposal_id)
    except LookupError:
        raise HTTPException(status_code=404)
    return RedirectResponse(f"/proposals/{proposal_id}", status_code=303)
