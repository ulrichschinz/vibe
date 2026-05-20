"""E2E-scoped fixtures — override the shared ``engine`` to exercise Alembic.

Remediation-Track T4b. The shared ``tests/conftest.py`` builds the per-test
schema via ``SQLModel.metadata.create_all`` + ``install_invoice_triggers`` +
``install_lead_invoice_columns`` (the pre-Schritt-9 path). That keeps the
132 characterization tests + the 90 %-Invoicing suite stable on the exact
seam they were pinned against, but it means **the Alembic path is never
exercised by tests** — Schritt 9 only makes it run in production
``database.create_db()`` and in the dedicated parity test (T4a,
``tests/test_db_migration_parity.py``).

This conftest overrides the ``engine`` fixture for the e2e suite so every
e2e run now goes through ``app.core.db_migrate.run_migrations`` — the same
runner production uses. T4a proves the resulting schema is byte-identical to
the ``create_all`` path (modulo the Alembic bookkeeping tables
``alembic_version`` / ``alembic_version_billing``, which no test touches),
so this is schema-neutral by construction; the e2e suite must stay green.
Pytest discovers conftests by directory, so this override applies only to
``tests/e2e/`` — unit/integration/characterization keep the shared fixture
unchanged.
"""
from __future__ import annotations

import pytest

import database
from app.core.db_migrate import run_migrations
from db_tables import register_tables

register_tables()  # populate SQLModel.metadata before Alembic's target_metadata diff


@pytest.fixture
def engine(tmp_path):
    """Fresh SQLite engine per e2e test, schema built via Alembic.

    Same engine configuration as production (WAL, foreign keys, BEGIN
    IMMEDIATE, busy_timeout 5 s — via ``database._make_engine``), but the
    schema is materialised by ``run_migrations`` instead of ``create_all`` +
    the trigger/column helpers. The baselines internally delegate to the
    same helpers, so the resulting schema is the same — this fixture only
    swaps *how* it is built so the Alembic code path participates in the CI
    run on every PR.
    """
    db_path = tmp_path / "test.db"
    eng = database._make_engine(f"sqlite:///{db_path}")
    run_migrations(eng)
    return eng
