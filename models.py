from __future__ import annotations
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, String, Text, Integer, ForeignKey, Numeric, Date, DateTime, Boolean, UniqueConstraint, Index
from typing import Optional, List
from datetime import datetime, date
from decimal import Decimal
from enum import Enum
import json


# ── AI Settings ─────────────────────────────────────────────────────────────

class AiProvider(str, Enum):
    anthropic = "anthropic"


AI_PROVIDER_LABELS = {
    AiProvider.anthropic: "Anthropic (Claude)",
}


class AiSettings(SQLModel, table=True):
    id: int = Field(default=1, primary_key=True)  # Singleton
    provider: AiProvider = AiProvider.anthropic
    api_key: str = ""
    model: str = "claude-sonnet-4-6"
    is_active: bool = False


# ── Users & Auth ────────────────────────────────────────────────────────────

class UserRole(str, Enum):
    admin = "admin"
    editor = "editor"
    viewer = "viewer"


USER_ROLE_LABELS = {
    UserRole.admin: "Admin",
    UserRole.editor: "Editor",
    UserRole.viewer: "Leser",
}


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    email: str = Field(unique=True, index=True)
    name: str
    hashed_password: str
    role: UserRole = UserRole.editor
    is_active: bool = True


class ApiKey(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    label: str
    key_hash: str
    is_active: bool = True
    created_by_id: int = Field(foreign_key="user.id")
    last_used_at: Optional[datetime] = None


# ── Leads ────────────────────────────────────────────────────────────────────

class LeadSource(str, Enum):
    website = "website"
    referral = "referral"
    agent = "agent"
    manual = "manual"
    linkedin = "linkedin"


class LeadStage(str, Enum):
    new = "new"
    contacted = "contacted"
    proposal_sent = "proposal_sent"
    negotiating = "negotiating"
    won = "won"
    lost = "lost"


class LeadType(str, Enum):
    direct = "direct"
    partner = "partner"


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

STAGE_ORDER = [
    LeadStage.new,
    LeadStage.contacted,
    LeadStage.proposal_sent,
    LeadStage.negotiating,
    LeadStage.won,
    LeadStage.lost,
]


class BantValue(str, Enum):
    yes = "yes"
    open = "open"
    no = "no"


BANT_LABELS = {
    BantValue.yes: "Ja",
    BantValue.open: "Offen",
    BantValue.no: "Nein",
}


class ReadinessLevel(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


READINESS_LABELS = {
    ReadinessLevel.high: "Hoch",
    ReadinessLevel.medium: "Mittel",
    ReadinessLevel.low: "Niedrig",
}


_BANT_SCORE = {
    BantValue.yes.value: 25,
    BantValue.open.value: 10,
    BantValue.no.value: 0,
}


class Lead(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    name: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True))
    company: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True))
    email: Optional[str] = None
    phone: Optional[str] = None
    salutation: Optional[str] = None    # "Frau" / "Herr" / ""
    source: LeadSource = LeadSource.manual
    lead_type: LeadType = Field(default=LeadType.direct)
    owner_id: Optional[int] = Field(default=None, foreign_key="user.id")
    stage: LeadStage = LeadStage.new
    notes: Optional[str] = None
    tags: Optional[str] = None          # JSON array string
    agent_metadata: Optional[str] = None  # JSON object string
    plan_text: Optional[str] = Field(default=None, sa_column=Column(Text))
    # Invoicing extension (added 2026-05): for §14 UStG-compliant recipient block.
    street: Optional[str] = None
    street2: Optional[str] = None
    postal_code: Optional[str] = None
    city: Optional[str] = None
    country_code: Optional[str] = Field(default="DE")  # ISO-3166-1 alpha-2
    vat_id: Optional[str] = None                       # USt-IdNr.
    is_business: Optional[bool] = Field(default=True)
    tax_country: Optional[str] = None                  # falls abweichend von country_code
    # Wiedervorlage / Qualifizierung (added 2026-05).
    snooze_until: Optional[date] = Field(default=None, sa_column=Column(Date, nullable=True))
    bant_budget: Optional[str] = None     # BantValue
    bant_authority: Optional[str] = None
    bant_need: Optional[str] = None
    bant_timing: Optional[str] = None
    ai_readiness: Optional[str] = None    # ReadinessLevel
    pain_points: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    next_action: Optional[str] = None
    next_action_date: Optional[date] = Field(default=None, sa_column=Column(Date, nullable=True))

    def display_name(self) -> str:
        return self.name or self.company or "—"

    def is_snoozed(self, today: Optional[date] = None) -> bool:
        if not self.snooze_until:
            return False
        ref = today or date.today()
        return self.snooze_until > ref

    def bant_score(self) -> int:
        return sum(
            _BANT_SCORE.get(v, 0)
            for v in (self.bant_budget, self.bant_authority, self.bant_need, self.bant_timing)
        )

    def get_tags(self) -> list:
        if not self.tags:
            return []
        try:
            return json.loads(self.tags)
        except Exception:
            return []

    def get_agent_metadata(self) -> dict:
        if not self.agent_metadata:
            return {}
        try:
            return json.loads(self.agent_metadata)
        except Exception:
            return {}


