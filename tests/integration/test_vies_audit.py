"""Phase 6 — VIES integration. R-16 + ADR-004."""
from __future__ import annotations

from datetime import date

import pytest
from sqlmodel import Session, select

from app.domains.billing.models import (
    Invoice,
    InvoiceStatus,
    ViesAuditEntry,
    ViesResponseStatus,
)
from services.invoicing.finalize import FinalizeOptions, finalize_invoice
from services.invoicing.vies import (
    ViesBlockedError,
    ViesGateOptions,
    ViesResult,
    make_vies_gate,
)
from tests.fixtures.factories import (
    make_draft_invoice,
    make_issuer,
    make_lead_eu_b2b_at,
)


def _opts(gate, **kwargs):
    return FinalizeOptions(today=date(2026, 5, 9), vies_gate=gate, **kwargs)


# ── Successful VIES check ───────────────────────────────────────────────────


@pytest.mark.integration
def test_valid_vat_id_writes_audit_and_proceeds(session: Session):
    make_issuer(session, ust_id="DE123456789")
    lead = make_lead_eu_b2b_at(session)
    inv = make_draft_invoice(session, lead)

    def fake_check(vat_id):
        return ViesResult(
            status=ViesResponseStatus.valid,
            vat_id=vat_id,
            country_code="AT",
            raw={"valid": True, "name": "Wiener Beratungs-AG"},
        )

    gate = make_vies_gate(ViesGateOptions(check_callable=fake_check))
    f = finalize_invoice(session, inv.id, options=_opts(gate))

    assert f.hint_reverse_charge is True
    audits = list(session.exec(select(ViesAuditEntry)).all())
    assert len(audits) == 1
    assert audits[0].response_status == ViesResponseStatus.valid
    assert audits[0].vat_id_queried == "ATU99999999"


# ── Invalid → block, audit recorded ────────────────────────────────────────


@pytest.mark.integration
def test_invalid_vat_id_blocks_and_audits(session: Session):
    make_issuer(session, ust_id="DE123456789")
    lead = make_lead_eu_b2b_at(session)
    inv = make_draft_invoice(session, lead)

    def fake_check(vat_id):
        return ViesResult(
            status=ViesResponseStatus.invalid,
            vat_id=vat_id,
            country_code="AT",
            raw={"valid": False},
        )

    gate = make_vies_gate(ViesGateOptions(check_callable=fake_check))
    with pytest.raises(ViesBlockedError):
        finalize_invoice(session, inv.id, options=_opts(gate))

    # Invoice still draft (rolled back)
    session.expire_all()
    inv2 = session.get(Invoice, inv.id)
    assert inv2.status == InvoiceStatus.draft

    # Audit is persisted
    audits = list(session.exec(select(ViesAuditEntry)).all())
    assert len(audits) == 1
    assert audits[0].response_status == ViesResponseStatus.invalid


# ── Service unavailable → block, override allowed ──────────────────────────


@pytest.mark.integration
def test_service_unavailable_blocks_without_override(session: Session):
    make_issuer(session, ust_id="DE123456789")
    lead = make_lead_eu_b2b_at(session)
    inv = make_draft_invoice(session, lead)

    def fake_check(vat_id):
        return ViesResult(
            status=ViesResponseStatus.service_unavailable,
            vat_id=vat_id,
            country_code="AT",
            raw={"error": "504 timeout"},
        )

    gate = make_vies_gate(ViesGateOptions(check_callable=fake_check))
    with pytest.raises(ViesBlockedError, match="admin override required"):
        finalize_invoice(session, inv.id, options=_opts(gate))


@pytest.mark.integration
def test_service_unavailable_admin_override_succeeds(session: Session):
    make_issuer(session, ust_id="DE123456789")
    lead = make_lead_eu_b2b_at(session)
    inv = make_draft_invoice(session, lead)

    def fake_check(vat_id):
        return ViesResult(
            status=ViesResponseStatus.service_unavailable,
            vat_id=vat_id,
            country_code="AT",
            raw={"error": "504 timeout"},
        )

    gate = make_vies_gate(ViesGateOptions(
        check_callable=fake_check,
        override=True,
        override_reason="VIES Ausfall, Kunde verifiziert per Telefon am 09.05.2026.",
        override_user_id=None,
    ))
    f = finalize_invoice(session, inv.id, options=_opts(gate))
    assert f.hint_reverse_charge is True

    audits = list(session.exec(select(ViesAuditEntry)).all())
    assert len(audits) == 1
    assert audits[0].response_status == ViesResponseStatus.override
    assert audits[0].override_reason and "VIES Ausfall" in audits[0].override_reason


@pytest.mark.integration
def test_override_without_reason_rejected(session: Session):
    make_issuer(session, ust_id="DE123456789")
    lead = make_lead_eu_b2b_at(session)
    inv = make_draft_invoice(session, lead)

    def fake_check(vat_id):
        return ViesResult(
            status=ViesResponseStatus.service_unavailable,
            vat_id=vat_id,
            country_code="AT",
            raw={},
        )

    gate = make_vies_gate(ViesGateOptions(
        check_callable=fake_check,
        override=True,
        override_reason=None,
    ))
    with pytest.raises(ViesBlockedError, match="reason"):
        finalize_invoice(session, inv.id, options=_opts(gate))


# ── Non-reverse-charge invoices skip the gate entirely ─────────────────────


@pytest.mark.integration
def test_non_reverse_charge_skips_vies(session: Session):
    """DE→DE invoice should not trigger the VIES gate, even if one is provided."""
    from tests.fixtures.factories import make_lead_de_b2b
    make_issuer(session)
    lead = make_lead_de_b2b(session)
    inv = make_draft_invoice(session, lead)

    calls = []

    def fake_check(vat_id):
        calls.append(vat_id)
        return ViesResult(ViesResponseStatus.invalid, vat_id, "DE", {})

    gate = make_vies_gate(ViesGateOptions(check_callable=fake_check))
    f = finalize_invoice(session, inv.id, options=_opts(gate))
    assert f.hint_reverse_charge is False
    assert calls == [], "VIES gate must not fire for non-reverse-charge invoices"
