from sqlmodel import create_engine, Session
from sqlalchemy import text, event

from app.core.config import get_settings

DATABASE_URL = get_settings().database_url


def _make_engine(url: str):
    """Build an engine + register the SQLite-specific event handlers.

    Extracted so tests can construct fresh engines that mirror production
    behaviour (WAL, foreign keys, BEGIN IMMEDIATE) without touching the
    module-level singleton.
    """
    eng = create_engine(url, connect_args={"check_same_thread": False})

    if "sqlite" in url:
        @event.listens_for(eng, "connect")
        def _set_sqlite_pragmas(dbapi_connection, _connection_record):
            """WAL + foreign keys + busy timeout on every connection.

            Required for our BEGIN IMMEDIATE based finalize path under
            contention (R-02).
            """
            dbapi_connection.isolation_level = None  # let us drive transactions
            cur = dbapi_connection.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA busy_timeout=30000")
            cur.close()

        @event.listens_for(eng, "begin")
        def _begin_immediate(conn):
            """Force every write transaction to begin in IMMEDIATE mode.

            R-02: serialises concurrent writers; combined with busy_timeout
            this means a second finalize call waits up to 5s for the first to
            commit instead of either silently racing or failing fast.
            """
            conn.exec_driver_sql("BEGIN IMMEDIATE")

    return eng


engine = _make_engine(DATABASE_URL)


# Columns that may NEVER change after a finalize. The status column itself,
# and post-finalize timestamps (sent_at, paid_at, cancelled_at) are excluded
# because state transitions still need to mutate them.
_INVOICE_FROZEN_COLS = [
    "number", "fiscal_year", "sequence_number",
    "invoice_date", "leistungsdatum", "due_date",
    "currency", "lead_id", "related_invoice_id", "proposal_id",
    "iss_legal_name", "iss_street", "iss_postal_code", "iss_city",
    "iss_country_code", "iss_steuernummer", "iss_ust_id",
    "iss_is_kleinunternehmer", "iss_bank_holder", "iss_bank_iban",
    "iss_bank_bic", "iss_contact_email", "iss_contact_phone",
    "cust_legal_name", "cust_company", "cust_salutation", "cust_street",
    "cust_street2", "cust_postal_code", "cust_city", "cust_country_code",
    "cust_vat_id", "cust_is_business", "cust_email",
    "subtotal_net", "vat_total", "total_gross", "vat_breakdown_json",
    "hint_kleinunternehmer", "hint_reverse_charge", "hint_third_country",
    "payment_terms_text", "title", "intro_text",
    "archive_path_pdf", "archive_path_xml",
    "hash_sha256", "hash_prev", "hash_algo",
    "kind",
]


def invoice_trigger_statements():
    """The BEFORE-UPDATE/INSERT/DELETE immutability trigger DDL (verbatim).

    Schritt 9: extracted unchanged out of ``install_invoice_triggers`` so the
    Alembic billing baseline and the legacy installer emit **byte-identical**
    SQL from one source (move-not-rewrite — the strings are not rewritten,
    only relocated into a list). All four use ``CREATE TRIGGER IF NOT
    EXISTS`` and are therefore natively idempotent.
    """
    cond = " OR ".join(f"NEW.{c} IS NOT OLD.{c}" for c in _INVOICE_FROZEN_COLS)
    return [
        f"""
        CREATE TRIGGER IF NOT EXISTS invoice_immutable_after_finalize
        BEFORE UPDATE ON invoice
        FOR EACH ROW
        WHEN OLD.status != 'draft' AND ({cond})
        BEGIN
            SELECT RAISE(ABORT, 'invoice immutable after finalize');
        END;
        """,
        """
        CREATE TRIGGER IF NOT EXISTS line_item_immutable_after_finalize_update
        BEFORE UPDATE ON invoicelineitem
        FOR EACH ROW
        WHEN (SELECT status FROM invoice WHERE id = OLD.invoice_id) != 'draft'
        BEGIN
            SELECT RAISE(ABORT, 'invoice line items immutable after finalize');
        END;
        """,
        """
        CREATE TRIGGER IF NOT EXISTS line_item_immutable_after_finalize_delete
        BEFORE DELETE ON invoicelineitem
        FOR EACH ROW
        WHEN (SELECT status FROM invoice WHERE id = OLD.invoice_id) != 'draft'
        BEGIN
            SELECT RAISE(ABORT, 'invoice line items immutable after finalize');
        END;
        """,
        """
        CREATE TRIGGER IF NOT EXISTS line_item_immutable_after_finalize_insert
        BEFORE INSERT ON invoicelineitem
        FOR EACH ROW
        WHEN (SELECT status FROM invoice WHERE id = NEW.invoice_id) != 'draft'
        BEGIN
            SELECT RAISE(ABORT, 'invoice line items immutable after finalize');
        END;
        """,
    ]


