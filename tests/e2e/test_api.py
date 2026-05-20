"""Phase 7 — REST API for invoices."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from main import app
from app.core.identity import ApiKey
from app.domains.billing.models import IssuerProfile
from app.domains.leads.models import Lead
from services.auth import hash_api_key
from sqlmodel import Session

pytestmark = [pytest.mark.e2e]


@pytest.fixture
def client_with_api_key(engine, tmp_path, monkeypatch):
    monkeypatch.setenv("INVOICE_ARCHIVE_ROOT", str(tmp_path / "archive"))
    from database import get_session
    def override():
        with Session(engine) as s:
            yield s
    app.dependency_overrides[get_session] = override

    raw_key = "test-api-key-9999"
    with Session(engine) as session:
        # bootstrap issuer + a lead + an API key
        from tests.fixtures.factories import make_issuer, make_lead_de_b2b
        make_issuer(session)
        lead = make_lead_de_b2b(session)
        # create an admin user to own the API key
        from app.core.identity import User, UserRole
        from services.auth import hash_password
        admin = User(email="api@test", name="API", hashed_password=hash_password("x"), role=UserRole.admin)
        session.add(admin); session.commit(); session.refresh(admin)
        key = ApiKey(label="test", key_hash=hash_api_key(raw_key), created_by_id=admin.id)
        session.add(key); session.commit()
        lead_id = lead.id

    client = TestClient(app)
    yield client, raw_key, lead_id
    app.dependency_overrides.clear()


@pytest.mark.e2e
def test_api_full_flow(client_with_api_key):
    client, key, lead_id = client_with_api_key
    headers = {"X-API-Key": key}

    # 1. Create draft
    r = client.post("/api/invoices/draft", json={
        "lead_id": lead_id,
        "leistungsdatum": "2026-05-01",
        "title": "API Beratung",
    }, headers=headers)
    assert r.status_code == 201, r.text
    draft = r.json()
    assert draft["status"] == "draft"

    # 2. Add line
    r = client.post(f"/api/invoices/{draft['id']}/lines", json={
        "description": "Beratung",
        "quantity": "5",
        "unit_price_net": "200",
        "vat_rate": "19",
    }, headers=headers)
    assert r.status_code == 201, r.text

    # 3. Finalize with idempotency key
    r = client.post(f"/api/invoices/{draft['id']}/finalize",
                    headers={**headers, "Idempotency-Key": "abc-123"})
    assert r.status_code == 200, r.text
    inv = r.json()
    assert inv["status"] == "finalized"
    assert inv["number"].startswith("RE-")
    assert inv["subtotal_net"] == "1000.00"
    assert inv["total_gross"] == "1190.00"

    # 4. Idempotent retry returns same row
    r2 = client.post(f"/api/invoices/{draft['id']}/finalize",
                     headers={**headers, "Idempotency-Key": "abc-123"})
    assert r2.status_code == 200
    assert r2.json()["number"] == inv["number"]

    # 5. List
    r = client.get("/api/invoices", headers=headers)
    assert r.status_code == 200
    assert len(r.json()) == 1


@pytest.mark.e2e
def test_api_unauthorized_without_key(client_with_api_key):
    client, _, _ = client_with_api_key
    r = client.get("/api/invoices")
    assert r.status_code == 401
