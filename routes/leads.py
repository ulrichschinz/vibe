"""Re-export shim — the leads web router moved to
``app.interfaces.web.leads`` (Schritt 8, ADR-009 §A).

Kept so the frozen Schritt-0.5 characterization / integration tests that do
``from routes import leads as leads_route`` keep working **unchanged**
(0-tests-diff). No production module imports this anymore — `main.py` wires
``app.interfaces.web``. Physical deletion + test-import migration is a
deferred follow-up (the chosen Fork-2 scope: cut the prod naht, keep the
test-shim, defer the file death).
"""

from app.interfaces.web.leads import router  # noqa: F401

__all__ = ["router"]
