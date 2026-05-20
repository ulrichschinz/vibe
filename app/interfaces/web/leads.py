"""interfaces.web.leads — Jinja UI: leads/notes (Schritt 8, moved verbatim).

Move-not-rewrite from `routes/leads.py`; only the model imports point at
`app.domains.*`/`app.core.*` directly (top-level `models`-Shim-Naht
gekappt). Handler bodies unchanged.
"""

from fastapi import APIRouter, Depends, Request, Form, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select
from sqlalchemy import or_
from datetime import datetime, date, timedelta
from typing import Optional

from database import get_session
from app.core.ai_settings import AiSettings
from app.core.identity import User
from app.domains.leads.service import (
    Lead,
    Note,
    PlanningMessage,
    LeadStage,
    LeadSource,
    LeadType,
    STAGE_ORDER,
    BantValue,
    ReadinessLevel,
)
from app.domains.proposals.service import Proposal
from app.shared.labels import (
    STAGE_LABELS,
    SOURCE_LABELS,
    LEAD_TYPE_LABELS,
    PROPOSAL_STATUS_LABELS,
    BANT_LABELS,
    READINESS_LABELS,
)
from app.domains.leads import service as leads_service
from services.auth import require_login, require_editor


def _parse_date(value: str) -> Optional[date]:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _parse_enum(value: str, enum_cls):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return enum_cls(value).value
    except ValueError:
        return None


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
templates.env.globals["LeadType"] = LeadType
templates.env.globals["LEAD_TYPE_LABELS"] = LEAD_TYPE_LABELS
templates.env.globals["PROPOSAL_STATUS_LABELS"] = PROPOSAL_STATUS_LABELS
templates.env.globals["BANT_LABELS"] = BANT_LABELS
templates.env.globals["READINESS_LABELS"] = READINESS_LABELS
templates.env.globals["BantValue"] = BantValue
templates.env.globals["ReadinessLevel"] = ReadinessLevel


def _active_users(session: Session) -> list[User]:
    return list(session.exec(select(User).where(User.is_active == True).order_by(User.name)).all())


def _parse_owner_id(value: str) -> Optional[int]:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, session: Session = Depends(get_session), _=Depends(require_login)):
    overview = leads_service.dashboard_overview(session)
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            **overview,
            "ai_active": _ai_active(session),
        },
    )


@router.get("/leads", response_class=HTMLResponse)
def lead_list(
    request: Request,
    stage: Optional[str] = None,
    source: Optional[str] = None,
    lead_type: Optional[str] = None,
    owner_id: Optional[str] = None,
    show_snoozed: bool = False,
    session: Session = Depends(get_session),
    _=Depends(require_login),
):
    today = date.today()
    query = select(Lead)
    if stage:
        query = query.where(Lead.stage == stage)
    if source:
        query = query.where(Lead.source == source)
    if lead_type:
        query = query.where(Lead.lead_type == lead_type)
    owner_filter = _parse_owner_id(owner_id) if owner_id else None
    if owner_id == "none":
        query = query.where(Lead.owner_id.is_(None))
    elif owner_filter is not None:
        query = query.where(Lead.owner_id == owner_filter)
    if not show_snoozed:
        query = query.where(or_(Lead.snooze_until.is_(None), Lead.snooze_until <= today))
    leads = session.exec(query.order_by(Lead.created_at.desc())).all()
    users = _active_users(session)
    owner_map = {u.id: u for u in users}
    return templates.TemplateResponse(
        "leads/list.html",
        {
            "request": request,
            "leads": leads,
            "filter_stage": stage,
            "filter_source": source,
            "filter_lead_type": lead_type,
            "filter_owner_id": owner_id,
            "users": users,
            "owner_map": owner_map,
            "show_snoozed": show_snoozed,
            "today": today,
            "ai_active": _ai_active(session),
        },
    )


@router.get("/leads/new", response_class=HTMLResponse)
def lead_new(request: Request, session: Session = Depends(get_session), _=Depends(require_editor)):
    return templates.TemplateResponse(
        "leads/form.html",
        {
            "request": request,
            "lead": None,
            "action": "/leads",
            "users": _active_users(session),
        },
    )


MAX_LINKEDIN_PDF_BYTES = 10 * 1024 * 1024  # 10 MB


