"""T4a — Alembic-Pfad real prüfen (Remediation-Track).

Schritt 9 (`docs/adr/010-alembic-split-versioning.md`) hat die
0001-Baseline beider Versionsbäume *definiert* als das alte
`create_all`-Schema (delegiert → byte-gleich, move-not-rewrite). Das
Repo hatte bis hier **null** Tests, die ``run_migrations`` tatsächlich
ausführen — die Behauptung war konstruktiv tautologisch statt
empirisch geprüft.

Dieser Test schließt die Lücke: er baut beide Schemas in jeweils einer
frischen SQLite-Datei auf — das pre-Schritt-9-`create_db()`-Schema
(``SQLModel.metadata.create_all`` + Invoice-Trigger +
Lead-Invoice-Spalten) gegen den Alembic-Pfad
(``app.core.db_migrate.run_migrations``) — und vergleicht den
kanonischen Schema-Dump (`sqlite_master` + `PRAGMA table_info` +
`PRAGMA index_list`). Sie *müssen* heute identisch sein und werden es
auch in Zukunft bleiben — andernfalls bricht dieser Test. Damit fängt
er genau die Klasse Drift, die Schritt 9 verbieten wollte: ein neues
Modell, ein neuer Index, eine geänderte Spalte ohne korrespondierende
Alembic-Revision.

Ehrlich zur Grenze: der Test prüft das *Schema*, nicht den *Daten*-Pfad
(Adopt einer befüllten DB ist bereits in Prod live, vgl.
`docs/deploy-runbook.md` §2). Der Daten-Adopt-Pfad ist idempotent per
Konstruktion (`create_all(checkfirst)` + `CREATE TRIGGER IF NOT EXISTS`
+ introspektions-geguardete `ALTER`), nicht durch diesen Test
abgedeckt.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from sqlalchemy import create_engine
from sqlmodel import SQLModel

# Registry-Bootstrap: gleicher Trick wie database.create_db() — ohne
# diesen Import wäre SQLModel.metadata leer.
import models  # noqa: F401

from app.core.db_migrate import run_migrations
from database import install_invoice_triggers, install_lead_invoice_columns


# Tabellen, die ZUM Schema-Vergleich AUSGENOMMEN werden: die Alembic-
# Versions-Tabellen existieren naturgemäß nur im Alembic-Pfad und sind
# nicht Teil des Domänen-Schemas (sie sind die Versions-Buchhaltung
# selbst). Schritt 9 nutzt zwei getrennte Versionsbäume, daher beide.
_ALEMBIC_BOOKKEEPING = {"alembic_version", "alembic_version_billing"}


def _schema_dump(db_path: Path) -> dict:
    """Kanonischer Schema-Dump: Tabellen → Spalten + Indizes + Trigger-DDL.

    Vergleicht *strukturell*, nicht textuell auf `sqlite_master.sql`
    allein — das fängt Drift in Spaltentypen/NOT-NULL/Defaults/PK auch
    dann, wenn die `CREATE TABLE`-Strings sich nur in Whitespace
    unterscheiden würden.
    """
    con = sqlite3.connect(str(db_path))
    cur = con.cursor()
    rows = cur.execute(
        "SELECT type, name, tbl_name, sql FROM sqlite_master "
        "WHERE name NOT LIKE 'sqlite_%' "
        "ORDER BY type, name"
    ).fetchall()
    out: dict[str, dict] = {"table": {}, "index": {}, "trigger": {}, "view": {}}
    for type_, name, tbl_name, sql in rows:
        if name in _ALEMBIC_BOOKKEEPING:
            continue
        entry: dict = {"tbl_name": tbl_name, "sql": sql}
        if type_ == "table":
            cols = cur.execute(f"PRAGMA table_info({name})").fetchall()
            entry["columns"] = [
                {
                    "cid": c[0],
                    "name": c[1],
                    "type": c[2],
                    "notnull": c[3],
                    "default": c[4],
                    "pk": c[5],
                }
                for c in cols
            ]
            idxs = cur.execute(f"PRAGMA index_list({name})").fetchall()
            # PRAGMA index_list returns (seq, name, unique, origin, partial)
            entry["indexes"] = sorted(
                ({"name": i[1], "unique": bool(i[2]), "origin": i[3]} for i in idxs),
                key=lambda d: d["name"],
            )
        out.setdefault(type_, {})[name] = entry
    con.close()
    return out


def _build_create_all_schema(db_path: Path) -> None:
    """Pre-Schritt-9-Pfad: `database.create_db()` ohne den `run_migrations`-
    Aufruf. Identische öffentliche Helfer aus `database.py` (keine
    Duplikation — das ist der move-not-rewrite-Invariant)."""
    engine = create_engine(f"sqlite:///{db_path}")
    SQLModel.metadata.create_all(engine)
    install_invoice_triggers(engine)
    install_lead_invoice_columns(engine)
    engine.dispose()


def _build_alembic_schema(db_path: Path) -> None:
    """Schritt-9-Pfad: `run_migrations` (CRM- + Billing-Baum, beide auf
    derselben DB). Die 0001-Revisionen rufen intern dieselben Helfer."""
    engine = create_engine(f"sqlite:///{db_path}")
    run_migrations(engine)
    engine.dispose()


def test_alembic_baseline_equals_create_all(tmp_path: Path) -> None:
    """Die 0001-Baseline beider Alembic-Bäume produziert byte-gleiches
    Schema wie der pre-Schritt-9-`create_all`-Pfad. Künftige Drift
    (Modell-Erweiterung ohne passende Revision) bricht diesen Test.
    """
    db_create_all = tmp_path / "create_all.db"
    db_alembic = tmp_path / "alembic.db"

    _build_create_all_schema(db_create_all)
    _build_alembic_schema(db_alembic)

    schema_create_all = _schema_dump(db_create_all)
    schema_alembic = _schema_dump(db_alembic)

    assert schema_alembic == schema_create_all, (
        "Schema-Drift zwischen `create_all` und Alembic-0001-Baseline. "
        "Wenn ein Modell geändert/ergänzt wurde, fehlt die korrespondierende "
        "Alembic-Revision (Schritt-9-Vertrag, ADR-010)."
    )
