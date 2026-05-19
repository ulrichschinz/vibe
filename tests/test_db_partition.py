"""Audit-Remediation T3 — CRM/Billing-Partition deckt jede Tabelle ab.

`app/core/db_migrate.py` versioniert das Schema über **zwei getrennte**
Alembic-Bäume; jede Baseline erstellt nur die in ihrer Partition
(`CRM_TABLES` / `BILLING_TABLES`) *aufgezählten* Tabellen. Diese String-
Tupel sind hartkodiert. Ohne diesen Test landet ein Modell der falschen
Partition (oder gar keiner) lautlos im falschen Versionsbaum — bzw. wird
beim Prod-Start gar nicht angelegt, während die Test-Suite es via
`create_all` sieht (grün im CI, kaputt im Deploy; defeated den „DB-Split
ohne Daten-Migration"). Der Doc-Gate zählt nur die *Anzahl* Tabellen, nicht
ihre Partitions-Zugehörigkeit — diese Lücke schließt genau dieser Test.

Acceptance-Test (in `tests/`, nicht `tests/characterization/`), daher ab
diesem PR erlaubt — analog `tests/test_models_split.py`.
"""

from __future__ import annotations

from sqlmodel import SQLModel

from app.core.db_migrate import BILLING_TABLES, CRM_TABLES


def test_partitions_are_disjoint() -> None:
    overlap = set(CRM_TABLES) & set(BILLING_TABLES)
    assert not overlap, f"a table is in both partitions: {sorted(overlap)}"


def test_partition_union_is_exactly_the_metadata_table_set() -> None:
    import models  # noqa: F401  aggregation shim registers every table

    registered = set(SQLModel.metadata.tables)
    partitioned = set(CRM_TABLES) | set(BILLING_TABLES)

    missing = registered - partitioned
    extra = partitioned - registered
    assert not missing, (
        f"table(s) on SQLModel.metadata but in NO migration partition "
        f"(would never be created by Alembic in prod): {sorted(missing)} — "
        f"add to CRM_TABLES or BILLING_TABLES in app/core/db_migrate.py"
    )
    assert not extra, (
        f"partition lists a table that no model registers anymore: "
        f"{sorted(extra)} — remove from app/core/db_migrate.py"
    )
