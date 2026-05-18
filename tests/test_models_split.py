"""Move-Vertrag guard for scaling-roadmap Schritt 4.

The split of `models.py` into `app/domains/*/models.py` +
`app/core/{identity,ai_settings}.py` must be a *pure move*: the set of
tables registered on the shared `SQLModel.metadata` is unchanged, every
table is registered exactly once (no `Table already defined`), and the
top-level `models` shim re-exports the *same* objects from their new homes.

This is a Schritt-4 acceptance test, not a characterization test (it lives
in `tests/`, not `tests/characterization/`), so it is allowed to exist
from this PR onward.
"""

from __future__ import annotations

import importlib

from sqlmodel import SQLModel

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
    import models  # noqa: F401  aggregation shim registers every table

    assert set(SQLModel.metadata.tables) == EXPECTED_TABLES


def test_reimport_is_idempotent_no_table_redefinition():
    import models

    # Re-importing the aggregation shim must not raise
    # "Table '...' is already defined" — registration happens exactly once.
    importlib.reload(models)
    assert set(SQLModel.metadata.tables) == EXPECTED_TABLES


def test_shim_reexports_the_same_objects_as_the_new_homes():
    import models
    from app.core.ai_settings import AiSettings
    from app.core.identity import User
    from app.domains.billing.models import Invoice
    from app.domains.leads.models import Lead
    from app.domains.leads.schemas import LeadCreate
    from app.domains.proposals.models import Proposal
    from app.shared.labels import STAGE_LABELS

    assert models.Lead is Lead
    assert models.User is User
    assert models.AiSettings is AiSettings
    assert models.Proposal is Proposal
    assert models.Invoice is Invoice
    assert models.LeadCreate is LeadCreate
    assert models.STAGE_LABELS is STAGE_LABELS
