"""leads domain — billing export seam (Scaling-roadmap Schritt 5).

The CRM side of the ``BillingOrder`` contract: project a ``Lead`` into the
immutable ``BillingCustomer`` snapshot that billing consumes instead of
reading ``Lead`` directly. This is the replacement for the inward reach in
``services.invoicing.finalize._snapshot_customer()``.

``build_billing_customer`` is a *pure projection*: it returns the raw
``Lead`` field values (``name`` and ``company`` kept separate). The
``cust_legal_name = name or company`` precedence and the "explicit
invoice-level value wins" merge stay in the consumer, so behaviour is
byte-equivalent to the pre-Schritt-5 in-finalize snapshot.

Imports stay contract-conformant: own domain (`Lead`) + `app.contracts`
only — no billing/other-domain import.
"""

from __future__ import annotations

from typing import Optional

from sqlmodel import Session

from app.contracts.billing_order import BillingCustomer
from app.domains.leads.models import Lead


def build_billing_customer(session: Session, lead_id: Optional[int]) -> Optional[BillingCustomer]:
    """Snapshot the bound ``Lead`` into a ``BillingCustomer``.

    Returns ``None`` when no lead is bound or the lead no longer exists —
    mirroring the old ``session.get(Lead, invoice.lead_id) if
    invoice.lead_id else None`` followed by the ``lead is None`` early
    return in ``_snapshot_customer()`` (no auto-fill, explicit invoice
    fields stand).
    """
    if lead_id is None:
        return None
    lead = session.get(Lead, lead_id)
    if lead is None:
        return None
    return BillingCustomer(
        name=lead.name,
        company=lead.company,
        salutation=lead.salutation,
        street=lead.street,
        street2=lead.street2,
        postal_code=lead.postal_code,
        city=lead.city,
        country_code=lead.country_code,
        vat_id=lead.vat_id,
        is_business=lead.is_business,
        email=lead.email,
    )
