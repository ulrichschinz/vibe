"""Backward-compat shim + single table-metadata aggregation module.

Scaling-roadmap Schritt 4 (Move-Vertrag). `models.py` no longer *defines*
anything: the 13 SQLModel tables, their enums, the Pydantic schemas and the
label dicts have moved to their final homes:

  app.core.identity            User, UserRole, ApiKey
  app.core.ai_settings         AiProvider, AiSettings
  app.domains.leads.models     Lead, Note, PlanningMessage, lead enums,
                               STAGE_ORDER
  app.domains.leads.schemas    LeadCreate, LeadRead, LeadPatch
  app.domains.proposals.models Proposal, ProposalStatus, DEFAULT_SERVICES
  app.domains.billing.models   IssuerProfile, Invoice, InvoiceLineItem,
                               InvoiceNumberSequence, ViesAuditEntry,
                               IntegrityCheckRun, billing enums,
                               INVOICE_STATUS_ORDER
  app.shared.labels            *_LABELS dicts

This module stays the **single aggregation module** of the Move-Vertrag:
importing it imports every model module in one deterministic order, so the
full set of tables is registered on the shared `SQLModel.metadata` exactly
once (no `Table already defined`). `database.create_db()` keeps this
registry-bootstrap `import models` before `create_all` — that (plus the
test suite) is the only `models` reach left. `database` is a top-level
module, **not** an import-linter root_package, so the bootstrap is
invisible to the contracts.

Schritt 8 (ADR-009 §F) repointed every production **name-re-export**
consumer (`main.py`, `services/*`, the moved `app.interfaces.*` handlers)
onto `app.*` directly — **no `services`/`routes`/`app` module imports this
shim's names anymore**. It survives as the **test-facing** re-export so the
frozen Schritt-0.5 characterization / integration / unit suite keeps
``from models import …`` working unchanged (0-tests-diff).

It re-exports **explicitly** (no `import *`) with an `__all__` so IDE/AST
resolution stays unambiguous. The shim-death is enforced prod-scoped: the
Schritt-8 interface/domain/core import-linter edge set forbids any path to
`domains/*/models` from `interfaces`/`core`/cross-domain, and the bare-
`models`-module rule is grep-verified by construction (a single `.py`
module is not a valid grimp `root_package` — the documented Schritt-5
limitation). Physical file deletion + the test-import migration is a
deferred follow-up step (Churn owned by no step — Schritt-1 precedent).
"""

from __future__ import annotations

# 1 — kernel identity / config tables
from app.core.identity import ApiKey, User, UserRole
from app.core.ai_settings import AiProvider, AiSettings

# 2 — leads domain (models then schemas)
from app.domains.leads.models import (
    BantValue,
    Lead,
    LeadSource,
    LeadStage,
    LeadType,
    Note,
    PlanningMessage,
    ReadinessLevel,
    STAGE_ORDER,
)
from app.domains.leads.schemas import LeadCreate, LeadPatch, LeadRead

# 3 — proposals domain
from app.domains.proposals.models import (
    DEFAULT_SERVICES,
    Proposal,
    ProposalStatus,
)

# 4 — billing domain (own table schema)
from app.domains.billing.models import (
    INVOICE_STATUS_ORDER,
    IntegrityCheckResult,
    IntegrityCheckRun,
    Invoice,
    InvoiceKind,
    InvoiceLineItem,
    InvoiceNumberSequence,
    InvoiceStatus,
    IssuerProfile,
    ViesAuditEntry,
    ViesResponseStatus,
)

# 5 — labels (data; importing also pulls every enum above)
from app.shared.labels import (
    AI_PROVIDER_LABELS,
    BANT_LABELS,
    INVOICE_KIND_LABELS,
    INVOICE_STATUS_LABELS,
    LEAD_TYPE_LABELS,
    PROPOSAL_STATUS_LABELS,
    READINESS_LABELS,
    SOURCE_LABELS,
    STAGE_LABELS,
    USER_ROLE_LABELS,
)

__all__ = [
    # kernel
    "User", "UserRole", "ApiKey", "AiProvider", "AiSettings",
    # leads
    "Lead", "Note", "PlanningMessage",
    "LeadSource", "LeadStage", "LeadType", "BantValue", "ReadinessLevel",
    "STAGE_ORDER",
    "LeadCreate", "LeadRead", "LeadPatch",
    # proposals
    "Proposal", "ProposalStatus", "DEFAULT_SERVICES",
    # billing
    "IssuerProfile", "Invoice", "InvoiceLineItem", "InvoiceNumberSequence",
    "ViesAuditEntry", "IntegrityCheckRun",
    "InvoiceStatus", "InvoiceKind", "ViesResponseStatus",
    "IntegrityCheckResult", "INVOICE_STATUS_ORDER",
    # labels
    "AI_PROVIDER_LABELS", "USER_ROLE_LABELS", "LEAD_TYPE_LABELS",
    "STAGE_LABELS", "SOURCE_LABELS", "BANT_LABELS", "READINESS_LABELS",
    "PROPOSAL_STATUS_LABELS", "INVOICE_STATUS_LABELS", "INVOICE_KIND_LABELS",
]
