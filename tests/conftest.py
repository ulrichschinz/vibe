"""
Shared pytest fixtures.

Each test gets a fresh SQLite file in tmp_path. We build a per-test engine
via ``database._make_engine`` (same configuration as production: WAL, foreign
keys, BEGIN IMMEDIATE on every transaction, busy_timeout 5s) and run
``create_all`` + invoice triggers + lead-column migrations against it. Models
are imported once at module level — they live on the global SQLModel metadata
and bind to whichever engine we point at.

The production ``database.engine`` is NOT touched by tests.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make the project importable
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest
from sqlmodel import Session, SQLModel

import models  # noqa: F401  registers tables on the metadata
import database  # noqa: F401
import services.invoicing.immutability  # noqa: F401  registers SA event listeners


@pytest.fixture
def engine(tmp_path):
    """Fresh SQLite engine per test, configured exactly like production."""
    db_path = tmp_path / "test.db"
    eng = database._make_engine(f"sqlite:///{db_path}")
    SQLModel.metadata.create_all(eng)
    database.install_lead_invoice_columns(eng)
    database.install_invoice_triggers(eng)
    return eng


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s


@pytest.fixture
def archive_dir(tmp_path, monkeypatch):
    """Per-test archive root."""
    root = tmp_path / "archive"
    root.mkdir()
    monkeypatch.setenv("INVOICE_ARCHIVE_ROOT", str(root))
    return root
