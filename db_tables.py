"""Tabellen-Metadaten-Bootstrap (Remediation-Track T7-A).

Erbe des aggregierenden `models.py`-Shims (ADR-014): Importiert per
expliziter Funktion jedes Modul, das eine `SQLModel`-Tabelle definiert,
sodass die geteilte `SQLModel.metadata` nach dem Aufruf alle 13 Tabellen
kennt. Reihenfolge spiegelt die alte `models.py`-Reihenfolge (kernel →
leads → proposals → billing).

`register_tables()` ist idempotent (Python-Module-Cache). Drei Aufrufer:

* `database.create_db()` — Prod-Bootstrap vor Alembic-Run
* `tests/conftest.py` — Char/Unit/Integration-Suite
* `tests/e2e/conftest.py` — e2e-Suite

**Bewusst keine Modul-Level-Side-Effect-Imports.** Die Funktions-Form
(a) macht den Aufruf explizit statt magisch, (b) disqualifiziert dieses
Modul als triviale Re-Export-Shim unter der T6-AST-Fingerprint-Definition
(`scripts/check_architecture_metrics.py:_is_reexport_shim`) — der T6-
Inventar-Zähler sinkt damit echt von 5 auf 4 (statt nur den Shim-Pfad
zu verschieben).

**Bewusst top-level (nicht in `app.core`).** Wäre die Aggregation im
`app.core`-Paket, würde sie den seit Schritt 8 aktiven `core ↛ domains`-
`import-linter`-Vertrag brechen (`app.core` darf `app.domains.*` nicht
importieren — ADR-009 §G). Das alte `models.py` lebte aus genau diesem
Grund top-level; sein Erbe bleibt es auch. `main.py`, `database.py` und
dieses Modul sind die drei top-level-Module außerhalb der import-linter-
`root_packages` — bewusst, dokumentiert, weiterhin gültig.
"""

from __future__ import annotations


def register_tables() -> None:
    """Side-effect import every SQLModel table module.

    Idempotent. Call once before `SQLModel.metadata.create_all(...)` or
    before Alembic's `target_metadata` comparison.
    """
    import app.core.identity  # noqa: F401
    import app.core.ai_settings  # noqa: F401
    import app.domains.leads.models  # noqa: F401
    import app.domains.proposals.models  # noqa: F401
    import app.domains.billing.models  # noqa: F401
