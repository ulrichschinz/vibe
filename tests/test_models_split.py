"""Table-Bootstrap-Vertrag für `app.core.db_tables.register_tables` (T7-A).

Historie: dieser Test war ursprünglich der Move-Vertrag-Guard für
scaling-roadmap Schritt 4 (Split von `models.py` in `app/domains/*/models.py`
+ `app/core/{identity,ai_settings}.py`). Mit Remediation-Track T7-A
(ADR-014) starb der `models.py`-Shim physisch — der Aggregations-Vertrag
lebt jetzt in `app/core/db_tables.register_tables()`. Der Test wandert die
Naht mit: gleiches strukturelles Versprechen, neuer Aufrufpfad.

Das geprüfte Versprechen ist unverändert: **nach einem `register_tables()`-
Aufruf kennt die geteilte `SQLModel.metadata` exakt die 13 Tabellen, jede
genau einmal registriert.**
"""

from __future__ import annotations

from sqlmodel import SQLModel

from db_tables import register_tables

# The 13 SQLModel tables (SQLModel lowercases the class name for __tablename__).
EXPECTED_TABLES = {
    "aisettings",
    "user",
    "apikey",
    "lead",
    "note",
    "planningmessage",
    "proposal",
    "issuerprofile",
    "invoice",
    "invoicelineitem",
    "invoicenumbersequence",
    "viesauditentry",
    "integritycheckrun",
}


def test_metadata_table_set_is_exactly_the_thirteen():
    register_tables()

    assert set(SQLModel.metadata.tables) == EXPECTED_TABLES


def test_reregister_is_idempotent_no_table_redefinition():
    # Re-calling the bootstrap must not raise "Table '...' is already
    # defined" — the Python module-cache makes registration happen exactly
    # once per module, every subsequent call is a no-op.
    register_tables()
    register_tables()
    assert set(SQLModel.metadata.tables) == EXPECTED_TABLES
