"""Re-export shim — the LinkedIn-PDF extraction adapter moved to
``app.core.ai`` (Schritt 6).

Kept so ``from services.linkedin_import import …`` and the frozen
Schritt-0.5 characterization test (which
``monkeypatch.setattr(services.linkedin_import, "extract_lead_from_pdf",
…)``) keep working unchanged — this module stays the patch seam through
which ``app.domains.leads.service.linkedin_preview`` resolves the adapter.
The shim dies in Schritt 7 (Shim-Sterbe-Gate, same pattern as ``models.py``).

The route handler composes the human-readable notes block and builds the
preview ``Lead`` in ``app.domains.leads.service`` from the flat dict this
returns.
"""

from app.core.ai import (  # noqa: F401
    SYSTEM_PROMPT,
    LinkedInImportError,
    _parse_json_block,
    extract_lead_from_pdf,
)

__all__ = [
    "SYSTEM_PROMPT",
    "LinkedInImportError",
    "_parse_json_block",
    "extract_lead_from_pdf",
]
