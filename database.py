from sqlmodel import create_engine, SQLModel, Session
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


def install_invoice_triggers(target_engine):
    """Install BEFORE-UPDATE triggers that block edits on finalized invoices.

    Belt-and-braces with the SQLAlchemy event listener in
    ``services/invoicing/immutability.py``. The DB-level trigger guarantees
    correctness even against SQL executed outside the ORM.
    """
    cond = " OR ".join(f"NEW.{c} IS NOT OLD.{c}" for c in _INVOICE_FROZEN_COLS)
    statements = [
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
    with target_engine.connect() as conn:
        for stmt in statements:
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


def install_lead_invoice_columns(target_engine):
    """Additive migration: lead address + tax fields used by invoicing."""
    _safe_add_column_on(target_engine, "ALTER TABLE lead ADD COLUMN salutation TEXT")
    _safe_add_column_on(target_engine, "ALTER TABLE lead ADD COLUMN street TEXT")
    _safe_add_column_on(target_engine, "ALTER TABLE lead ADD COLUMN street2 TEXT")
    _safe_add_column_on(target_engine, "ALTER TABLE lead ADD COLUMN postal_code TEXT")
    _safe_add_column_on(target_engine, "ALTER TABLE lead ADD COLUMN city TEXT")
    _safe_add_column_on(target_engine, "ALTER TABLE lead ADD COLUMN country_code TEXT DEFAULT 'DE'")
    _safe_add_column_on(target_engine, "ALTER TABLE lead ADD COLUMN vat_id TEXT")
    _safe_add_column_on(target_engine, "ALTER TABLE lead ADD COLUMN is_business INTEGER DEFAULT 1")
    _safe_add_column_on(target_engine, "ALTER TABLE lead ADD COLUMN tax_country TEXT")


def create_db():
    SQLModel.metadata.create_all(engine)
    install_lead_invoice_columns(engine)
    install_invoice_triggers(engine)


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
