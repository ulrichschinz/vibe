"""Characterization — routes/leads.py + the Lead→Proposal handler.

Pins behaviour Schritt 6 moves into domains/leads/service.py (dashboard
aggregation, LinkedIn-import orchestration) and the Lead→Proposal creation
(routes/proposals.py, also Schritt 6). See docs/characterization-map.md.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.ai_settings import AiSettings
from app.domains.leads.models import Lead, LeadStage
from app.domains.proposals.models import Proposal
from routes import leads as leads_route
from routes import proposals as proposals_route
from tests.characterization.conftest import build_minimal_app
from tests.fixtures.factories import make_lead_de_b2b

pytestmark = pytest.mark.characterization


def _enable_ai(session: Session) -> None:
    session.merge(AiSettings(id=1, api_key="sk-test", model="claude-sonnet-4-6", is_active=True))
    session.commit()


# ── Dashboard aggregation ──────────────────────────────────────────────────
# Dashboard has no DB side-effect and no redirect; its only output is HTML
# (excluded by the Vertrag). The stable characterization is therefore: the
# aggregation handler executes over a dataset spanning every stage + a
# snoozed lead and returns 200. The exact by_stage/snoozed numbers get
# pinned by the Schritt-6 service unit-test that replaces this (lifecycle).


@pytest.mark.characterization
def test_dashboard_aggregation_over_all_stages_returns_200(engine, session):
    from datetime import date, timedelta

    for st in LeadStage:
        make_lead_de_b2b(session, name=f"L-{st.value}", stage=st)
    make_lead_de_b2b(session, name="Snoozed", snooze_until=date.today() + timedelta(days=7))

    app = build_minimal_app(leads_route.router, session=session)
    with TestClient(app) as c:
        resp = c.get("/")

    assert resp.status_code == 200


# ── LinkedIn import flow (preview-only: NEVER persists a Lead) ──────────────


@pytest.mark.characterization
def test_linkedin_import_happy_path_renders_preview_without_persisting(engine, session, monkeypatch):
    _enable_ai(session)
    import services.linkedin_import as li

    def fake_extract(pdf_bytes, why_good, settings):
        return {
            "name": "Erika Beispiel",
            "company": "Beispiel AG",
            "salutation": "Frau",
            "email": "erika@beispiel.ag",
            "company_summary": "Mittelständischer Maschinenbauer.",
            "buying_signals": "Skaliert Vertrieb.",
        }

    monkeypatch.setattr(li, "extract_lead_from_pdf", fake_extract)

    app = build_minimal_app(leads_route.router, session=session, with_session_mw=True)
    with TestClient(app) as c:
        resp = c.post(
            "/leads/import-linkedin",
            files={"pdf": ("profile.pdf", b"%PDF-1.4 fake", "application/pdf")},
            data={"why_good": "Klarer ICP-Fit", "lead_type": "direct"},
        )

    assert resp.status_code == 200
    # Characterization: import is preview-only — nothing written.
    assert session.exec(select(Lead)).all() == []


@pytest.mark.characterization
def test_linkedin_import_non_pdf_redirects_and_persists_nothing(engine, session):
    _enable_ai(session)
    app = build_minimal_app(leads_route.router, session=session, with_session_mw=True)
    with TestClient(app) as c:
        resp = c.post(
            "/leads/import-linkedin",
            files={"pdf": ("notes.txt", b"hello", "text/plain")},
            data={"why_good": "x", "lead_type": "direct"},
            follow_redirects=False,
        )

    assert resp.status_code == 303
    assert resp.headers["location"] == "/leads/import-linkedin"
    assert session.exec(select(Lead)).all() == []


@pytest.mark.characterization
def test_linkedin_import_extraction_error_redirects_and_persists_nothing(engine, session, monkeypatch):
    _enable_ai(session)
    import services.linkedin_import as li

    def boom(pdf_bytes, why_good, settings):
        raise li.LinkedInImportError("model refused")

    monkeypatch.setattr(li, "extract_lead_from_pdf", boom)

    app = build_minimal_app(leads_route.router, session=session, with_session_mw=True)
    with TestClient(app) as c:
        resp = c.post(
            "/leads/import-linkedin",
            files={"pdf": ("profile.pdf", b"%PDF-1.4 fake", "application/pdf")},
            data={"why_good": "x", "lead_type": "direct"},
            follow_redirects=False,
        )

    assert resp.status_code == 303
    assert resp.headers["location"] == "/leads/import-linkedin"
    assert session.exec(select(Lead)).all() == []


# ── Lead → Proposal creation ───────────────────────────────────────────────


@pytest.mark.characterization
def test_lead_to_proposal_creates_row_and_redirects(engine, session):
    lead = make_lead_de_b2b(session)
    app = build_minimal_app(proposals_route.router, session=session)
    with TestClient(app) as c:
        resp = c.post(
            f"/leads/{lead.id}/proposals",
            data={"title": "Angebot Beratung"},
            follow_redirects=False,
        )

    assert resp.status_code == 303
    loc = resp.headers["location"]
    assert loc.startswith("/proposals/")

    proposals = session.exec(select(Proposal).where(Proposal.lead_id == lead.id)).all()
    assert len(proposals) == 1
    p = proposals[0]
    assert p.title == "Angebot Beratung"
    assert p.number  # numbering service assigned a number
    assert loc == f"/proposals/{p.id}"


@pytest.mark.characterization
def test_lead_to_proposal_unknown_lead_is_404(engine, session):
    app = build_minimal_app(proposals_route.router, session=session)
    with TestClient(app) as c:
        resp = c.post(
            "/leads/999999/proposals",
            data={"title": "X"},
            follow_redirects=False,
        )
    assert resp.status_code == 404
