"""app.core.db_migrate — Alembic runner + CRM/Billing table partition.

Scaling-roadmap Schritt 9. Schema is established by **two independently
versioned Alembic trees** that share the single SQLite database today but
keep **separate version tables** (``alembic_version`` for CRM,
``alembic_version_billing`` for Billing). That partition is the whole point
of the roadmap's "CRM- und Billing-Schema getrennt versioniert → ermöglicht
späteren DB-Split ohne Daten-Migration": when Billing later moves to its own
deployable + DB (bounded-context Stage B, see
``docs/adr/007-billing-order-contract.md``), its migration history is
already self-contained — no retroactive untangling of a shared linear
history. It is also the structural home of the GoBD↔DSGVO split: the
Billing tree owns the separate billing retention rule (leads are
DSGVO-erasable, finalized invoices GoBD-retained ~10y).

This module is deliberately **domain-agnostic** (only ``alembic`` + stdlib
+ the passed engine): the ``core ↛ domains/interfaces/contracts``
import-linter contract (Schritt 8) must stay green. The table partition
below is plain ``__tablename__`` *strings* — no model import — so it is the
single source the baseline migration scripts read without coupling
``app.core`` to ``app.domains``.

The runner binds Alembic to the **live engine** the app uses (passed in,
stashed on ``config.attributes["connection"]`` for ``env.py``) rather than
re-deriving the URL — this preserves the e2e per-test-engine monkeypatch
seam (the ``database.engine`` / ``main.engine`` test isolation; the PR-#5
lesson) exactly as the old in-process ``create_all`` did.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Engine

# Repo-root/migrations (this file is app/core/db_migrate.py → parents[2]).
_MIGRATIONS_ROOT = Path(__file__).resolve().parents[2] / "migrations"

# --- Domain ↔ table partition (single source; strings only) ------------------
# Default SQLModel __tablename__ is the lowercased class name (no overrides in
# the codebase — verified). CRM/kernel + Billing together = the 13 tables of
# the ARCHITECTURE.md Datenmodell. The split mirrors the bounded-context cut:
# Billing's six tables are exactly the invoicing compliance domain.
CRM_TABLES: tuple[str, ...] = (
    "user",
    "apikey",
    "aisettings",
    "lead",
    "note",
    "planningmessage",
    "proposal",
)
BILLING_TABLES: tuple[str, ...] = (
    "issuerprofile",
    "invoice",
    "invoicelineitem",
    "invoicenumbersequence",
    "viesauditentry",
    "integritycheckrun",
)

# (tree dir under migrations/, Alembic version table) — separate version
# tables are what make a later DB split a pure deploy move.
_TREES: tuple[tuple[str, str], ...] = (
    ("crm", "alembic_version"),
    ("billing", "alembic_version_billing"),
)


def _config(tree: str, version_table: str, engine: Engine) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(_MIGRATIONS_ROOT / tree))
    cfg.set_main_option("version_table", version_table)
    # env.py uses this live connectable instead of building one from a URL,
    # so the per-test-engine monkeypatch seam keeps working.
    cfg.attributes["connection"] = engine
    return cfg


def run_migrations(engine: Engine) -> None:
    """Upgrade both versioned trees (CRM then Billing) to ``head``.

    CRM first so the shared SQLite file has the ``lead`` table before the
    Billing baseline runs (``Invoice.lead_id`` is a soft-FK with no SQL
    constraint, so this ordering is belt-and-braces, not a hard dependency —
    and it stays correct if Billing later runs against its own DB).
    Idempotent: the baselines delegate to ``create_all`` (checkfirst) +
    ``CREATE TRIGGER IF NOT EXISTS`` + introspection-guarded ``ALTER``.
    """
    for tree, version_table in _TREES:
        command.upgrade(_config(tree, version_table, engine), "head")
