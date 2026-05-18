"""Re-export shim — the AI adapter moved to ``app.core.ai`` (Schritt 6).

Kept so existing imports (`from services.ai import …`) and the frozen
Schritt-0.5 characterization / `test_ai_proposal_drafts` unit tests keep
working unchanged: they ``monkeypatch.setattr(services.ai,
"chat_with_context", …)`` and read ``services.ai.PROPOSAL_DRAFTS_SYSTEM`` /
``services.ai.AiDraftError`` — this module stays the patch seam through
which the moved orchestration resolves the adapter (see
``app.domains.proposals.service``). The shim dies in Schritt 7 when those
tests retire (Shim-Sterbe-Gate, same pattern as the ``models.py`` shim).

This module deliberately does **not** read configuration.
"""

from app.core.ai import (  # noqa: F401
    AiDraftError,
    PROPOSAL_DRAFTS_SYSTEM,
    SYSTEM_PROMPTS,
    _call_anthropic,
    _parse_proposal_drafts,
    chat_with_context,
    generate_text,
)
from app.domains.proposals.service import generate_proposal_drafts  # noqa: F401

__all__ = [
    "AiDraftError",
    "PROPOSAL_DRAFTS_SYSTEM",
    "SYSTEM_PROMPTS",
    "_call_anthropic",
    "_parse_proposal_drafts",
    "chat_with_context",
    "generate_text",
    "generate_proposal_drafts",
]
