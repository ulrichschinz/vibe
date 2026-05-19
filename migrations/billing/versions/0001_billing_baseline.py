"""Billing baseline — the current invoicing-compliance schema, verbatim.

Scaling-roadmap Schritt 9. Same principle as the CRM baseline: delegate to
the exact pre-Schritt-9 schema builder so the captured schema is
byte-identical by construction (move-not-rewrite — ``services/invoicing/``
is never rewritten). This is the Billing tree: its own ``script_location``,
its own version table (``alembic_version_billing``) → a later DB split is a
pure deploy move, no data migration. It is also the structural home of the
GoBD↔DSGVO split (the separate billing retention rule lives on this tree;
finalized invoices are GoBD-retained independently of DSGVO lead erasure).

The six tables here are exactly the invoicing compliance domain
(Issuer/Invoice/LineItem/Sequence/Vies/Integrity). The immutability triggers
are reinstalled verbatim from ``database.invoice_trigger_statements()`` (all
``CREATE TRIGGER IF NOT EXISTS`` → natively idempotent). All DDL runs on
Alembic's migration connection (single connection, WAL-safe).

Revision ID: 0001_billing_baseline
Revises:
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_billing_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    import models  # noqa: F401  registers every table on SQLModel.metadata
    from sqlmodel import SQLModel

    import database
    from app.core.db_migrate import BILLING_TABLES

    bind = op.get_bind()
    md = SQLModel.metadata
    md.create_all(bind, tables=[md.tables[t] for t in BILLING_TABLES])

    for stmt in database.invoice_trigger_statements():
        op.execute(sa.text(stmt))


def downgrade() -> None:
    import models  # noqa: F401
    from sqlmodel import SQLModel

    from app.core.db_migrate import BILLING_TABLES

    bind = op.get_bind()
    for trig in (
        "invoice_immutable_after_finalize",
        "line_item_immutable_after_finalize_update",
        "line_item_immutable_after_finalize_delete",
        "line_item_immutable_after_finalize_insert",
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {trig}")
    md = SQLModel.metadata
    md.drop_all(bind, tables=[md.tables[t] for t in reversed(BILLING_TABLES)])
