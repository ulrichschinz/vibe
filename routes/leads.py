from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from datetime import datetime
from typing import Optional
import json

from database import get_session
from models import Lead, Proposal, Note, PlanningMessage, AiSettings, LeadStage, LeadSource, STAGE_LABELS, SOURCE_LABELS, STAGE_ORDER, PROPOSAL_STATUS_LABELS
from services.auth import require_login, require_editor


def _ai_active(session: Session) -> bool:
    s = session.get(AiSettings, 1)
    return bool(s and s.is_active and s.api_key)

router = APIRouter()
templates = Jinja2Templates(directory="templates")
templates.env.globals["STAGE_LABELS"] = STAGE_LABELS
templates.env.globals["SOURCE_LABELS"] = SOURCE_LABELS
templates.env.globals["STAGE_ORDER"] = STAGE_ORDER
templates.env.globals["LeadStage"] = LeadStage
templates.env.globals["LeadSource"] = LeadSource
templates.env.globals["PROPOSAL_STATUS_LABELS"] = PROPOSAL_STATUS_LABELS


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, session: Session = Depends(get_session), _=Depends(require_login)):
    leads = session.exec(select(Lead).order_by(Lead.created_at.desc())).all()
    by_stage = {s: sum(1 for l in leads if l.stage == s) for s in LeadStage}
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "leads": leads,
        "by_stage": by_stage,
        "total": len(leads),
    })


@router.get("/leads", response_class=HTMLResponse)
def lead_list(
    request: Request,
    stage: Optional[str] = None,
    source: Optional[str] = None,
    session: Session = Depends(get_session),
    _=Depends(require_login),
):
    query = select(Lead)
    if stage:
        query = query.where(Lead.stage == stage)
    if source:
        query = query.where(Lead.source == source)
    leads = session.exec(query.order_by(Lead.created_at.desc())).all()
    return templates.TemplateResponse("leads/list.html", {
        "request": request,
        "leads": leads,
        "filter_stage": stage,
        "filter_source": source,
    })


@router.get("/leads/new", response_class=HTMLResponse)
def lead_new(request: Request, _=Depends(require_editor)):
    return templates.TemplateResponse("leads/form.html", {
        "request": request,
        "lead": None,
        "action": "/leads",
    })


@router.post("/leads", response_class=RedirectResponse)
def lead_create(
    request: Request,
    name: str = Form(""),
    company: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    salutation: str = Form(""),
    source: str = Form("manual"),
    notes: str = Form(""),
    session: Session = Depends(get_session),
    _=Depends(require_editor),
):
    if not name.strip() and not company.strip():
        raise HTTPException(status_code=422, detail="Name oder Firma muss angegeben sein.")
    lead = Lead(
        name=name.strip() or None,
        company=company.strip() or None,
        email=email.strip() or None,
        phone=phone.strip() or None,
        salutation=salutation.strip() or None,
        source=LeadSource(source),
        notes=notes.strip() or None,
    )
    session.add(lead)
    session.commit()
    session.refresh(lead)
    return RedirectResponse(f"/leads/{lead.id}", status_code=303)


@router.get("/leads/{lead_id}", response_class=HTMLResponse)
def lead_detail(request: Request, lead_id: int, session: Session = Depends(get_session), _=Depends(require_login)):
    lead = session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404)
    proposals = session.exec(
        select(Proposal).where(Proposal.lead_id == lead_id).order_by(Proposal.created_at.desc())
    ).all()

    nums = {
        LeadStage.new: "01",
        LeadStage.contacted: "02",
        LeadStage.proposal_sent: "03",
        LeadStage.negotiating: "04",
        LeadStage.won: "05",
        LeadStage.lost: "—",
    }
    current_idx = STAGE_ORDER.index(lead.stage)
    stages = [
        {
            "key": s.value,
            "label": STAGE_LABELS[s],
            "num": nums[s],
            "is_active": s == lead.stage,
            "is_done": STAGE_ORDER.index(s) < current_idx,
        }
        for s in STAGE_ORDER
    ]

    notes = session.exec(
        select(Note).where(Note.lead_id == lead_id).order_by(Note.created_at.desc())
    ).all()

    return templates.TemplateResponse("leads/detail.html", {
        "request": request,
        "lead": lead,
        "proposals": proposals,
        "stages": stages,
        "notes": notes,
        "ai_active": _ai_active(session),
    })