class Note(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    lead_id: int = Field(foreign_key="lead.id")
    body: str = Field(sa_column=Column(Text))


class PlanningMessage(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    lead_id: int = Field(foreign_key="lead.id")
    role: str          # "user" | "assistant"
    content: str = Field(sa_column=Column(Text))


class ProposalStatus(str, Enum):
    draft = "draft"
    sent = "sent"
    accepted = "accepted"
    declined = "declined"


PROPOSAL_STATUS_LABELS = {
    ProposalStatus.draft: "Entwurf",
    ProposalStatus.sent: "Gesendet",
    ProposalStatus.accepted: "Angenommen",
    ProposalStatus.declined: "Abgelehnt",
}

DEFAULT_SERVICES = [
    {
        "id": "strategy",
        "eyebrow": "// 01",
        "title": "Strategie & Consulting",
        "enabled": True,
        "description": "",
        "deliverables": ["Use-Case-Assessment", "Roadmap & Wirtschaftlichkeit", "Make-or-Buy-Entscheidung"],
        "price": None,
    },
    {
        "id": "change",
        "eyebrow": "// 02",
        "title": "Change-Begleitung",
        "enabled": False,
        "description": "",
        "deliverables": ["Sparring für Führungskräfte", "Team-Workshops", "Kommunikation & Befähigung"],
        "price": None,
    },
    {
        "id": "tech",
        "eyebrow": "// 03",
        "title": "Technische Umsetzung",
        "enabled": False,
        "description": "",
        "deliverables": ["Agenten-Architektur", "Knowledge-Graph-Setup", "Integration & Betrieb"],
        "price": None,
    },
]


class Proposal(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    lead_id: int = Field(foreign_key="lead.id")
    number: str               # AR-2026-001
    title: str
    intro_text: Optional[str] = None
    services: str = Field(default=json.dumps(DEFAULT_SERVICES))
    total_value: Optional[float] = None
    duration: Optional[str] = None
    payment_terms: Optional[str] = "50 % bei Projektstart, 50 % bei Abschluss"
    travel_costs: Optional[str] = "Reisekosten werden nach Aufwand und vorheriger Abstimmung gesondert in Rechnung gestellt."
    validity_days: int = 30
    status: ProposalStatus = ProposalStatus.draft
    sent_at: Optional[datetime] = None
    pdf_path: Optional[str] = None

    def get_services(self) -> list:
        try:
            return json.loads(self.services)
        except Exception:
            return DEFAULT_SERVICES[:]

    def get_enabled_services(self) -> list:
        return [s for s in self.get_services() if s.get("enabled")]


# ── API schemas (no table=True) ────────────────────────────────────────────

class LeadCreate(SQLModel):
    name: Optional[str] = None
    company: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    source: LeadSource = LeadSource.manual
    lead_type: LeadType = LeadType.direct
    owner_id: Optional[int] = None
    notes: Optional[str] = None
    tags: Optional[list] = None
    agent_metadata: Optional[dict] = None
    snooze_until: Optional[date] = None
    bant_budget: Optional[BantValue] = None
    bant_authority: Optional[BantValue] = None
    bant_need: Optional[BantValue] = None
    bant_timing: Optional[BantValue] = None
    ai_readiness: Optional[ReadinessLevel] = None
    pain_points: Optional[str] = None
    next_action: Optional[str] = None
    next_action_date: Optional[date] = None


class LeadRead(SQLModel):
    id: int
    created_at: datetime
    updated_at: datetime
    name: Optional[str]
    company: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    source: LeadSource
    lead_type: LeadType
    owner_id: Optional[int] = None
    stage: LeadStage
    notes: Optional[str]
    snooze_until: Optional[date] = None
    bant_budget: Optional[BantValue] = None
    bant_authority: Optional[BantValue] = None
    bant_need: Optional[BantValue] = None
    bant_timing: Optional[BantValue] = None
    ai_readiness: Optional[ReadinessLevel] = None
    pain_points: Optional[str] = None
    next_action: Optional[str] = None
    next_action_date: Optional[date] = None


class LeadPatch(SQLModel):
    name: Optional[str] = None
    company: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    stage: Optional[LeadStage] = None
    lead_type: Optional[LeadType] = None
    owner_id: Optional[int] = None
    notes: Optional[str] = None
    snooze_until: Optional[date] = None
    bant_budget: Optional[BantValue] = None
    bant_authority: Optional[BantValue] = None
    bant_need: Optional[BantValue] = None
    bant_timing: Optional[BantValue] = None
    ai_readiness: Optional[ReadinessLevel] = None
    pain_points: Optional[str] = None
    next_action: Optional[str] = None
    next_action_date: Optional[date] = None


# ── Invoicing ──────────────────────────────────────────────────────────────
#
# §14 UStG-konformes Rechnungsmodul. Aggregat-Pattern: Invoice + InvoiceLineItem.
# Beim Finalize werden Stammdaten als Snapshot (iss_*, cust_*) eingefroren.
# Nach Finalize sind die meisten Felder unveränderlich (DB-Trigger + App-Layer).


class IssuerProfile(SQLModel, table=True):
    """Singleton (id=1). Stammdaten des Rechnungsausstellers."""
    id: int = Field(default=1, primary_key=True)
    legal_name: str
    street: str
    postal_code: str
    city: str
    country_code: str = "DE"
    steuernummer: Optional[str] = None
    ust_id: Optional[str] = None  # USt-IdNr., z. B. DE123456789
    is_kleinunternehmer: bool = False
    bank_holder: str = ""
    bank_iban: str = ""
    bank_bic: Optional[str] = None
    contact_email: str = ""
    contact_phone: Optional[str] = None
    default_payment_terms_days: int = 14
    default_payment_terms_text: str = "Zahlbar innerhalb 14 Tagen ohne Abzug."
    signature_block: Optional[str] = None
    logo_path: Optional[str] = None
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class InvoiceStatus(str, Enum):
    draft = "draft"
    finalized = "finalized"
    sent = "sent"
    paid = "paid"
    cancelled = "cancelled"


INVOICE_STATUS_LABELS = {
    InvoiceStatus.draft: "Entwurf",
    InvoiceStatus.finalized: "Finalisiert",
    InvoiceStatus.sent: "Versendet",
    InvoiceStatus.paid: "Bezahlt",
    InvoiceStatus.cancelled: "Storniert",
}

INVOICE_STATUS_ORDER = [
    InvoiceStatus.draft,
    InvoiceStatus.finalized,
    InvoiceStatus.sent,
    InvoiceStatus.paid,
    InvoiceStatus.cancelled,
]


class InvoiceKind(str, Enum):
    invoice = "invoice"
    storno = "storno"


INVOICE_KIND_LABELS = {
    InvoiceKind.invoice: "Rechnung",
    InvoiceKind.storno: "Stornorechnung",
}


class Invoice(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("fiscal_year", "sequence_number", name="uq_invoice_year_seq"),
        Index("ix_invoice_status", "status"),
        Index("ix_invoice_lead_id", "lead_id"),
        # `number` already gets an index via Field(index=True, unique=True).
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    status: InvoiceStatus = InvoiceStatus.draft
    kind: InvoiceKind = InvoiceKind.invoice

    # Numbering — assigned at finalize, NULL during draft.
    number: Optional[str] = Field(default=None, index=True, unique=True)
    fiscal_year: Optional[int] = None
    sequence_number: Optional[int] = None

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    finalized_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None

    # Dates (date, not datetime)
    invoice_date: Optional[date] = Field(default=None, sa_column=Column(Date, nullable=True))
    leistungsdatum: Optional[date] = Field(default=None, sa_column=Column(Date, nullable=True))
    due_date: Optional[date] = Field(default=None, sa_column=Column(Date, nullable=True))

    currency: str = "EUR"
    customer_reference: Optional[str] = None

    # Soft references
    lead_id: Optional[int] = Field(default=None, foreign_key="lead.id")
    related_invoice_id: Optional[int] = Field(default=None, foreign_key="invoice.id")
    proposal_id: Optional[int] = Field(default=None, foreign_key="proposal.id")

    # Idempotency
    idempotency_key: Optional[str] = Field(default=None, unique=True)

    # Snapshot — issuer (frozen at finalize)
    iss_legal_name: Optional[str] = None
    iss_street: Optional[str] = None
    iss_postal_code: Optional[str] = None
    iss_city: Optional[str] = None
    iss_country_code: Optional[str] = None
    iss_steuernummer: Optional[str] = None
    iss_ust_id: Optional[str] = None
    iss_is_kleinunternehmer: Optional[bool] = None
    iss_bank_holder: Optional[str] = None
    iss_bank_iban: Optional[str] = None
    iss_bank_bic: Optional[str] = None
    iss_contact_email: Optional[str] = None
    iss_contact_phone: Optional[str] = None

    # Snapshot — customer (frozen at finalize)
    cust_legal_name: Optional[str] = None
    cust_company: Optional[str] = None
    cust_salutation: Optional[str] = None
    cust_street: Optional[str] = None
    cust_street2: Optional[str] = None
    cust_postal_code: Optional[str] = None
    cust_city: Optional[str] = None
    cust_country_code: Optional[str] = None
    cust_vat_id: Optional[str] = None
    cust_is_business: Optional[bool] = None
    cust_email: Optional[str] = None

    # Computed totals (Decimal 12,2)
    subtotal_net: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(12, 2), nullable=True))
    vat_total: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(12, 2), nullable=True))
    total_gross: Optional[Decimal] = Field(default=None, sa_column=Column(Numeric(12, 2), nullable=True))
    vat_breakdown_json: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))

    # Legal-hint flags
    hint_kleinunternehmer: bool = False
    hint_reverse_charge: bool = False
    hint_third_country: bool = False

    # Payment
    payment_terms_text: Optional[str] = None

    # Document title / intro (analog Proposal)
    title: Optional[str] = None
    intro_text: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))

    # Archive
    archive_path_pdf: Optional[str] = None
    archive_path_xml: Optional[str] = None
    hash_sha256: Optional[str] = None
    hash_prev: Optional[str] = None
    hash_algo: str = "sha256-v1"

    # VIES
    vies_audit_id: Optional[int] = Field(default=None, foreign_key="viesauditentry.id")

    def get_vat_breakdown(self) -> list:
        if not self.vat_breakdown_json:
            return []
        try:
            return json.loads(self.vat_breakdown_json)
        except Exception:
            return []


