"""Schritt-8 equivalent unit test for the central RFC-7807 mapper.

Lifecycle (docs/characterization-map.md): `tests/characterization/
test_api_errors.py` pinned the *old* inline-coerced FastAPI-default body
(`{"detail": …}`) precisely so the Schritt-8 switch is a **visible,
intentional** diff. Per the characterization lifecycle rule, that
characterization test is deleted **in the same PR** that introduces this
equivalent unit test — which asserts the *new* contract:

- `app.core.errors.problem_response` emits `application/problem+json`
  with the RFC-7807 members (`type`, `title`, `status`, `detail`);
- the REST surface returns problem+json, the web surface keeps the
  FastAPI-default body (so the Jinja UI is byte-identical);
- status codes **and** the 422-before-409 catch order are preserved
  (`InvoiceValidationError ⊂ FinalizeError` → re-finalize is **422**,
  draft-guard is **409**) — the exact behaviour the old
  `test_double_finalize_is_422_and_lines_on_finalized_is_409` pinned.

The app-level cases mirror the old `test_api_errors` fixture verbatim
(api-key client, lead seed) so the equivalence is auditable.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session
from starlette.datastructures import URL

from app.core.errors import PROBLEM_JSON, is_api_request, problem_response
from main import app
from models import ApiKey
from services.auth import hash_api_key, hash_password


# ── pure unit: the mapper itself ───────────────────────────────────────────


def test_problem_response_is_rfc7807_problem_json():
    r = problem_response(404, "Lead not found")
    assert r.status_code == 404
    assert r.media_type == PROBLEM_JSON
    import json

    body = json.loads(bytes(r.body))
    assert body == {
        "type": "about:blank",
        "title": "Not Found",
        "status": 404,
        "detail": "Lead not found",
    }


def test_problem_response_omits_empty_detail():
    import json

    body = json.loads(bytes(problem_response(401, None).body))
    assert body == {"type": "about:blank", "title": "Unauthorized", "status": 401}
    assert "detail" not in body


def test_is_api_request_only_true_for_rest_surface():
    class _Req:
        url = URL("http://t/api/leads")

    class _Web:
        url = URL("http://t/leads")

    assert is_api_request(_Req()) is True  # type: ignore[arg-type]
    assert is_api_request(_Web()) is False  # type: ignore[arg-type]


# ── app-level: same scenarios the deleted characterization pinned ──────────


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
        admin = User(
            email="rfc-api@test",
            name="API",
            hashed_password=hash_password("x"),
            role=UserRole.admin,
        )
        session.add(admin)
        session.commit()
        session.refresh(admin)
        session.add(ApiKey(label="rfc", key_hash=hash_api_key(raw_key), created_by_id=admin.id))
        session.commit()
        lead_id = lead.id

    client = TestClient(app)
    yield client, {"X-API-Key": raw_key}, lead_id
    app.dependency_overrides.clear()


def _is_problem(r):
    assert r.headers["content-type"].startswith(PROBLEM_JSON)
    b = r.json()
    assert b["type"] == "about:blank"
    assert b["status"] == r.status_code
    assert isinstance(b["title"], str)
    return b


def test_missing_api_key_is_401_problem_json(api):
    client, _, _ = api
    r = client.post("/api/leads", json={"name": "X"})
    assert r.status_code == 401
    assert _is_problem(r)["detail"] == "API key required"


def test_invalid_api_key_is_401_problem_json(api):
    client, _, _ = api
    r = client.post("/api/leads", json={"name": "X"}, headers={"X-API-Key": "nope"})
    assert r.status_code == 401
    assert _is_problem(r)["detail"] == "Invalid API key"


def test_create_lead_without_name_or_company_is_422_problem_json(api):
    client, headers, _ = api
    r = client.post("/api/leads", json={}, headers=headers)
    assert r.status_code == 422
    assert _is_problem(r)["detail"] == "name oder company muss angegeben sein."


def test_add_line_to_unknown_invoice_is_404_problem_json(api):
    client, headers, _ = api
    r = client.post(
        "/api/invoices/999999/lines",
        json={"description": "B", "quantity": "1", "unit_price_net": "1"},
        headers=headers,
    )
    assert r.status_code == 404
    assert _is_problem(r)["detail"] == "invoice not found"


def test_get_unknown_invoice_is_404_problem_json(api):
    client, headers, _ = api
    r = client.get("/api/invoices/999999", headers=headers)
    assert r.status_code == 404
    _is_problem(r)


def test_finalize_without_lines_is_422_problem_json(api):
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
    assert isinstance(_is_problem(r)["detail"], str)


def test_double_finalize_is_422_and_lines_on_finalized_is_409(api):
    # The 422-before-409 ordering MUST be preserved by the central mapper:
    # re-finalize raises InvoiceValidationError (⊂ FinalizeError) → 422;
    # adding a line to a finalized invoice hits the explicit 409 guard.
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
    assert again.status_code == 422
    _is_problem(again)

    on_final = client.post(
        f"/api/invoices/{inv_id}/lines",
        json={"description": "B", "quantity": "1", "unit_price_net": "1"},
        headers=headers,
    )
    assert on_final.status_code == 409
    assert _is_problem(on_final)["detail"] == "invoice is not draft"