@router.get("/leads/{lead_id}/edit", response_class=HTMLResponse)
def lead_edit(request: Request, lead_id: int, session: Session = Depends(get_session), _=Depends(require_editor)):
    lead = session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("leads/form.html", {
        "request": request,
        "lead": lead,
        "action": f"/leads/{lead_id}/update",
    })


@router.post("/leads/{lead_id}/update", response_class=RedirectResponse)
def lead_update(
    lead_id: int,
    name: str = Form(""),
    company: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    salutation: str = Form(""),
    source: str = Form("manual"),
    notes: str = Form(""),
    session: Session = Depends(get_session),
    _=Depends(require_editor),
):
    if not name.strip() and not company.strip():
        raise HTTPException(status_code=422, detail="Name oder Firma muss angegeben sein.")
    lead = session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404)
    lead.name = name.strip() or None
    lead.company = company.strip() or None
    lead.email = email.strip() or None
    lead.phone = phone.strip() or None
    lead.salutation = salutation.strip() or None
    lead.source = LeadSource(source)
    lead.notes = notes.strip() or None
    lead.updated_at = datetime.utcnow()
    session.add(lead)
    session.commit()
    return RedirectResponse(f"/leads/{lead_id}", status_code=303)


@router.post("/leads/{lead_id}/stage")
def lead_stage_change(
    lead_id: int,
    stage: str = Form(...),
    session: Session = Depends(get_session),
    _=Depends(require_editor),
):
    lead = session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404)
    lead.stage = LeadStage(stage)
    lead.updated_at = datetime.utcnow()
    session.add(lead)
    session.commit()
    return RedirectResponse(f"/leads/{lead_id}", status_code=303)


@router.post("/leads/{lead_id}/delete", response_class=RedirectResponse)
def lead_delete(lead_id: int, session: Session = Depends(get_session), _=Depends(require_editor)):
    lead = session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404)
    for note in session.exec(select(Note).where(Note.lead_id == lead_id)).all():
        session.delete(note)
    for msg in session.exec(select(PlanningMessage).where(PlanningMessage.lead_id == lead_id)).all():
        session.delete(msg)
    session.delete(lead)
    session.commit()
    return RedirectResponse("/leads", status_code=303)


@router.post("/leads/{lead_id}/notes", response_class=RedirectResponse)
def note_create(
    lead_id: int,
    body: str = Form(...),
    session: Session = Depends(get_session),
    _=Depends(require_editor),
):
    if not body.strip():
        return RedirectResponse(f"/leads/{lead_id}", status_code=303)
    note = Note(lead_id=lead_id, body=body.strip())
    session.add(note)
    session.commit()
    return RedirectResponse(f"/leads/{lead_id}#notizen", status_code=303)


@router.post("/notes/{note_id}/delete", response_class=RedirectResponse)
def note_delete(note_id: int, session: Session = Depends(get_session), _=Depends(require_editor)):
    note = session.get(Note, note_id)
    if not note:
        raise HTTPException(status_code=404)
    lead_id = note.lead_id
    session.delete(note)
    session.commit()
    return RedirectResponse(f"/leads/{lead_id}#notizen", status_code=303)


@router.post("/leads/{lead_id}/plan", response_class=RedirectResponse)
def plan_update(
    lead_id: int,
    plan_text: str = Form(""),
    session: Session = Depends(get_session),
    _=Depends(require_editor),
):
    lead = session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404)
    lead.plan_text = plan_text.strip() or None
    lead.updated_at = datetime.utcnow()
    session.add(lead)
    session.commit()
    return RedirectResponse(f"/leads/{lead_id}#planung", status_code=303)
