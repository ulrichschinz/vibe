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
from datetime import date
from typing import Any, Optional

from sqlmodel import Session, select

from app.domains.leads.models import (
    BantValue,
    Lead,
    LeadSource,
    LeadStage,
    LeadType,
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
