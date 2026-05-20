"""R-05 — Storno-Workflow."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlmodel import Session, select

from app.domains.billing.models import Invoice, InvoiceKind, InvoiceStatus
from services.invoicing.finalize import (
    FinalizeError,
    FinalizeOptions,
    create_storno,
    finalize_invoice,
)
from tests.fixtures.factories import make_draft_invoice, make_issuer, make_lead_de_b2b


def _opts():
    return FinalizeOptions(today=date(2026, 5, 9))


@pytest.mark.integration
def test_storno_creates_new_invoice_with_negative_amounts(session: Session):
    make_issuer(session)
    lead = make_lead_de_b2b(session)
    inv = make_draft_invoice(session, lead)
    f = finalize_invoice(session, inv.id, options=_opts())

    storno = create_storno(session, f.id, reason="Doppelt berechnet", options=_opts())

    assert storno.kind == InvoiceKind.storno
    assert storno.number != f.number
    assert storno.related_invoice_id == f.id
    assert storno.total_gross == -f.total_gross
    assert storno.subtotal_net == -f.subtotal_net
    # Original is cancelled but otherwise intact (R-05).
    original = session.get(Invoice, f.id)
    assert original.status == InvoiceStatus.cancelled
    assert original.cancelled_at is not None
    assert original.number == f.number  # number unchanged
    assert original.total_gross == f.total_gross  # totals unchanged


@pytest.mark.integration
def test_storno_customer_snapshot_matches_original(session: Session):
    make_issuer(session)
    lead = make_lead_de_b2b(session, name="Original Kunde")
    inv = make_draft_invoice(session, lead)
    f = finalize_invoice(session, inv.id, options=_opts())
    # Even if Lead changes, storno copies from original snapshot
    lead.name = "Anderer Name"
    session.add(lead)
    session.commit()
    storno = create_storno(session, f.id, options=_opts())
    assert storno.cust_legal_name == "Original Kunde"


@pytest.mark.integration
def test_cannot_storno_draft(session: Session):
    make_issuer(session)
    lead = make_lead_de_b2b(session)
    inv = make_draft_invoice(session, lead)
    with pytest.raises(FinalizeError, match="draft"):
        create_storno(session, inv.id, options=_opts())


@pytest.mark.integration
def test_cannot_storno_already_cancelled(session: Session):
    make_issuer(session)
    lead = make_lead_de_b2b(session)
    inv = make_draft_invoice(session, lead)
    f = finalize_invoice(session, inv.id, options=_opts())
    create_storno(session, f.id, options=_opts())
    with pytest.raises(FinalizeError, match="Already cancelled"):
        create_storno(session, f.id, options=_opts())


@pytest.mark.integration
def test_storno_uses_next_sequence_number(session: Session):
    make_issuer(session)
    lead = make_lead_de_b2b(session)
    inv = make_draft_invoice(session, lead)
    f = finalize_invoice(session, inv.id, options=_opts())
    assert f.sequence_number == 1
    storno = create_storno(session, f.id, options=_opts())
    assert storno.sequence_number == 2
    assert storno.number == "RE-2026-0002"
