"""proposals domain — service layer (Scaling-roadmap Schritt 6).

Pure business logic pulled out of ``routes/proposals.py`` (and the
draft-generator out of ``services/ai.py``): AI-draft generation + the
"prefill the editor from a planning chat" merge. No FastAPI import; the
``Session`` is passed in by the caller (Scaffold-Vertrag). The AI *adapter*
(Anthropic client, prompts, ``===MARKER===`` parsing) lives in
``app.core.ai`` — orchestration stays here, the owning domain.

"Keine Verhaltensänderung": ``generate_proposal_drafts`` and the merge loop
are the verbatim originals. Contract-conformant imports: own domain
(``app.domains.proposals.models``) + ``app.core.*`` only — never another
``app.domains.*``.

Module-as-seam adapter: ``generate_proposal_drafts`` resolves
``chat_with_context`` and ``PROPOSAL_DRAFTS_SYSTEM`` through the
``app.core.ai`` module object (lazy ``from app.core import ai as _seam``)
so the unit + characterization tests that
``monkeypatch.setattr(ai, "chat_with_context", …)`` keep intercepting on
the same module object — the seam is the module, not its old path.
T7-B (ADR-015) retired the ``services/ai.py`` re-export shim; this is
the direct successor seam (no shim hop, no domain→domain edge).
"""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any, Optional

from sqlmodel import Session, select

from app.core.ai import AiDraftError
from app.core.config import get_settings
from app.domains.proposals.models import DEFAULT_SERVICES, Proposal, ProposalStatus

log = logging.getLogger(__name__)

__all__ = [
    "AiDraftError",
    "generate_proposal_drafts",
    "build_proposal_prefill",
    "DEFAULT_SERVICES",
    "ProposalStatus",
    "serialize_proposal",
    "list_proposals",
    "get_proposal",
]


def generate_proposal_drafts(lead: Any, planning_messages: Any, settings: Any) -> dict:
    """Single Anthropic call → parsed dict {intro, services:[3 blocks]}.

    Raises AiDraftError when there is no chat to draw from.
    """
    if not planning_messages:
        raise AiDraftError("Kein Chat-Verlauf vorhanden.")
    # Resolve the adapter through the app.core.ai module object so the
    # monkeypatch seam (ai.chat_with_context / .PROPOSAL_DRAFTS_SYSTEM)
    # keeps intercepting — see module docstring. Lazy import preserves the
    # module-as-seam pattern (per-call attribute lookup, not import-time bind).
    from app.core import ai as _seam

    messages = [{"role": m.role, "content": m.content} for m in planning_messages]
    messages.append(
        {
            "role": "user",
            "content": (
                "Erstelle jetzt den Angebots-Entwurf wie im System-Prompt vorgegeben. "
                f"Kunde: {lead.name or '—'} / {lead.company or '—'}."
            ),
        }
    )
    text = _seam.chat_with_context(messages, _seam.PROPOSAL_DRAFTS_SYSTEM, settings)
    return _seam._parse_proposal_drafts(text)


def build_proposal_prefill(
    lead: Any,
    planning_messages: Any,
    ai_settings: Any,
    ai_ok: bool,
) -> tuple[list[dict], Any]:
    """Build the editor prefill (services list + intro) for ``from_plan``.

    Verbatim move of the merge/fallback branch from ``routes/proposals.py``:
    all 3 service blocks are enabled when prefilled from chat; on any LLM
    failure fall back to ``lead.plan_text`` (no robustness fix in this step).
    Returns ``(services, prefill_intro)``.
    """
    services = deepcopy(DEFAULT_SERVICES)
    prefill_intro = None

    if ai_ok and planning_messages:
        try:
            drafts = generate_proposal_drafts(lead, planning_messages, ai_settings)
            prefill_intro = drafts["intro"] or lead.plan_text
            # All 3 service blocks are enabled when prefilled from chat —
            # the operator turns them off manually in the editor.
            by_id = {s["id"]: s for s in drafts["services"]}
            for svc in services:
                d = by_id.get(svc["id"])
                if d and d["description"]:
                    svc["description"] = d["description"]
                if d and d["deliverables"]:
                    svc["deliverables"] = d["deliverables"]
                if d and (d["description"] or d["deliverables"]):
                    svc["enabled"] = True
        except Exception:
            log.exception("KI-Draft fehlgeschlagen, Fallback auf plan_text")
            prefill_intro = lead.plan_text
    else:
        prefill_intro = lead.plan_text

    return services, prefill_intro


# ── MCP-facing Proposal operations (Schritt 7: MCP-Entdopplung) ────────────
#
# Verbatim move of the proposal query/serialization that lived in
# ``services/mcp_server.py`` (``list_proposals``/``get_proposal`` + the
# ``_proposal_dict``/``_proposal_pdf_url`` serializers). The MCP
# ``create_proposal``/``mark_proposal_sent`` tools already delegated
# construction to the clean shared ``services/proposals.py`` (left
# **untouched** — also used verbatim by ``routes/proposals.py``); they keep
# calling it directly and now only attach ``serialize_proposal`` so the MCP
# interface no longer imports the ``Proposal`` model. ``ProposalStatus``/
# ``DEFAULT_SERVICES`` are re-exported (see ``__all__``) so the MCP tool
# signatures/defaults resolve via this service module — no
# ``domains/proposals/models`` import in the interface (import-linter
# Schritt-7 rule). Deliberately **no** ``services.proposals`` import here:
# that would pull the legacy ``services.numbering`` into the ``app.*``-strict
# mypy graph (a pre-existing legacy ``[attr-defined]``); the construction
# stays wired in the (non-mypy-gated) MCP interface. "Keine
# Verhaltensänderung": bodies are byte-for-byte the originals.


def _proposal_pdf_url(proposal_id: int) -> str:
    host = get_settings().app_host
    if host:
        return f"https://{host}/proposals/{proposal_id}/pdf"
    return f"/proposals/{proposal_id}/pdf"


def serialize_proposal(p: Proposal) -> dict:
    return {
        "id": p.id,
        "number": p.number,
        "lead_id": p.lead_id,
        "title": p.title,
        "intro_text": p.intro_text,
        "services": p.get_services(),
        "total_value": p.total_value,
        "duration": p.duration,
        "payment_terms": p.payment_terms,
        "travel_costs": p.travel_costs,
        "validity_days": p.validity_days,
        "status": p.status.value if p.status else None,
        "sent_at": p.sent_at.isoformat() if p.sent_at else None,
        "created_at": p.created_at.isoformat(),
        "updated_at": p.updated_at.isoformat(),
        "pdf_url": _proposal_pdf_url(p.id) if p.id else None,
        "pdf_url_note": "Open in browser while logged in to Vibe; not fetchable with X-API-Key.",
    }


def list_proposals(
    session: Session,
    lead_id: Optional[int] = None,
    status: Optional[ProposalStatus] = None,
) -> list[dict]:
    query = select(Proposal)
    if lead_id is not None:
        query = query.where(Proposal.lead_id == lead_id)
    if status:
        query = query.where(Proposal.status == status)
    query = query.order_by(Proposal.created_at.desc())  # type: ignore[attr-defined]
    return [serialize_proposal(p) for p in session.exec(query).all()]


def get_proposal(session: Session, proposal_id: int) -> dict:
    proposal = session.get(Proposal, proposal_id)
    if not proposal:
        raise LookupError(f"Proposal {proposal_id} not found")
    return serialize_proposal(proposal)