@router.get("/leads/import-linkedin", response_class=HTMLResponse)
def lead_import_linkedin_form(
    request: Request,
    session: Session = Depends(get_session),
    _=Depends(require_editor),
):
    if not _ai_active(session):
        raise HTTPException(
            status_code=400,
            detail="KI-Integration ist nicht aktiv. Bitte unter /admin/ai aktivieren.",
        )
    error = request.session.pop("linkedin_import_error", None)
    return templates.TemplateResponse(
        "leads/import_linkedin.html",
        {
            "request": request,
            "error": error,
        },
    )


@router.post("/leads/import-linkedin", response_class=HTMLResponse)
async def lead_import_linkedin(
    request: Request,
    pdf: UploadFile = File(...),
    why_good: str = Form(""),
    lead_type: str = Form("direct"),
    session: Session = Depends(get_session),
    _=Depends(require_editor),
):
    if not _ai_active(session):
        raise HTTPException(status_code=400, detail="KI-Integration ist nicht aktiv.")
    settings = session.get(AiSettings, 1)

    if pdf.content_type not in ("application/pdf", "application/x-pdf"):
        request.session["linkedin_import_error"] = "Bitte eine PDF-Datei hochladen."
        return RedirectResponse("/leads/import-linkedin", status_code=303)

    pdf_bytes = await pdf.read()
    if not pdf_bytes:
        request.session["linkedin_import_error"] = "Die Datei ist leer."
        return RedirectResponse("/leads/import-linkedin", status_code=303)
    if len(pdf_bytes) > MAX_LINKEDIN_PDF_BYTES:
        request.session["linkedin_import_error"] = (
            f"PDF ist zu groß (max. {MAX_LINKEDIN_PDF_BYTES // (1024 * 1024)} MB)."
        )
        return RedirectResponse("/leads/import-linkedin", status_code=303)

    from app.core.ai import LinkedInImportError

    current_user = getattr(request.state, "user", None)
    owner_id_default = current_user.id if current_user else None
    try:
        preview_lead = leads_service.linkedin_preview(
            pdf_bytes, why_good, lead_type, owner_id_default, settings
        )
    except LinkedInImportError as e:
        request.session["linkedin_import_error"] = f"Extraktion fehlgeschlagen: {e}"
        return RedirectResponse("/leads/import-linkedin", status_code=303)

    return templates.TemplateResponse(
        "leads/form.html",
        {
            "request": request,
            "lead": preview_lead,
            "action": "/leads",
            "preview_source": "vorschau aus linkedin",
            "users": _active_users(session),
        },
    )


@router.post("/leads", response_class=RedirectResponse)
def lead_create(
    request: Request,
    name: str = Form(""),
    company: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    salutation: str = Form(""),
    source: str = Form("manual"),
    lead_type: str = Form("direct"),
    owner_id: str = Form(""),
    notes: str = Form(""),
    snooze_until: str = Form(""),
    bant_budget: str = Form(""),
    bant_authority: str = Form(""),
    bant_need: str = Form(""),
    bant_timing: str = Form(""),
    ai_readiness: str = Form(""),
    pain_points: str = Form(""),
    next_action: str = Form(""),
    next_action_date: str = Form(""),
    session: Session = Depends(get_session),
    _=Depends(require_editor),
):
    if not name.strip() and not company.strip():
        raise HTTPException(status_code=422, detail="Name oder Firma muss angegeben sein.")
    try:
        lt = LeadType(lead_type)
    except ValueError:
        lt = LeadType.direct
    parsed_owner = _parse_owner_id(owner_id)
    if parsed_owner is None and not (owner_id or "").strip():
        current_user = getattr(request.state, "user", None)
        if current_user is not None:
            parsed_owner = current_user.id
    lead = leads_service.create_lead_web(
        session,
        name=name.strip() or None,
        company=company.strip() or None,
        email=email.strip() or None,
        phone=phone.strip() or None,
        salutation=salutation.strip() or None,
        source=LeadSource(source),
        lead_type=lt,
        owner_id=parsed_owner,
        notes=notes.strip() or None,
        snooze_until=_parse_date(snooze_until),
        bant_budget=_parse_enum(bant_budget, BantValue),
        bant_authority=_parse_enum(bant_authority, BantValue),
        bant_need=_parse_enum(bant_need, BantValue),
        bant_timing=_parse_enum(bant_timing, BantValue),
        ai_readiness=_parse_enum(ai_readiness, ReadinessLevel),
        pain_points=pain_points.strip() or None,
        next_action=next_action.strip() or None,
        next_action_date=_parse_date(next_action_date),
    )
    return RedirectResponse(f"/leads/{lead.id}", status_code=303)


