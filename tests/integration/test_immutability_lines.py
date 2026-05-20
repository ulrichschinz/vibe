"""Phase 4/10 — line-item immutability after finalize.

Covers the SQLAlchemy event listeners for INSERT/DELETE on InvoiceLineItem
when the parent invoice is past draft (R-03).
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlmodel import Session

from app.domains.billing.models import InvoiceLineItem, InvoiceStatus
from services.invoicing.finalize import FinalizeOptions, finalize_invoice
from services.invoicing.immutability import ImmutableInvoiceError
from tests.fixtures.factories import (
    make_draft_invoice,
    make_issuer,
    make_lead_de_b2b,
)


def _opts():
    return FinalizeOptions(today=date(2026, 5, 9))


@pytest.mark.integration
def test_cannot_insert_line_after_finalize(session: Session):
    make_issuer(session)
    lead = make_lead_de_b2b(session)
    inv = make_draft_invoice(session, lead)
    f = finalize_invoice(session, inv.id, options=_opts())

    new_line = InvoiceLineItem(
        invoice_id=f.id,
        position=99,
        description="Geheim hinzugefügt",
        quantity=Decimal("1"),
        unit="Std",
        unit_price_net=Decimal("10000"),
        vat_rate=Decimal("19"),
        vat_code="S",
        line_net=Decimal("10000.00"),
        line_vat=Decimal("1900.00"),
        line_gross=Decimal("11900.00"),
    )
    session.add(new_line)
    with pytest.raises(Exception):  # ImmutableInvoiceError or sqlite ABORT
        session.commit()
    session.rollback()


@pytest.mark.integration
def test_cannot_delete_line_after_finalize(session: Session):
    make_issuer(session)
    lead = make_lead_de_b2b(session)
    inv = make_draft_invoice(session, lead)
    f = finalize_invoice(session, inv.id, options=_opts())

    line = session.exec(
        InvoiceLineItem.__table__.select().where(InvoiceLineItem.invoice_id == f.id)
    ).first()
    if line is not None:
        # Re-fetch via ORM to get a managed object
        from sqlmodel import select
        managed = session.exec(select(InvoiceLineItem).where(InvoiceLineItem.invoice_id == f.id)).first()
        session.delete(managed)
        with pytest.raises(Exception):
            session.commit()
        session.rollback()


@pytest.mark.integration
def test_can_still_insert_lines_on_draft(session: Session):
    """Sanity: the listener must not over-block — drafts must accept new lines."""
    make_issuer(session)
    lead = make_lead_de_b2b(session)
    inv = make_draft_invoice(session, lead)

    new_line = InvoiceLineItem(
        invoice_id=inv.id,
        position=2,
        description="Zweite Position",
        quantity=Decimal("1"),
        unit="Stk",
        unit_price_net=Decimal("50"),
        vat_rate=Decimal("19"),
        vat_code="S",
        line_net=Decimal("50.00"),
        line_vat=Decimal("9.50"),
        line_gross=Decimal("59.50"),
    )
    session.add(new_line)
    session.commit()  # must succeed