class InvoiceLineItem(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("invoice_id", "position", name="uq_line_invoice_position"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    invoice_id: int = Field(foreign_key="invoice.id")
    position: int                         # 1-based, gap-free per invoice
    description: str = Field(sa_column=Column(Text))
    quantity: Decimal = Field(sa_column=Column(Numeric(12, 4), nullable=False))
    unit: str = "Std"                     # Std | Tag | Stk | Pauschal
    unit_price_net: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
    vat_rate: Decimal = Field(sa_column=Column(Numeric(5, 2), nullable=False))
    vat_code: str = "S"                   # EN16931: S | AE | E | G | O | Z
    line_net: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
    line_vat: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))
    line_gross: Decimal = Field(sa_column=Column(Numeric(12, 2), nullable=False))


class InvoiceNumberSequence(SQLModel, table=True):
    """Race-safe Counter pro Geschäftsjahr. Update unter BEGIN IMMEDIATE."""
    fiscal_year: int = Field(primary_key=True)
    prefix: str = "RE"
    last_sequence: int = 0
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ViesResponseStatus(str, Enum):
    valid = "valid"
    invalid = "invalid"
    service_unavailable = "service_unavailable"
    override = "override"


class ViesAuditEntry(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    invoice_id: Optional[int] = Field(default=None, foreign_key="invoice.id")
    queried_at: datetime = Field(default_factory=datetime.utcnow)
    vat_id_queried: str
    country_code: str
    response_status: ViesResponseStatus
    raw_response_json: str = Field(sa_column=Column(Text))
    queried_by_user_id: Optional[int] = Field(default=None, foreign_key="user.id")
    override_reason: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))


class IntegrityCheckResult(str, Enum):
    ok = "ok"
    mismatch = "mismatch"
    error = "error"


class IntegrityCheckRun(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    ran_at: datetime = Field(default_factory=datetime.utcnow)
    scanned_count: int = 0
    mismatches_json: str = Field(default="[]", sa_column=Column(Text))
    result: IntegrityCheckResult = IntegrityCheckResult.ok
    notes: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
