"""Alembic environment — shared by both versioned trees (CRM & Billing).

Scaling-roadmap Schritt 9. This file is identical for the ``crm`` and
``billing`` script locations on purpose: the only thing that differs is the
**version table**, which the runner passes via the ``version_table`` main
option (``alembic_version`` for CRM, ``alembic_version_billing`` for
Billing) so the two histories never share state — the precondition for a
later DB split without data migration.

It lives under ``migrations/`` which is **not** an import-linter
``root_package`` and **not** in the ``mypy scripts app`` / ``ruff`` scope,
so its dynamic Alembic patterns and its ``database``/``models`` reach do not
affect any Schritt-1..8 contract.

Binding: the in-process runner (``app.core.db_migrate.run_migrations``)
stashes the **live engine** on ``config.attributes["connection"]`` — this
preserves the e2e per-test-engine monkeypatch seam (PR-#5 lesson). When run
from the ``alembic`` CLI (no stashed connection) it falls back to the
configured database URL.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy.engine import Engine

config = context.config

# No autogenerate in Schritt 9 — the 0001 baseline is hand-defined to be the
# previous create_all schema (byte-identical by delegation). target_metadata
# is intentionally None; a future step may wire the per-tree metadata in.
target_metadata = None

_VERSION_TABLE = config.get_main_option("version_table") or "alembic_version"


def _run(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        version_table=_VERSION_TABLE,
        render_as_batch=True,  # SQLite-friendly (ALTER via batch) for future revisions
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = config.attributes.get("connection", None)

    if connectable is None:
        # CLI fallback: build an engine from the central settings (no direct
        # environment read here — avoids both duplicating config and the
        # doc-gate getenv-substring false positive).
        from app.core.config import get_settings
        from sqlalchemy import create_engine

        connectable = create_engine(
            get_settings().database_url, connect_args={"check_same_thread": False}
        )

    if isinstance(connectable, Engine):
        with connectable.connect() as connection:
            _run(connection)
    else:
        # Already a Connection (in-process bind).
        _run(connectable)


if context.is_offline_mode():
    # Offline/--sql mode is unused in-process; supported for completeness.
    url = None
    from contextlib import suppress

    with suppress(Exception):
        from app.core.config import get_settings

        url = get_settings().database_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        version_table=_VERSION_TABLE,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    run_migrations_online()
