"""leads domain — service layer (Scaling-roadmap Schritt 6).

Pure business logic pulled out of ``routes/leads.py`` and ``routes/ai.py``:
dashboard aggregation, LinkedIn-import orchestration, and the planning-chat
history + prompt builders (planning belongs to the Lead, not the Proposal —
roadmap owner table). No FastAPI import; the ``Session`` is passed in by the
caller (Scaffold-Vertrag). The AI *adapter* (Anthropic client, prompts,
``<json>`` parsing) lives in ``app.core.ai``.

"Keine Verhaltensänderung": every function below is the verbatim original
(only type annotations added for the ``app.*``-strict mypy gate). The
LinkedIn ``_parse_enum`` helper is a verbatim copy of the route-local one
(the route keeps its own copy for lead create/update — Schritt 6 touches the
import flow only).

Contract-conformant imports: own domain (``app.domains.leads.models``) +
``app.shared.*`` only — never another ``app.domains.*``. ``linkedin_preview``
resolves ``extract_lead_from_pdf`` through the legacy ``services.linkedin_import``
shim (re-export over ``app.core.ai``) so the frozen Schritt-0.5
characterization test — which ``monkeypatch.setattr`` that module — keeps
intercepting through the same module object until it retires (Schritt 7).
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import or_
from sqlmodel import Session, select

from app.domains.leads.models import (
    BantValue,
    Lead,
    LeadSource,
    LeadStage,
    LeadType,
    Note,
    PlanningMessage,
    ReadinessLevel,
)
from app.shared.labels import (
    BANT_LABELS,
    READINESS_LABELS,
    SOURCE_LABELS,
    STAGE_LABELS,
)


# ── Dashboard aggregation ──────────────────────────────────────────────────


def dashboard_overview(session: Session) -> dict[str, Any]:
    today = date.today()
    all_leads = session.exec(
        select(Lead).order_by(Lead.created_at.desc())  # type: ignore[attr-defined]
    ).all()
    active_leads = [ld for ld in all_leads if not ld.is_snoozed(today)]
    snoozed_count = len(all_leads) - len(active_leads)
    by_stage = {s: sum(1 for ld in active_leads if ld.stage == s) for s in LeadStage}
    return {
        "leads": active_leads,
        "by_stage": by_stage,
        "total": len(active_leads),
        "snoozed_count": snoozed_count,
    }


# ── LinkedIn-import orchestration (preview-only: never persists a Lead) ─────


def _parse_enum(value: Any, enum_cls: Any) -> Any:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return enum_cls(value).value
    except ValueError:
        return None


def _compose_linkedin_notes(
    why_good: str, data: dict, readiness_label: Optional[str]
) -> Optional[str]:
    """Build the structured notes block from the sales-extraction fields."""
    parts: list[str] = []
    if why_good.strip():
        parts.append("Warum dieser Lead (Vertrieb):\n" + why_good.strip())

    sections = [
        ("Firma", data.get("company_summary")),
        ("Buying Signals", data.get("buying_signals")),
        ("Decision-Role", data.get("decision_role")),
        ("Fit für Agentic Reach", data.get("agentic_reach_fit")),
        (
            f"AI-Readiness: {readiness_label}" if readiness_label else "AI-Readiness",
            data.get("ai_readiness_reason"),
        ),
        ("Karriere-Highlights", data.get("career_highlights")),
    ]
    body_parts = [
        f"## {header}\n{body.strip()}" for header, body in sections if body and body.strip()
    ]
    if body_parts:
        parts.append("\n\n".join(body_parts))

    return "\n\n---\n\n".join(parts) or None


def linkedin_preview(
    pdf_bytes: bytes,
    why_good: str,
    lead_type: str,
    owner_id_default: Optional[int],
    settings: Any,
) -> Lead:
    """Extract a LinkedIn PDF and build an *unpersisted* preview ``Lead``.

    Raises ``LinkedInImportError`` (via the legacy shim) on extraction
    failure — the route maps that to a redirect. Nothing is written here.
    """
    # Resolve through the legacy shim so the frozen monkeypatch seam
    # (services.linkedin_import.extract_lead_from_pdf) keeps intercepting.
    from services import linkedin_import as _li

    data = _li.extract_lead_from_pdf(pdf_bytes, why_good, settings)

    ai_readiness = _parse_enum(data.get("ai_readiness_level"), ReadinessLevel)
    bant_authority = _parse_enum(data.get("bant_authority"), BantValue)
    bant_need = _parse_enum(data.get("bant_need"), BantValue)

    readiness_label = READINESS_LABELS[ReadinessLevel(ai_readiness)] if ai_readiness else None
    notes = _compose_linkedin_notes(why_good, data, readiness_label)

    try:
        lt = LeadType(lead_type)
    except ValueError:
        lt = LeadType.direct

    return Lead(
        name=data.get("name") or None,
        company=data.get("company") or None,
        salutation=data.get("salutation") or None,
        email=data.get("email") or None,
        phone=data.get("phone") or None,
        source=LeadSource.linkedin,
        lead_type=lt,
        owner_id=owner_id_default,
        notes=notes,
        pain_points=data.get("pain_points") or None,
        ai_readiness=ai_readiness,
        bant_authority=bant_authority,
        bant_need=bant_need,
    )


# ── Planning chat — history + prompt builders (planning belongs to Lead) ───


def build_qualification_block(lead: Lead) -> str:
    """Strukturierter Qualifizierungs-Auszug für Prompt und Markdown-Export."""

    def _label(val: Optional[str], labels: dict) -> str:
        if not val:
            return "—"
        return labels.get(val, val)  # type: ignore[no-any-return]

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


def build_planning_system(lead: Lead, notes: list) -> str:
    notes_text = (
        "\n".join(
            f"[{n.created_at.strftime('%d.%m.%Y %H:%M')}] {n.body}"
            for n in sorted(notes, key=lambda n: n.created_at)
        )
        or "Noch keine Notizen vorhanden."
    )

    prev = (
        f"\n\n## Zusammenfassung letzter Planungssession\n{lead.plan_text}"
        if lead.plan_text
        else ""
    )

    return (
        "Du bist ein erfahrener Business- und Technologie-Consultant, spezialisiert auf B2B-Projektlösungen. "
        "Du hilfst dabei, Projektideen zu diskutieren, zu schärfen und konkrete Lösungsansätze zu entwickeln.\n\n"
        f"## Lead-Kontext\n"
        f"Name: {lead.name or '—'} | Firma: {lead.company or '—'}\n"
        f"Stage: {STAGE_LABELS[lead.stage]} | Quelle: {SOURCE_LABELS[lead.source]}\n"
        f"Lead seit: {lead.created_at.strftime('%d.%m.%Y')}\n\n"
        f"## Qualifizierung & Status\n{build_qualification_block(lead)}\n\n"
        f"## Notizen aus bisherigen Gesprächen\n{notes_text}{prev}\n\n"
        "Führe eine fokussierte Diskussion. Stelle gezielte Rückfragen. "
        "Hilf, am Ende einen klaren, umsetzbaren Projektplan zu entwickeln — "
        "mit konkreten Leistungen, Budget-Indikation und nächsten Schritten."
    )


def planning_messages(session: Session, lead_id: int) -> list[PlanningMessage]:
    return list(
        session.exec(
            select(PlanningMessage)
            .where(PlanningMessage.lead_id == lead_id)
            .order_by(PlanningMessage.created_at)  # type: ignore[arg-type]
        ).all()
    )


def record_planning_exchange(session: Session, lead_id: int, user_message: str, reply: str) -> None:
    session.add(PlanningMessage(lead_id=lead_id, role="user", content=user_message))
    session.add(PlanningMessage(lead_id=lead_id, role="assistant", content=reply))
    session.commit()


def clear_planning_messages(session: Session, lead_id: int) -> None:
    msgs = session.exec(select(PlanningMessage).where(PlanningMessage.lead_id == lead_id)).all()
    for m in msgs:
        session.delete(m)
    session.commit()


# ── MCP-facing Lead/Note operations (Schritt 7: MCP-Entdopplung) ───────────
#
# Verbatim move of the duplicated construction/query/serialization that lived
# in ``services/mcp_server.py``'s create_lead/update_lead/list_leads/get_lead/
# add_note/list_notes tools (ARCHITECTURE.md Struktur-Schuld 4). "Keine
# Verhaltensänderung": the bodies are byte-for-byte the originals — only the
# ``with Session(engine)`` block is replaced by the caller-supplied
# ``session`` (Scaffold-/Service-Vertrag: the service is pure logic, the MCP
# interface owns the engine/session lifecycle) and ``# type: ignore`` were
# added on the ORM expressions for the ``app.*``-strict mypy gate (type-only,
# no behaviour change — the documented Schritt-4/6 pattern). The enums above
# are re-exported here so the MCP tool signatures can type-hint via the
# service module without importing ``domains/leads/models`` directly
# (import-linter Schritt-7 rule).


def serialize_lead(lead: Lead) -> dict:
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


def serialize_note(note: Note) -> dict:
    return {
        "id": note.id,
        "lead_id": note.lead_id,
        "body": note.body,
        "created_at": note.created_at.isoformat(),
    }


def mcp_create_lead(
    session: Session,
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
    if not name and not company:
        raise ValueError("name or company must be provided")
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
    return serialize_lead(lead)


def mcp_list_leads(
    session: Session,
    stage: Optional[LeadStage] = None,
    source: Optional[LeadSource] = None,
    show_snoozed: bool = False,
    limit: int = 50,
) -> list[dict]:
    query = select(Lead)
    if stage:
        query = query.where(Lead.stage == stage)
    if source:
        query = query.where(Lead.source == source)
    if not show_snoozed:
        today = date.today()
        query = query.where(
            or_(Lead.snooze_until.is_(None), Lead.snooze_until <= today)  # type: ignore[union-attr,operator]
        )
    query = query.order_by(Lead.created_at.desc()).limit(  # type: ignore[attr-defined]
        max(1, min(limit, 500))
    )
    return [serialize_lead(ld) for ld in session.exec(query).all()]


def mcp_get_lead(session: Session, lead_id: int) -> dict:
    lead = session.get(Lead, lead_id)
    if not lead:
        raise LookupError(f"Lead {lead_id} not found")
    return serialize_lead(lead)


def mcp_update_lead(
    session: Session,
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
    lead = session.get(Lead, lead_id)
    if not lead:
        raise LookupError(f"Lead {lead_id} not found")
    if name is not None:
        lead.name = name
    if company is not None:
        lead.company = company
    if email is not None:
        lead.email = email
    if phone is not None:
        lead.phone = phone
    if stage is not None:
        lead.stage = stage
    if notes is not None:
        lead.notes = notes
    if snooze_until is not None:
        lead.snooze_until = date.fromisoformat(snooze_until) if snooze_until else None
    if bant_budget is not None:
        lead.bant_budget = bant_budget.value
    if bant_authority is not None:
        lead.bant_authority = bant_authority.value
    if bant_need is not None:
        lead.bant_need = bant_need.value
    if bant_timing is not None:
        lead.bant_timing = bant_timing.value
    if ai_readiness is not None:
        lead.ai_readiness = ai_readiness.value
    if pain_points is not None:
        lead.pain_points = pain_points
    if next_action is not None:
        lead.next_action = next_action
    if next_action_date is not None:
        lead.next_action_date = date.fromisoformat(next_action_date) if next_action_date else None
    lead.updated_at = datetime.utcnow()
    session.add(lead)
    session.commit()
    session.refresh(lead)
    return serialize_lead(lead)


def mcp_add_note(session: Session, lead_id: int, body: str) -> dict:
    body = (body or "").strip()
    if not body:
        raise ValueError("body must not be empty")
    if not session.get(Lead, lead_id):
        raise LookupError(f"Lead {lead_id} not found")
    note = Note(lead_id=lead_id, body=body)
    session.add(note)
    session.commit()
    session.refresh(note)
    return serialize_note(note)


def mcp_list_notes(session: Session, lead_id: int) -> list[dict]:
    if not session.get(Lead, lead_id):
        raise LookupError(f"Lead {lead_id} not found")
    notes = session.exec(
        select(Note).where(Note.lead_id == lead_id).order_by(Note.created_at.desc())  # type: ignore[attr-defined]
    ).all()
    return [serialize_note(n) for n in notes]
