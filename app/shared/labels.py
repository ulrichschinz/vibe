"""app.shared.labels — display labels as data ("labels sind Daten").

Scaling-roadmap Schritt 4: the label dicts move out of `models.py` to a
single cross-cutting data module; the Jinja-global injection in the route
modules is repointed here (dashboard characterization test covers
regressions). The dicts are kept **enum-keyed and byte-identical** to the
pre-split definitions: e.g. `templates/invoices/list.html` iterates
`INVOICE_STATUS_LABELS.items()` and uses `st.value`, so the keys must stay
enum members — a pure move, zero behaviour change.

Note: this module imports the domain/kernel enums it labels. The end-state
`shared ↛ domains` contract edge is *not* active in Schritt 4 (the roadmap
sharpens the full edge set in Schritt 5/7; `app.*` is not yet an
import-linter root package). Decoupling these to string/i18n keys is the
roadmap's explicit later option ("oder JSON/i18n"), not a Schritt-4
behaviour change.
"""

from __future__ import annotations

from app.core.ai_settings import AiProvider
from app.core.identity import UserRole
from app.domains.billing.models import InvoiceKind, InvoiceStatus
from app.domains.leads.models import (
    BantValue,
    LeadSource,
    LeadStage,
    LeadType,
    ReadinessLevel,
)
from app.domains.proposals.models import ProposalStatus

AI_PROVIDER_LABELS = {
    AiProvider.anthropic: "Anthropic (Claude)",
}

USER_ROLE_LABELS = {
    UserRole.admin: "Admin",
    UserRole.editor: "Editor",
    UserRole.viewer: "Leser",
}

LEAD_TYPE_LABELS = {
    LeadType.direct: "Direkt",
    LeadType.partner: "Partner / Alliance",
}

STAGE_LABELS = {
    LeadStage.new: "Neu",
    LeadStage.contacted: "Kontaktiert",
    LeadStage.proposal_sent: "Angebot gesendet",
    LeadStage.negotiating: "In Verhandlung",
    LeadStage.won: "Gewonnen",
    LeadStage.lost: "Verloren",
}

SOURCE_LABELS = {
    LeadSource.website: "Website",
    LeadSource.referral: "Empfehlung",
    LeadSource.agent: "KI-Agent",
    LeadSource.manual: "Manuell",
    LeadSource.linkedin: "LinkedIn",
}

BANT_LABELS = {
    BantValue.yes: "Ja",
    BantValue.open: "Offen",
    BantValue.no: "Nein",
}

READINESS_LABELS = {
    ReadinessLevel.high: "Hoch",
    ReadinessLevel.medium: "Mittel",
    ReadinessLevel.low: "Niedrig",
}

PROPOSAL_STATUS_LABELS = {
    ProposalStatus.draft: "Entwurf",
    ProposalStatus.sent: "Gesendet",
    ProposalStatus.accepted: "Angenommen",
    ProposalStatus.declined: "Abgelehnt",
}

INVOICE_STATUS_LABELS = {
    InvoiceStatus.draft: "Entwurf",
    InvoiceStatus.finalized: "Finalisiert",
    InvoiceStatus.sent: "Versendet",
    InvoiceStatus.paid: "Bezahlt",
    InvoiceStatus.cancelled: "Storniert",
}

INVOICE_KIND_LABELS = {
    InvoiceKind.invoice: "Rechnung",
    InvoiceKind.storno: "Stornorechnung",
}
