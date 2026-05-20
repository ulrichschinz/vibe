"""CRM baseline — the current create_all schema, captured verbatim.

Scaling-roadmap Schritt 9. Baseline migration = *aktuelles Schema, keine
Datenänderung*. We deliberately do **not** hand-write ~7 ``op.create_table``
blocks (drift risk, and no local interpreter to autogenerate against — see
docs/adr/010): instead the baseline **delegates to the exact schema builder
production used before** —
``SQLModel.metadata.create_all(<crm tables>)`` plus the verbatim additive
``lead`` invoice-column DDL. That makes the captured schema byte-identical
to the pre-Schritt-9 ``create_all`` by construction (move-not-rewrite).

All DDL runs on Alembic's own migration connection (``op.get_bind()``) — a
single connection, no nested second writer against the WAL/BEGIN-IMMEDIATE
SQLite engine. Idempotent: ``create_all`` is checkfirst; the ``ALTER`` is
introspection-guarded (the Lead model already declares these columns since
Schritt 4, so they exist after ``create_all`` — the guard reproduces the
legacy try/except-pass end state without aborting the migration txn).

Revision ID: 0001_crm_baseline
Revises:
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_crm_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    from db_tables import register_tables

    register_tables()  # T7-A (ADR-014): expliziter Tabellen-Bootstrap statt models-Shim
    from sqlmodel import SQLModel

    import database
    from app.core.db_migrate import CRM_TABLES

    bind = op.get_bind()
    md = SQLModel.metadata
    md.create_all(bind, tables=[md.tables[t] for t in CRM_TABLES])

    # Additive lead address/tax columns — verbatim list from database.py,
    # guarded by introspection so a re-run (or columns already present from
    # the model) is a no-op exactly like the legacy _safe_add_column swallow.
    existing = {c["name"] for c in sa.inspect(bind).get_columns("lead")}
    for col in database.LEAD_INVOICE_COLUMNS:
        if col.split()[0] not in existing:
            op.execute(f"ALTER TABLE lead ADD COLUMN {col}")


def downgrade() -> None:
    from db_tables import register_tables

    register_tables()  # T7-A (ADR-014)
    from sqlmodel import SQLModel

    from app.core.db_migrate import CRM_TABLES

    bind = op.get_bind()
    md = SQLModel.metadata
    md.drop_all(bind, tables=[md.tables[t] for t in reversed(CRM_TABLES)])