def install_invoice_triggers(target_engine):
    """Install BEFORE-UPDATE triggers that block edits on finalized invoices.

    Belt-and-braces with the SQLAlchemy event listener in
    ``services/invoicing/immutability.py``. The DB-level trigger guarantees
    correctness even against SQL executed outside the ORM. Behaviour
    unchanged by the Schritt-9 extraction (same statements, same order, same
    per-statement swallow).
    """
    with target_engine.connect() as conn:
        for stmt in invoice_trigger_statements():
            try:
                conn.execute(text(stmt))
                conn.commit()
            except Exception:
                pass


def _safe_add_column_on(target_engine, stmt: str):
    with target_engine.connect() as conn:
        try:
            conn.execute(text(stmt))
            conn.commit()
        except Exception:
            pass  # column already exists


# Additive lead address + tax columns used by invoicing. Schritt 9:
# extracted verbatim (column definition fragments only — the
# ``ALTER TABLE lead ADD COLUMN`` prefix is reassembled identically below)
# so the Alembic CRM baseline and the legacy installer share one source.
LEAD_INVOICE_COLUMNS = [
    "salutation TEXT",
    "street TEXT",
    "street2 TEXT",
    "postal_code TEXT",
    "city TEXT",
    "country_code TEXT DEFAULT 'DE'",
    "vat_id TEXT",
    "is_business INTEGER DEFAULT 1",
    "tax_country TEXT",
]


def install_lead_invoice_columns(target_engine):
    """Additive migration: lead address + tax fields used by invoicing.

    Behaviour unchanged by the Schritt-9 extraction (same nine
    ``ALTER TABLE`` statements, same order, same per-statement swallow).
    """
    for col in LEAD_INVOICE_COLUMNS:
        _safe_add_column_on(target_engine, f"ALTER TABLE lead ADD COLUMN {col}")


def create_db():
    # Move-Vertrag (Schritt 4): the table definitions live in
    # app/domains/*/models.py + app/core/{identity,ai_settings}.py.
    # `models.py` stays the single deterministic table-metadata aggregation
    # module (its Move-Vertrag role); this registry-bootstrap import is the
    # only documented `models` reach left. `database` is a top-level module
    # (not an import-linter root_package), so this is invisible to the
    # contracts; the Schritt-8 models-shim-death is prod *name-re-export*
    # scoped — no `services`/`routes`/`app` module imports it (ADR-009 §F).
    import models  # noqa: F401

    # Schritt 9 (Alembic): schema is now established by two independently
    # versioned Alembic trees (CRM + Billing, separate version tables) whose
    # 0001 baseline is *defined to be* the previous create_all schema
    # (delegates to `SQLModel.metadata.create_all` + the verbatim trigger /
    # lead-column DDL above). No implicit `create_all` schema evolution
    # anymore: future schema changes are new revisions. Bound to the live
    # `engine` (preserves the e2e per-test-engine monkeypatch seam — the
    # PR-#5 lesson). Rationale: docs/adr/010-alembic-split-versioning.md.
    from app.core.db_migrate import run_migrations

    run_migrations(engine)


# Backwards-compat shims used elsewhere in the codebase.
def _safe_add_column(stmt: str):
    _safe_add_column_on(engine, stmt)


def _safe_exec(stmt: str):
    with engine.connect() as conn:
        try:
            conn.execute(text(stmt))
            conn.commit()
        except Exception:
            pass


def get_session():
    with Session(engine) as session:
        yield session
