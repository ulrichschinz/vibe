import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlmodel import Session, select
from typing import Optional
from datetime import datetime

from database import get_session
from models import (
    AiSettings,
    Lead,
    Note,
    PlanningMessage,
    STAGE_LABELS,
    SOURCE_LABELS,
    BANT_LABELS,
    READINESS_LABELS,
)
from services.auth import require_editor, require_login
from services.ai import generate_text, chat_with_context

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
        raise HTTPException(status_code=503, detail="KI nicht konfiguriert. Bitte unter Admin → KI einrichten.")

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

def _build_qualification_block(lead: Lead) -> str:
    """Strukturierter Qualifizierungs-Auszug für Prompt und Markdown-Export."""
    def _label(val: Optional[str], labels: dict) -> str:
        if not val:
            return "—"
        return labels.get(val, val)

    lines: list[str] = []
    lines.append(
        f"BANT: Budget={_label(lead.bant_budget, BANT_LABELS)} | "
        f"Authority={_label(lead.bant_authority, BANT_LABELS)} | "
        f"Need={_label(lead.bant_need, BANT_LABELS)} | "
        f"Timing={_label(lead.bant_timing, BANT_LABELS)} "
        f"(Score: {lead.bant_score()}/100)"
    )
    lines.append(f"AI-Readiness: {_label(lead.ai_readiness, READINESS_LABELS)}")
    lines.append(f"Pain Points: {lead.pain_points or '—'}")

    if lead.next_action or lead.next_action_date:
        action = lead.next_action or "—"
        when = lead.next_action_date.strftime("%d.%m.%Y") if lead.next_action_date else "ohne Datum"
        lines.append(f"Nächster Schritt: {action} ({when})")

    if lead.snooze_until:
        flag = "aktuell pausiert bis" if lead.is_snoozed() else "Wiedervorlage am"
        lines.append(f"{flag} {lead.snooze_until.strftime('%d.%m.%Y')}")

    tags = lead.get_tags()
    if tags:
        lines.append("Tags: " + ", ".join(str(t) for t in tags))

    contact = []
    if lead.email:
        contact.append(lead.email)
    if lead.phone:
        contact.append(lead.phone)
    if contact:
        lines.append("Kontakt: " + " · ".join(contact))

    meta = lead.get_agent_metadata()
    if meta:
        try:
            meta_json = json.dumps(meta, ensure_ascii=False, indent=2)
        except Exception:
            meta_json = str(meta)
        lines.append("Agent-Metadaten (z.B. LinkedIn-Import):\n" + meta_json)

    return "\n".join(lines)


def _build_planning_system(lead: Lead, notes: list) -> str:
    notes_text = "\n".join(
        f"[{n.created_at.strftime('%d.%m.%Y %H:%M')}] {n.body}"
        for n in sorted(notes, key=lambda n: n.created_at)
    ) or "Noch keine Notizen vorhanden."

    prev = (
        f"\n\n## Zusammenfassung letzter Planungssession\n{lead.plan_text}"
        if lead.plan_text else ""
    )

    return (
        "Du bist ein erfahrener Business- und Technologie-Consultant, spezialisiert auf B2B-Projektlösungen. "
        "Du hilfst dabei, Projektideen zu diskutieren, zu schärfen und konkrete Lösungsansätze zu entwickeln.\n\n"
        f"## Lead-Kontext\n"
        f"Name: {lead.name or '—'} | Firma: {lead.company or '—'}\n"
        f"Stage: {STAGE_LABELS[lead.stage]} | Quelle: {SOURCE_LABELS[lead.source]}\n"
        f"Lead seit: {lead.created_at.strftime('%d.%m.%Y')}\n\n"
        f"## Qualifizierung & Status\n{_build_qualification_block(lead)}\n\n"
        f"## Notizen aus bisherigen Gesprächen\n{notes_text}{prev}\n\n"
        "Führe eine fokussierte Diskussion. Stelle gezielte Rückfragen. "
        "Hilf, am Ende einen klaren, umsetzbaren Projektplan zu entwickeln — "
        "mit konkreten Leistungen, Budget-Indikation und nächsten Schritten."
    )


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
    msgs = session.exec(
        select(PlanningMessage)
        .where(PlanningMessage.lead_id == lead_id)
        .order_by(PlanningMessage.created_at)
    ).all()
    return [
        {"role": m.role, "content": m.content, "created_at": m.created_at.isoformat()}
        for m in msgs
    ]


