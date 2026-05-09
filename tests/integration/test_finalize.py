"""Phase 4 — finalize service integration tests.

R-01 (mandatory fields), R-02 (number gap-free), R-03 (immutability after),
R-04 (snapshot), R-09 (Leistungsdatum), R-12 (hash chain), idempotency.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlmodel import Session

from models import Invoice, InvoiceStatus
from services.invoicing.finalize import (
    FinalizeOptions,
    InvoiceValidationError,
    IdempotencyMismatchError,
    finalize_invoice,
    mark_paid,
    mark_sent,
)
from services.invoicing.state_machine import InvoiceStateError
from tests.fixtures.factories import (
    make_draft_invoice,
    make_issuer,
    make_lead_de_b2b,
    make_lead_drittland_us,
    make_lead_eu_b2b_at,
)


def _opts(**kwargs):
    return FinalizeOptions(today=date(2026, 5, 9), **kwargs)


# ─── Happy path ─────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_finalize_de_b2b_assigns_number_and_freezes_snapshot(session: Session):
    issuer = make_issuer(session)
    lead = make_lead_de_b2b(session)
    invoice = make_draft_invoice(session, lead)

    finalized = finalize_invoice(session, invoice.id, options=_opts())

    assert finalized.status == InvoiceStatus.finalized
    assert finalized.number == "RE-2026-0001"
    assert finalized.fiscal_year == 2026
    assert finalized.sequence_number == 1
    assert finalized.invoice_date == date(2026, 5, 9)
    # Snapshots populated
    assert finalized.iss_legal_name == issuer.legal_name
    assert finalized.iss_steuernummer == issuer.steuernummer
    assert finalized.cust_legal_name == lead.name
    assert finalized.cust_postal_code == lead.postal_code
    # Totals (10 Std × 100 €, 19 %)
    assert finalized.subtotal_net == Decimal("1000.00")
    assert finalized.vat_total == Decimal("190.00")
    assert finalized.total_gross == Decimal("1190.00")
    # Hash + archive paths
    assert finalized.hash_sha256 and len(finalized.hash_sha256) == 64
    assert finalized.archive_path_pdf
    assert finalized.archive_path_xml


@pytest.mark.integration
def test_finalize_dense_sequence_for_two_invoices(session: Session):
    make_issuer(session)
    lead = make_lead_de_b2b(session)
    a = make_draft_invoice(session, lead)
    b = make_draft_invoice(session, lead)
    fa = finalize_invoice(session, a.id, options=_opts())
    fb = finalize_invoice(session, b.id, options=_opts())
    assert (fa.sequence_number, fb.sequence_number) == (1, 2)
    assert fb.hash_prev == fa.hash_sha256, "hash chain links to predecessor"


# ─── R-04 snapshot freezes after edits to source ────────────────────────────


@pytest.mark.integration
def test_snapshot_isolated_from_lead_edits(session: Session):
    make_issuer(session)
    lead = make_lead_de_b2b(session, name="Vor Finalize")
    inv = make_draft_invoice(session, lead)
    finalized = finalize_invoice(session, inv.id, options=_opts())
    assert finalized.cust_legal_name == "Vor Finalize"
    # Mutate the lead post-finalize
    lead.name = "Nach Finalize"
    lead.city = "Berlin"
    session.add(lead)
    session.commit()
    # Reload invoice — snapshot must remain unchanged
    fresh = session.get(Invoice, finalized.id)
    assert fresh.cust_legal_name == "Vor Finalize"
    assert fresh.cust_city == "München"  # original lead value


# ─── R-09 Leistungsdatum required ───────────────────────────────────────────


@pytest.mark.integration
def test_missing_leistungsdatum_blocked(session: Session):
    make_issuer(session)
    lead = make_lead_de_b2b(session)
    inv = make_draft_invoice(session, lead, leistungsdatum=None)
    with pytest.raises(InvoiceValidationError, match="Leistungsdatum"):
        finalize_invoice(session, inv.id, options=_opts())


@pytest.mark.integration
def test_missing_customer_address_blocked(session: Session):
    make_issuer(session)
    lead = make_lead_de_b2b(session, postal_code=None, city=None)
    inv = make_draft_invoice(session, lead)
    with pytest.raises(InvoiceValidationError, match="Customer block incomplete"):
        finalize_invoice(session, inv.id, options=_opts())


@pytest.mark.integration
def test_missing_issuer_steuernummer_blocked_unless_kleinunternehmer(session: Session):
    make_issuer(session, steuernummer=None, ust_id=None, is_kleinunternehmer=False)
    lead = make_lead_de_b2b(session)
    inv = make_draft_invoice(session, lead)
    with pytest.raises(InvoiceValidationError, match="Steuernummer or USt-IdNr"):
        finalize_invoice(session, inv.id, options=_opts())


@pytest.mark.integration
def test_kleinunternehmer_without_steuernummer_allowed(session: Session):
    make_issuer(session, steuernummer=None, ust_id=None, is_kleinunternehmer=True)
    lead = make_lead_de_b2b(session)
    inv = make_draft_invoice(session, lead)
    finalized = finalize_invoice(session, inv.id, options=_opts())
    assert finalized.hint_kleinunternehmer is True
    assert finalized.vat_total == Decimal("0.00")


# ─── R-08 reverse charge ────────────────────────────────────────────────────


@pytest.mark.integration
def test_eu_b2b_reverse_charge_zero_vat(session: Session):
    make_issuer(session)
    lead = make_lead_eu_b2b_at(session)
    inv = make_draft_invoice(session, lead)
    finalized = finalize_invoice(session, inv.id, options=_opts())
    assert finalized.hint_reverse_charge is True
    assert finalized.vat_total == Decimal("0.00")
    assert finalized.cust_vat_id == "ATU99999999"


# ─── R-06 Drittland ─────────────────────────────────────────────────────────


@pytest.mark.integration
def test_third_country_zero_vat(session: Session):
    make_issuer(session)
    lead = make_lead_drittland_us(session)
    inv = make_draft_invoice(session, lead)
    finalized = finalize_invoice(session, inv.id, options=_opts())
    assert finalized.hint_third_country is True
    assert finalized.vat_total == Decimal("0.00")


# ─── Idempotency ────────────────────────────────────────────────────────────


@pytest.mark.integration
def test_idempotent_finalize_returns_existing(session: Session):
    make_issuer(session)
    lead = make_lead_de_b2b(session)
    inv = make_draft_invoice(session, lead)
    a = finalize_invoice(session, inv.id, idempotency_key="abc-123", options=_opts())
    b = finalize_invoice(session, inv.id, idempotency_key="abc-123", options=_opts())
    assert a.id == b.id
    assert a.number == b.number


@pytest.mark.integration
def test_idempotency_key_collision_across_invoices_rejected(session: Session):
    make_issuer(session)
    lead = make_lead_de_b2b(session)
    inv_a = make_draft_invoice(session, lead)
    inv_b = make_draft_invoice(session, lead)
    finalize_invoice(session, inv_a.id, idempotency_key="dup-key", options=_opts())
    with pytest.raises(IdempotencyMismatchError):
        finalize_invoice(session, inv_b.id, idempotency_key="dup-key", options=_opts())


# ─── R-15 6-Monats-Warnung ──────────────────────────────────────────────────


@pytest.mark.integration
def test_late_leistungsdatum_warning_fires(session: Session):
    make_issuer(session)
    lead = make_lead_de_b2b(session)
    inv = make_draft_invoice(session, lead, leistungsdatum=date(2025, 9, 1))
    warnings_seen = []
    finalized = finalize_invoice(
        session, inv.id,
        options=_opts(on_late_leistungsdatum=lambda i: warnings_seen.append(i.id)),
    )
    assert warnings_seen == [finalized.id]


@pytest.mark.integration
def test_recent_leistungsdatum_no_warning(session: Session):
    make_issuer(session)
    lead = make_lead_de_b2b(session)
    inv = make_draft_invoice(session, lead, leistungsdatum=date(2026, 1, 1))
    warnings_seen = []
    finalize_invoice(
        session, inv.id,
        options=_opts(on_late_leistungsdatum=lambda i: warnings_seen.append(i.id)),
    )
    assert warnings_seen == []


# ─── R-03 immutability — DB triggers + ORM listener ─────────────────────────


@pytest.mark.integration
def test_finalized_invoice_total_change_blocked(session: Session):
    make_issuer(session)
    lead = make_lead_de_b2b(session)
    inv = make_draft_invoice(session, lead)
    finalized = finalize_invoice(session, inv.id, options=_opts())
    # ORM-level mutation should raise before reaching SQL
    finalized.total_gross = Decimal("0.00")
    session.add(finalized)
    with pytest.raises(Exception):  # ImmutableInvoiceError or sqlite ABORT
        session.commit()
    session.rollback()


# ─── Status transitions ─────────────────────────────────────────────────────


@pytest.mark.integration
def test_mark_sent_then_paid(session: Session):
    make_issuer(session)
    lead = make_lead_de_b2b(session)
    inv = make_draft_invoice(session, lead)
    f = finalize_invoice(session, inv.id, options=_opts())
    sent = mark_sent(session, f.id)
    assert sent.status == InvoiceStatus.sent
    assert sent.sent_at is not None
    paid = mark_paid(session, sent.id)
    assert paid.status == InvoiceStatus.paid
    assert paid.paid_at is not None


@pytest.mark.integration
def test_cannot_skip_states(session: Session):
    make_issuer(session)
    lead = make_lead_de_b2b(session)
    inv = make_draft_invoice(session, lead)
    f = finalize_invoice(session, inv.id, options=_opts())
    with pytest.raises(InvoiceStateError):
        mark_paid(session, f.id)  # finalized → paid is not allowed; must go via sent
