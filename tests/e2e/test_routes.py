"""Phase 7 — end-to-end via FastAPI TestClient. Auth + happy path + storno."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from main import app
from app.core.identity import User, UserRole
from app.domains.billing.models import Invoice, InvoiceStatus, IssuerProfile
from app.domains.leads.models import Lead
from services.auth import hash_password
from sqlmodel import Session

pytestmark = [pytest.mark.e2e]


@pytest.fixture
def client(engine, tmp_path, monkeypatch):
    """TestClient sharing the per-test engine.

    Route handlers get the per-test engine via the get_session Depends
    override. The attach_user middleware (main.py) does NOT use Depends —
    it opens ``Session(engine)`` against the module-global engine bound at
    import (main.py: ``from database import ... engine``). dependency
    overrides cannot reach that, so without redirecting it too, web routes
    hit the schemaless default DB → ``no such table: user`` (only visible
    in CI, where no dev leads.db exists). Point both bindings at the
    per-test engine. Test-only isolation; no production behaviour change.
    """
    monkeypatch.setenv("INVOICE_ARCHIVE_ROOT", str(tmp_path / "archive"))
    monkeypatch.setattr("main.engine", engine)
    monkeypatch.setattr("database.engine", engine)
    from database import get_session
    def override():
        with Session(engine) as s:
            yield s
    app.dependency_overrides[get_session] = override
    yield TestClient(app)
    app.dependency_overrides.clear()


def _login_admin(client, engine):
    with Session(engine) as session:
        user = User(
            email="admin@example.com",
            name="Admin",
            hashed_password=hash_password("pwpw"),
            role=UserRole.admin,
            is_active=True,
        )
        session.add(user); session.commit()
    r = client.post("/login", data={"email": "admin@example.com", "password": "pwpw"}, follow_redirects=False)
    assert r.status_code in (200, 303), r.text


def _seed_issuer(session):
    issuer = IssuerProfile(
        id=1, legal_name="Agentic Reach", street="Staltacher 59A",
        postal_code="82393", city="Iffeldorf", country_code="DE",
        steuernummer="100/000/00000",
        bank_holder="UR", bank_iban="DE89370400440532013000",
        contact_email="x@y.de",
    )
    session.merge(issuer); session.commit()


def _seed_lead(session):
    lead = Lead(
        name="Test Kunde", company="Test GmbH",
        email="kunde@test.de", phone="+49 89 1",
        street="Teststr 1", postal_code="80331", city="München",
        country_code="DE", is_business=True,
    )
    session.add(lead); session.commit(); session.refresh(lead)
    return lead


@pytest.mark.e2e
def test_invoice_list_redirects_when_logged_out(client):
    r = client.get("/invoices/", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


@pytest.mark.e2e
def test_invoice_full_web_flow(client, engine):
    with Session(engine) as session:
        _seed_issuer(session)
        lead = _seed_lead(session)
    _login_admin(client, engine)

    # Step 1: create draft
    r = client.post("/invoices/", data={
        "lead_id": lead.id,
        "title": "Beratung Mai",
        "leistungsdatum": "2026-05-01",
    }, follow_redirects=False)
    assert r.status_code == 303
    inv_id = int(r.headers["location"].split("/")[2])

    # Step 2: add line
    r = client.post(f"/invoices/{inv_id}/lines", data={
        "description": "Beratung",
        "quantity": "10",
        "unit": "Std",
        "unit_price_net": "100",
        "vat_rate": "19",
    }, follow_redirects=False)
    assert r.status_code == 303

    # Step 3: finalize
    r = client.post(f"/invoices/{inv_id}/finalize", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == f"/invoices/{inv_id}"

    # Step 4: detail page renders
    r = client.get(f"/invoices/{inv_id}")
    assert r.status_code == 200
    assert "RE-2026-0001" in r.text
    assert "1.190,00" in r.text or "1190.00" in r.text

    # Step 5: PDF download
    r = client.get(f"/invoices/{inv_id}/pdf")
    assert r.status_code == 200
    assert r.content.startswith(b"%PDF-")

    # Step 6: XML download
    r = client.get(f"/invoices/{inv_id}/xml")
    assert r.status_code == 200
    assert b"RE-2026-0001" in r.content

    # Step 7: mark sent → mark paid
    r = client.post(f"/invoices/{inv_id}/mark-sent", follow_redirects=False)
    assert r.status_code == 303
    r = client.post(f"/invoices/{inv_id}/mark-paid", follow_redirects=False)
    assert r.status_code == 303

    # Step 8: storno (redirects to the new storno invoice)
    r = client.post(f"/invoices/{inv_id}/storno", data={"reason": "Test"}, follow_redirects=False)
    assert r.status_code == 303
    storno_id = int(r.headers["location"].split("/")[2])
    assert storno_id != inv_id

    with Session(engine) as session:
        original = session.get(Invoice, inv_id)
        storno = session.get(Invoice, storno_id)
        assert original.status == InvoiceStatus.cancelled
        assert storno.related_invoice_id == inv_id
        assert storno.total_gross == -original.total_gross


@pytest.mark.e2e
def test_admin_issuer_form(client, engine):
    _login_admin(client, engine)
    r = client.get("/admin/issuer")
    assert r.status_code == 200
    assert "Aussteller-Daten" in r.text
    r = client.post("/admin/issuer", data={
        "legal_name": "Neu GmbH",
        "street": "Hauptstr 1",
        "postal_code": "10115",
        "city": "Berlin",
        "country_code": "DE",
        "steuernummer": "123/456/78901",
        "ust_id": "DE123456789",
        "bank_holder": "Neu GmbH",
        "bank_iban": "DE89370400440532013000",
        "contact_email": "kontakt@neu.de",
        "default_payment_terms_days": "14",
        "default_payment_terms_text": "14 Tage netto",
    }, follow_redirects=False)
    assert r.status_code == 303
    with Session(engine) as session:
        i = session.get(IssuerProfile, 1)
        assert i.legal_name == "Neu GmbH"
        assert i.steuernummer == "123/456/78901"