@router.post("/leads/{lead_id}/plan/chat")
def plan_chat(
    lead_id: int,
    payload: ChatRequest,
    session: Session = Depends(get_session),
    _=Depends(require_editor),
):
    lead, settings = _get_lead_and_settings(lead_id, session)
    notes = session.exec(select(Note).where(Note.lead_id == lead_id).order_by(Note.created_at)).all()
    system = _build_planning_system(lead, notes)

    existing = session.exec(
        select(PlanningMessage).where(PlanningMessage.lead_id == lead_id).order_by(PlanningMessage.created_at)
    ).all()
    messages = [{"role": m.role, "content": m.content} for m in existing]
    messages.append({"role": "user", "content": payload.message})

    try:
        reply = chat_with_context(messages, system, settings)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"KI-Fehler: {e}")

    session.add(PlanningMessage(lead_id=lead_id, role="user", content=payload.message))
    session.add(PlanningMessage(lead_id=lead_id, role="assistant", content=reply))
    session.commit()
    return {"reply": reply}


@router.post("/leads/{lead_id}/plan/summarize")
def plan_summarize(lead_id: int, session: Session = Depends(get_session), _=Depends(require_editor)):
    lead, settings = _get_lead_and_settings(lead_id, session)
    notes = session.exec(select(Note).where(Note.lead_id == lead_id).order_by(Note.created_at)).all()
    system = _build_planning_system(lead, notes)

    existing = session.exec(
        select(PlanningMessage).where(PlanningMessage.lead_id == lead_id).order_by(PlanningMessage.created_at)
    ).all()
    if not existing:
        raise HTTPException(status_code=400, detail="Kein Chat-Verlauf zum Zusammenfassen.")

    messages = [{"role": m.role, "content": m.content} for m in existing]
    messages.append({"role": "user", "content": (
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
    )})

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
    msgs = session.exec(select(PlanningMessage).where(PlanningMessage.lead_id == lead_id)).all()
    for m in msgs:
        session.delete(m)
    session.commit()
    return {"ok": True}


@router.get("/leads/{lead_id}/plan/prompt.md")
def plan_prompt_download(lead_id: int, session: Session = Depends(get_session), _=Depends(require_login)):
    lead = session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404)

    notes = session.exec(select(Note).where(Note.lead_id == lead_id).order_by(Note.created_at)).all()
    msgs = session.exec(
        select(PlanningMessage).where(PlanningMessage.lead_id == lead_id).order_by(PlanningMessage.created_at)
    ).all()

    notes_text = "\n\n".join(
        f"**{n.created_at.strftime('%d.%m.%Y %H:%M')}**\n{n.body}" for n in notes
    ) or "_Keine Notizen vorhanden._"

    chat_text = "\n\n".join(
        f"**{'Du' if m.role == 'user' else 'Assistent'}:** {m.content}" for m in msgs
    ) or "_Kein Chat-Verlauf vorhanden._"

    summary_text = lead.plan_text or "_Noch nicht gespeichert._"

    content = (
        f"# Projekt-Kontext: {lead.display_name()}\n"
        f"Exportiert: {datetime.utcnow().strftime('%d.%m.%Y')} | "
        f"Status: {STAGE_LABELS[lead.stage]} | Quelle: {SOURCE_LABELS[lead.source]}\n\n"
        f"## Qualifizierung\n\n{_build_qualification_block(lead)}\n\n"
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
