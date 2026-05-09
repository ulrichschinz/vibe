"""Application-layer guard against editing finalized invoices (R-03).

Belt-and-braces with the SQLite triggers in ``database.py``. The ORM-level
listener catches edits *before* SQL is sent so callers see a Python exception
with a helpful message rather than a generic SQLite ABORT.

Activation: import this module once at app start (e.g. in ``main.py``). The
listener is registered as a side-effect of import.
"""
from __future__ import annotations

from sqlalchemy import event, inspect

from models import Invoice, InvoiceLineItem, InvoiceStatus


class ImmutableInvoiceError(Exception):
    """Raised when code tries to mutate a finalized invoice."""


# Columns that may NEVER change after a finalize (matches database.py trigger).
_PROTECTED_INVOICE_ATTRS = frozenset({
    "number", "fiscal_year", "sequence_number",
    "invoice_date", "leistungsdatum", "due_date",
    "currency", "lead_id", "related_invoice_id", "proposal_id",
    "iss_legal_name", "iss_street", "iss_postal_code", "iss_city",
    "iss_country_code", "iss_steuernummer", "iss_ust_id",
    "iss_is_kleinunternehmer", "iss_bank_holder", "iss_bank_iban",
    "iss_bank_bic", "iss_contact_email", "iss_contact_phone",
    "cust_legal_name", "cust_company", "cust_salutation", "cust_street",
    "cust_street2", "cust_postal_code", "cust_city", "cust_country_code",
    "cust_vat_id", "cust_is_business", "cust_email",
    "subtotal_net", "vat_total", "total_gross", "vat_breakdown_json",
    "hint_kleinunternehmer", "hint_reverse_charge", "hint_third_country",
    "payment_terms_text", "title", "intro_text",
    "archive_path_pdf", "archive_path_xml",
    "hash_sha256", "hash_prev", "hash_algo",
    "kind",
})


def _previous_status(target: Invoice) -> InvoiceStatus:
    """Return the *old* status as recorded by the SQLAlchemy attribute history."""
    state = inspect(target)
    hist = state.attrs.status.history
    if hist.deleted:
        return hist.deleted[0]
    return target.status


@event.listens_for(Invoice, "before_update")
def _block_invoice_edit_after_finalize(mapper, connection, target):
    old_status = _previous_status(target)
    if old_status == InvoiceStatus.draft:
        # We're either staying in draft or transitioning out of it (e.g. finalize).
        # Either way: allow.
        return

    state = inspect(target)
    changed = []
    for attr_name in _PROTECTED_INVOICE_ATTRS:
        attr_state = state.attrs.get(attr_name)
        if attr_state is None:
            continue
        if attr_state.history.has_changes():
            changed.append(attr_name)
    if changed:
        raise ImmutableInvoiceError(
            f"Invoice {target.id} is {old_status.value}; cannot modify: {sorted(changed)}"
        )


@event.listens_for(InvoiceLineItem, "before_update")
def _block_line_edit_after_finalize(mapper, connection, target):
    """Reject any UPDATE on a line item whose parent invoice is past draft."""
    parent_status = connection.execute(
        Invoice.__table__.select().with_only_columns(Invoice.status).where(Invoice.id == target.invoice_id)
    ).scalar()
    if parent_status is None:
        return
    if parent_status != InvoiceStatus.draft.value and parent_status != InvoiceStatus.draft:
        raise ImmutableInvoiceError(
            f"Invoice {target.invoice_id} is {parent_status}; line items are immutable"
        )


@event.listens_for(InvoiceLineItem, "before_insert")
def _block_line_insert_after_finalize(mapper, connection, target):
    parent_status = connection.execute(
        Invoice.__table__.select().with_only_columns(Invoice.status).where(Invoice.id == target.invoice_id)
    ).scalar()
    if parent_status is None:
        return
    if parent_status != InvoiceStatus.draft.value and parent_status != InvoiceStatus.draft:
        raise ImmutableInvoiceError(
            f"Cannot add lines to invoice {target.invoice_id}: status is {parent_status}"
        )


@event.listens_for(InvoiceLineItem, "before_delete")
def _block_line_delete_after_finalize(mapper, connection, target):
    parent_status = connection.execute(
        Invoice.__table__.select().with_only_columns(Invoice.status).where(Invoice.id == target.invoice_id)
    ).scalar()
    if parent_status is None:
        return
    if parent_status != InvoiceStatus.draft.value and parent_status != InvoiceStatus.draft:
        raise ImmutableInvoiceError(
            f"Cannot delete lines from invoice {target.invoice_id}: status is {parent_status}"
        )
