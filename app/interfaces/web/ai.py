"""interfaces.web.ai — planning-chat + one-shot AI endpoints (Schritt 8,
moved verbatim from `routes/ai.py`).

Model imports point at `app.core.*`/`app.domains.*` directly; the AI
adapter call resolves to `app.core.ai` directly (no frozen characterization
test patches `services.ai` for the `/ai` router — the Schritt-6 lazy
`services.ai` seam is only the proposals/leads-service path and stays
untouched there).
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlmodel import Session, select
from typing import Optional
from datetime import datetime

from database import get_session
from app.core.ai_settings import AiSettings
from app.domains.leads.models import Lead, Note
from app.shared.labels import (
    STAGE_LABELS,
    SOURCE_LABELS,
)
from app.domains.leads import service as leads_service
from services.auth import require_editor, require_login
from app.core.ai import generate_text, chat_with_context

router = APIRouter(prefix="/ai")


# ── Existing: one-shot text generation ──────────────────────────────────────


class GenerateRequest(BaseModel):
    field: str
    notes: str = ""
    lead_name: Optional[str] = None
    lead_company: Optional[str] = None
    proposal_title: Optional[str] = None
    service_title: Optional[str] = None


@router.post("/generate")
def ai_generate(
    payload: GenerateRequest,
    session: Session = Depends(get_session),
    _=Depends(require_editor),
):
    settings = session.get(AiSettings, 1)
    if not settings or not settings.is_active or not settings.api_key:
        raise HTTPException(
            status_code=503, detail="KI nicht konfiguriert. Bitte unter Admin → KI einrichten."
        )

    context = {
        "lead_name": payload.lead_name,
        "lead_company": payload.lead_company,
        "proposal_title": payload.proposal_title,
        "service_title": payload.service_title,
    }

    try:
        text = generate_text(payload.field, payload.notes, context, settings)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"KI-Fehler: {e}")

    return {"text": text}


# ── Planning chat ────────────────────────────────────────────────────────────
# The qualification/system-prompt builders and the PlanningMessage history
# accessors moved verbatim to app.domains.leads.service (Schritt 6 — planning
# belongs to the Lead). This router keeps only HTTP + the AI transport call.


def _get_lead_and_settings(lead_id: int, session: Session):
    settings = session.get(AiSettings, 1)
    if not settings or not settings.is_active or not settings.api_key:
        raise HTTPException(status_code=503, detail="KI nicht konfiguriert.")
    lead = session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404)
    return lead, settings


class ChatRequest(BaseModel):
    message: str


@router.get("/leads/{lead_id}/plan/messages")
def plan_messages(lead_id: int, session: Session = Depends(get_session), _=Depends(require_login)):
    msgs = leads_service.planning_messages(session, lead_id)
    return [
        {"role": m.role, "content": m.content, "created_at": m.created_at.isoformat()} for m in msgs
    ]


@router.post("/leads/{lead_id}/plan/chat")
def plan_chat(
    lead_id: int,
    payload: ChatRequest,
    session: Session = Depends(get_session),
    _=Depends(require_editor),
):
    lead, settings = _get_lead_and_settings(lead_id, session)
    notes = session.exec(
        select(Note).where(Note.lead_id == lead_id).order_by(Note.created_at)
    ).all()
    system = leads_service.build_planning_system(lead, notes)

    existing = leads_service.planning_messages(session, lead_id)
    messages = [{"role": m.role, "content": m.content} for m in existing]
    messages.append({"role": "user", "content": payload.message})

    try:
        reply = chat_with_context(messages, system, settings)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"KI-Fehler: {e}")

    leads_service.record_planning_exchange(session, lead_id, payload.message, reply)
    return {"reply": reply}


@router.post("/leads/{lead_id}/plan/summarize")
def plan_summarize(
    lead_id: int, session: Session = Depends(get_session), _=Depends(require_editor)
):
    lead, settings = _get_lead_and_settings(lead_id, session)
    notes = session.exec(
        select(Note).where(Note.lead_id == lead_id).order_by(Note.created_at)
    ).all()
    system = leads_service.build_planning_system(lead, notes)

    existing = leads_service.planning_messages(session, lead_id)
    if not existing:
        raise HTTPException(status_code=400, detail="Kein Chat-Verlauf zum Zusammenfassen.")

    messages = [{"role": m.role, "content": m.content} for m in existing]
    messages.append(
        {
            "role": "user",
            "content": (
                "Erstelle jetzt eine umfangreiche, vollständige Zusammenfassung dieser Planungsdiskussion. "
                "Sie dient als Kontext für zukünftige Sessions und muss lückenlos sein.\n\n"
                "Struktur (Markdown):\n"
                "## Projektidee & Hintergrund\n"
                "## Diskutierte Lösung\n"
                "## Konkrete Leistungen & Scope\n"
                "## Budget-Indikation & Timeline\n"
                "## Offene Fragen & Risiken\n"
                "## Nächste Schritte\n\n"
                "Sei ausführlich. Kürze nichts ab. Wissensverlust zwischen Sessions ist teuer."
            ),
        }
    )

    try:
        summary = chat_with_context(messages, system, settings)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"KI-Fehler: {e}")

    lead.plan_text = summary
    lead.updated_at = datetime.utcnow()
    session.add(lead)
    session.commit()
    return {"summary": summary}


@router.post("/leads/{lead_id}/plan/clear")
def plan_clear(lead_id: int, session: Session = Depends(get_session), _=Depends(require_editor)):
    leads_service.clear_planning_messages(session, lead_id)
    return {"ok": True}


@router.get("/leads/{lead_id}/plan/prompt.md")
def plan_prompt_download(
    lead_id: int, session: Session = Depends(get_session), _=Depends(require_login)
):
    lead = session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404)

    notes = session.exec(
        select(Note).where(Note.lead_id == lead_id).order_by(Note.created_at)
    ).all()
    msgs = leads_service.planning_messages(session, lead_id)

    notes_text = (
        "\n\n".join(f"**{n.created_at.strftime('%d.%m.%Y %H:%M')}**\n{n.body}" for n in notes)
        or "_Keine Notizen vorhanden._"
    )

    chat_text = (
        "\n\n".join(f"**{'Du' if m.role == 'user' else 'Assistent'}:** {m.content}" for m in msgs)
        or "_Kein Chat-Verlauf vorhanden._"
    )

    summary_text = lead.plan_text or "_Noch nicht gespeichert._"

    content = (
        f"# Projekt-Kontext: {lead.display_name()}\n"
        f"Exportiert: {datetime.utcnow().strftime('%d.%m.%Y')} | "
        f"Status: {STAGE_LABELS[lead.stage]} | Quelle: {SOURCE_LABELS[lead.source]}\n\n"
        f"## Qualifizierung\n\n{leads_service.build_qualification_block(lead)}\n\n"
        f"## Notizen ({len(notes)} Einträge)\n\n{notes_text}\n\n"
        f"## Planungszusammenfassung\n\n{summary_text}\n\n"
        f"## Vollständiger Planungs-Chat\n\n{chat_text}\n\n"
        "---\n"
        "*Exportiert aus Vibe CRM — kann direkt als Kontext in Claude Code / claude.ai verwendet werden.*\n"
    )

    safe_name = lead.display_name().replace(" ", "_").replace("/", "_").replace("\\", "_")
    filename = f"Projekt_{safe_name}.md"
    return Response(
        content=content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
