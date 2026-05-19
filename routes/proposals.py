"""Re-export shim — the proposals web router moved to
``app.interfaces.web.proposals`` (Schritt 8, ADR-009 §A).

Kept so the frozen Schritt-0.5 characterization / integration tests that do
``from routes import proposals as proposals_route`` keep working
**unchanged** (0-tests-diff). No production module imports this anymore —
`main.py` wires ``app.interfaces.web``. Physical deletion + test-import
migration is a deferred follow-up.
"""

from app.interfaces.web.proposals import router  # noqa: F401

__all__ = ["router"]