@router.get("/leads/{lead_id}", response_class=HTMLResponse)
def lead_detail(
    request: Request,
    lead_id: int,
    session: Session = Depends(get_session),
    _=Depends(require_login),
):
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

    owner = session.get(User, lead.owner_id) if lead.owner_id else None

    return templates.TemplateResponse(
        "leads/detail.html",
        {
            "request": request,
            "lead": lead,
            "owner": owner,
            "proposals": proposals,
            "stages": stages,
            "notes": notes,
            "ai_active": _ai_active(session),
            "today": date.today(),
        },
    )


@router.get("/leads/{lead_id}/edit", response_class=HTMLResponse)
def lead_edit(
    request: Request,
    lead_id: int,
    session: Session = Depends(get_session),
    _=Depends(require_editor),
):
    lead = session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(
        "leads/form.html",
        {
            "request": request,
            "lead": lead,
            "action": f"/leads/{lead_id}/update",
            "users": _active_users(session),
        },
    )


@router.post("/leads/{lead_id}/update", response_class=RedirectResponse)
def lead_update(
    lead_id: int,
    name: str = Form(""),
    company: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    salutation: str = Form(""),
    source: str = Form("manual"),
    lead_type: str = Form("direct"),
    owner_id: str = Form(""),
    notes: str = Form(""),
    snooze_until: str = Form(""),
    bant_budget: str = Form(""),
    bant_authority: str = Form(""),
    bant_need: str = Form(""),
    bant_timing: str = Form(""),
    ai_readiness: str = Form(""),
    pain_points: str = Form(""),
    next_action: str = Form(""),
    next_action_date: str = Form(""),
    session: Session = Depends(get_session),
    _=Depends(require_editor),
):
    if not name.strip() and not company.strip():
        raise HTTPException(status_code=422, detail="Name oder Firma muss angegeben sein.")
    lead = session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404)
    try:
        lt = LeadType(lead_type)
    except ValueError:
        lt = LeadType.direct
    lead.name = name.strip() or None
    lead.company = company.strip() or None
    lead.email = email.strip() or None
    lead.phone = phone.strip() or None
    lead.salutation = salutation.strip() or None
    lead.source = LeadSource(source)
    lead.lead_type = lt
    lead.owner_id = _parse_owner_id(owner_id)
    lead.notes = notes.strip() or None
    lead.snooze_until = _parse_date(snooze_until)
    lead.bant_budget = _parse_enum(bant_budget, BantValue)
    lead.bant_authority = _parse_enum(bant_authority, BantValue)
    lead.bant_need = _parse_enum(bant_need, BantValue)
    lead.bant_timing = _parse_enum(bant_timing, BantValue)
    lead.ai_readiness = _parse_enum(ai_readiness, ReadinessLevel)
    lead.pain_points = pain_points.strip() or None
    lead.next_action = next_action.strip() or None
    lead.next_action_date = _parse_date(next_action_date)
    lead.updated_at = datetime.utcnow()
    session.add(lead)
    session.commit()
    return RedirectResponse(f"/leads/{lead_id}", status_code=303)


@router.post("/leads/{lead_id}/snooze", response_class=RedirectResponse)
def lead_snooze(
    lead_id: int,
    days: int = Form(...),
    session: Session = Depends(get_session),
    _=Depends(require_editor),
):
    lead = session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404)
    if days <= 0:
        lead.snooze_until = None
    else:
        lead.snooze_until = date.today() + timedelta(days=days)
    lead.updated_at = datetime.utcnow()
    session.add(lead)
    session.commit()
    return RedirectResponse(f"/leads/{lead_id}#qualifizierung", status_code=303)


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
    for msg in session.exec(
        select(PlanningMessage).where(PlanningMessage.lead_id == lead_id)
    ).all():
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
    leads_service.create_note_web(session, lead_id, body.strip())
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
