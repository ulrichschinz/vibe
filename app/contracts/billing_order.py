"""app.contracts.billing_order — the published BillingOrder DTO.

Scaling-roadmap Schritt 5: the explicit, anti-corruption seam between the
CRM and the (extraction-ready) billing bounded context. The CRM side builds
this immutable snapshot at *export* time; billing consumes the snapshot and
never reaches back into CRM tables. This replaces the direct ``Lead`` read
in ``services.invoicing.finalize._snapshot_customer()``.

Field reconciliation (Verifikation 2a of the roadmap): the model must carry
*everything* that ``_snapshot_customer()`` and the ``IssuerProfile`` read in
``finalize.py`` deliver today — see ARCHITECTURE.md → "Invoicing↔CRM-Naht".

- ``BillingCustomer`` mirrors the exact 11 ``Lead`` fields
  ``_snapshot_customer()`` copies (incl. ``name`` *and* ``company``
  separately so the ``cust_legal_name = name or company`` precedence is
  reproducible on the consumer side, byte-equivalent behaviour).
- ``BillingIssuer`` / ``BillingLine`` / ``BillingMeta`` carry everything the
  issuer / line / header reads deliver, so a later physical split needs no
  contract rework. **Only the customer portion is wired in Schritt 5** — the
  *single* behaviour change the move-not-rewrite plan permits; issuer and
  lines stay billing-internal reads (allowed edges) until a later step.

Pure pydantic, dependency-free (stdlib + pydantic only) — enforced by the
import-linter ``contracts ↛ domains/core/interfaces`` end-state rule. The
models are ``frozen`` (immutable snapshot — billing must not mutate it).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class _Frozen(BaseModel):
    """Immutable snapshot base — billing consumes, never mutates."""

    model_config = ConfigDict(frozen=True)


class BillingCustomer(_Frozen):
    """Customer snapshot — exactly the ``Lead`` fields ``_snapshot_customer()``
    reads today (`Lead.{salutation,street,street2,postal_code,city,
    country_code,vat_id,is_business,email,name,company}`). ``name`` and
    ``company`` are kept separate so the consumer can reproduce the
    ``cust_legal_name = name or company`` precedence verbatim.
    """

    name: Optional[str] = None
    company: Optional[str] = None
    salutation: Optional[str] = None
    street: Optional[str] = None
    street2: Optional[str] = None
    postal_code: Optional[str] = None
    city: Optional[str] = None
    country_code: Optional[str] = None
    vat_id: Optional[str] = None
    is_business: Optional[bool] = None
    email: Optional[str] = None


class BillingIssuer(_Frozen):
    """Issuer snapshot — everything ``finalize._snapshot_issuer()`` plus the
    payment-terms / signature reads copy off ``IssuerProfile``. Defined for
    contract completeness (extraction-ready); not wired in Schritt 5 because
    ``IssuerProfile`` is billing-owned (its read is an allowed edge).
    """

    legal_name: str
    street: str
    postal_code: str
    city: str
    country_code: str = "DE"
    steuernummer: Optional[str] = None
    ust_id: Optional[str] = None
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


class BillingLine(_Frozen):
    """One billable line. Mirrors the ``InvoiceLineItem`` inputs the VAT
    engine consumes (``LineInput``). Defined for contract completeness.
    """

    position: int
    description: str
    quantity: Decimal
    unit: Optional[str] = None
    unit_price_net: Decimal
    vat_rate_hint: Optional[Decimal] = None


class BillingMeta(_Frozen):
    """Header / reference data the invoice carries (title, performance date,
    payment target, references). Defined for contract completeness.
    """

    title: Optional[str] = None
    leistungsdatum: Optional[date] = None
    currency: str = "EUR"
    customer_reference: Optional[str] = None
    payment_terms_text: Optional[str] = None


class BillingOrder(_Frozen):
    """The explicit "billable order" the CRM exports. Carries an immutable
    snapshot so billing never reaches back into CRM/`domains/*`.
    """

    order_ref: str
    idempotency_key: Optional[str] = None
    issuer: Optional[BillingIssuer] = None
    customer: Optional[BillingCustomer] = None
    lines: list[BillingLine] = Field(default_factory=list)
    meta: BillingMeta = Field(default_factory=BillingMeta)
