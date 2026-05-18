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

Transitional seam: ``generate_proposal_drafts`` resolves ``chat_with_context``
and ``PROPOSAL_DRAFTS_SYSTEM`` through the legacy ``services.ai`` module
(re-export shim over ``app.core.ai``) so the frozen Schritt-0.5
characterization tests and the ``test_ai_proposal_drafts`` unit test — which
``monkeypatch.setattr(services.ai, "chat_with_context", …)`` and assert
``ai.PROPOSAL_DRAFTS_SYSTEM`` — keep intercepting through the same module
object until they retire (Schritt 7 lifecycle). Same family as the
``models.py`` shim; not a domain→domain edge.
"""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any

from app.core.ai import AiDraftError
from app.domains.proposals.models import DEFAULT_SERVICES

log = logging.getLogger(__name__)

__all__ = ["AiDraftError", "generate_proposal_drafts", "build_proposal_prefill"]


def generate_proposal_drafts(lead: Any, planning_messages: Any, settings: Any) -> dict:
    """Single Anthropic call → parsed dict {intro, services:[3 blocks]}.

    Raises AiDraftError when there is no chat to draw from.
    """
    if not planning_messages:
        raise AiDraftError("Kein Chat-Verlauf vorhanden.")
    # Resolve the adapter through the legacy shim so the frozen monkeypatch
    # seam (services.ai.chat_with_context / .PROPOSAL_DRAFTS_SYSTEM) keeps
    # intercepting — see module docstring. Lazy import avoids an import cycle
    # (services.ai re-exports this very function).
    from services import ai as _seam

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
