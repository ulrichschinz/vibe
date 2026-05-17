"""Characterization — routes/api.py inline error coercion.

Schritt 8 replaces the per-endpoint inline `HTTPException(status, str)` with
ONE central RFC-7807 mapper. These tests pin the CURRENT error contract —
FastAPI's default ``{"detail": "..."}`` body (NOT application/problem+json)
and the exact status codes — so that Schritt-8 change is a *visible,
intentional* diff, not a silent regression. Mirrors the api-key client
fixture from tests/e2e/test_api.py. See docs/characterization-map.md.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from main import app
from models import ApiKey
from services.auth import hash_api_key, hash_password

pytestmark = pytest.mark.characterization


@pytest.fixture
def api(engine, tmp_path, monkeypatch):
    monkeypatch.setenv("INVOICE_ARCHIVE_ROOT", str(tmp_path / "archive"))
    from database import get_session

    def override():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = override

    raw_key = "char-api-key-0001"
    with Session(engine) as session:
        from models import User, UserRole
        from tests.fixtures.factories import make_issuer, make_lead_de_b2b

        make_issuer(session)
        lead = make_lead_de_b2b(session)
        admin = User(email="char-api@test", name="API", hashed_password=hash_password("x"), role=UserRole.admin)
        session.add(admin)
        session.commit()
        session.refresh(admin)
        session.add(ApiKey(label="char", key_hash=hash_api_key(raw_key), created_by_id=admin.id))
        session.commit()
        lead_id = lead.id

    client = TestClient(app)
    yield client, {"X-API-Key": raw_key}, lead_id
    app.dependency_overrides.clear()


# ── auth errors ────────────────────────────────────────────────────────────


@pytest.mark.characterization
def test_missing_api_key_is_401_detail(api):
    client, _, _ = api
    r = client.post("/api/leads", json={"name": "X"})
    assert r.status_code == 401
    assert r.json() == {"detail": "API key required"}


@pytest.mark.characterization
def test_invalid_api_key_is_401_detail(api):
    client, _, _ = api
    r = client.post("/api/leads", json={"name": "X"}, headers={"X-API-Key": "nope"})
    assert r.status_code == 401
    assert r.json() == {"detail": "Invalid API key"}


# ── inline 422 / 404 / 409 coercions ───────────────────────────────────────


@pytest.mark.characterization
def test_create_lead_without_name_or_company_is_422_detail(api):
    client, headers, _ = api
    r = client.post("/api/leads", json={}, headers=headers)
    assert r.status_code == 422
    assert r.json() == {"detail": "name oder company muss angegeben sein."}


@pytest.mark.characterization
def test_add_line_to_unknown_invoice_is_404_detail(api):
    client, headers, _ = api
    r = client.post(
        "/api/invoices/999999/lines",
        json={"description": "B", "quantity": "1", "unit_price_net": "1"},
        headers=headers,
    )
    assert r.status_code == 404
    assert r.json() == {"detail": "invoice not found"}


@pytest.mark.characterization
def test_get_unknown_invoice_is_404(api):
    client, headers, _ = api
    r = client.get("/api/invoices/999999", headers=headers)
    assert r.status_code == 404
    assert "detail" in r.json()


@pytest.mark.characterization
def test_finalize_without_lines_is_422_detail_string(api):
    client, headers, lead_id = api
    d = client.post(
        "/api/invoices/draft",
        json={"lead_id": lead_id, "leistungsdatum": "2026-05-01", "title": "X"},
        headers=headers,
    )
    assert d.status_code == 201, d.text
    inv_id = d.json()["id"]

    r = client.post(f"/api/invoices/{inv_id}/finalize", headers=headers)
    assert r.status_code == 422
    body = r.json()
    assert set(body) == {"detail"}
    assert isinstance(body["detail"], str)


@pytest.mark.characterization
def test_double_finalize_is_409_and_lines_on_finalized_is_409(api):
    client, headers, lead_id = api
    d = client.post(
        "/api/invoices/draft",
        json={"lead_id": lead_id, "leistungsdatum": "2026-05-01", "title": "X"},
        headers=headers,
    )
    inv_id = d.json()["id"]
    client.post(
        f"/api/invoices/{inv_id}/lines",
        json={"description": "Beratung", "quantity": "10", "unit_price_net": "100"},
        headers=headers,
    )

    ok = client.post(f"/api/invoices/{inv_id}/finalize", headers=headers)
    assert ok.status_code == 200, ok.text

    again = client.post(f"/api/invoices/{inv_id}/finalize", headers=headers)
    assert again.status_code == 409
    assert set(again.json()) == {"detail"}

    on_final = client.post(
        f"/api/invoices/{inv_id}/lines",
        json={"description": "B", "quantity": "1", "unit_price_net": "1"},
        headers=headers,
    )
    assert on_final.status_code == 409
    assert on_final.json() == {"detail": "invoice is not draft"}
