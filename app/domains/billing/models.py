"""billing domain — own table schema (compliance bounded context).

Scaling-roadmap Schritt 4 (move-not-rewrite, **compliance-critical**):
`IssuerProfile`, `Invoice`, `InvoiceLineItem`, `InvoiceNumberSequence`,
`ViesAuditEntry`, `IntegrityCheckRun` + their enums move here from the
pre-split `models.py` **byte-identical** — field names, table names,
constraints, `__table_args__` and hash/immutability-relevant columns are
unchanged. Any drift here would break the 90 % invoicing suite /
hashchain / immutability triggers. `INVOICE_STATUS_ORDER` is billing data
and stays; the label dicts moved to `app.shared.labels`.

`IssuerProfile` (Rechnungssteller-Stammdaten) belongs to billing — it is
the source of the `BillingOrder.issuer{}` snapshot (Schritt 5). Soft-FK
`Invoice.lead_id` stays (no cascade); all cross-table references are SQLite
string FKs, never Python imports — so the end-state hardest rule
(`domains/billing/* ↛ domains/*` / `models`) is satisfiable. The
`_snapshot_customer()` `Lead` read is the only remaining inward reach and
is replaced by the `BillingOrder` contract in Schritt 5 (not this PR).
"""

from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from sqlalchemy import Column, Date, Index, Numeric, Text, UniqueConstraint
from sqlmodel import Field

from app.core.db import SQLModel


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
    subtotal_net: Optional[Decimal] = Field(
        default=None, sa_column=Column(Numeric(12, 2), nullable=True)
    )
    vat_total: Optional[Decimal] = Field(
        default=None, sa_column=Column(Numeric(12, 2), nullable=True)
    )
    total_gross: Optional[Decimal] = Field(
        default=None, sa_column=Column(Numeric(12, 2), nullable=True)
    )
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
            return json.loads(self.vat_breakdown_json)  # type: ignore[no-any-return]
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
