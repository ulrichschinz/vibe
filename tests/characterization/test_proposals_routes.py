"""Characterization — routes/proposals.py AI-draft + merge, update, mark-sent.

Pins behaviour Schritt 6 moves into domains/proposals/service.py (AI-draft
generation + merge) and the proposal mutation handlers Schritt 7 rewires.
Assertion granularity: status + redirect Location + DB side-effect, and for
the AI-draft prefill GET the *side-effect-free* contract (it must NOT write)
plus the stubbed-LLM call count — NOT the rendered HTML (cosmetic-fragile
across the service extraction; the exact merged text is pinned later by the
Schritt-6 service unit-test, per the lifecycle rule). See
docs/characterization-map.md.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from models import AiSettings, Proposal, ProposalStatus
from routes import proposals as proposals_route
from services import ai
from services.proposals import create_proposal as create_proposal_svc
from tests.characterization.conftest import build_minimal_app
from tests.fixtures.factories import make_lead_de_b2b, make_planning_messages

pytestmark = pytest.mark.characterization

_LLM_DRAFT = (
    "===INTRO===\nAnschreiben aus dem Chat.\n"
    "===STRATEGY_DESCRIPTION===\nStrat-Desc.\n"
    "===STRATEGY_DELIVERABLES===\nD-A\nD-B\n"
    "===CHANGE_DESCRIPTION===\nChange-Desc.\n"
    "===CHANGE_DELIVERABLES===\nWS\n"
    "===TECH_DESCRIPTION===\nTech-Desc.\n"
    "===TECH_DELIVERABLES===\nMulti-Agent\n"
)


def _enable_ai(session: Session) -> None:
    session.merge(AiSettings(id=1, api_key="sk-test", model="claude-sonnet-4-6", is_active=True))
    session.commit()


# ── AI-draft prefill (GET, side-effect free) ───────────────────────────────


@pytest.mark.characterization
def test_from_plan_calls_llm_once_and_writes_nothing(engine, session, monkeypatch):
    _enable_ai(session)
    lead = make_lead_de_b2b(session, plan_text="Fallback-Plan")
    make_planning_messages(session, lead, count=4)

    calls = {"n": 0}

    def fake_chat(messages, system, settings):
        calls["n"] += 1
        return _LLM_DRAFT

    monkeypatch.setattr(ai, "chat_with_context", fake_chat)

    app = build_minimal_app(proposals_route.router, session=session)
    with TestClient(app) as c:
        resp = c.get(f"/leads/{lead.id}/proposals/new?from_plan=1")

    assert resp.status_code == 200
    assert calls["n"] == 1
    # Prefill is read-only — no Proposal persisted.
    assert session.exec(select(Proposal)).all() == []


@pytest.mark.characterization
def test_from_plan_llm_error_falls_back_without_5xx_or_write(engine, session, monkeypatch):
    _enable_ai(session)
    lead = make_lead_de_b2b(session, plan_text="Fallback-bei-Fehler")
    make_planning_messages(session, lead, count=2)

    def boom(messages, system, settings):
        raise RuntimeError("LLM down")

    monkeypatch.setattr(ai, "chat_with_context", boom)

    app = build_minimal_app(proposals_route.router, session=session)
    with TestClient(app) as c:
        resp = c.get(f"/leads/{lead.id}/proposals/new?from_plan=1")

    assert resp.status_code == 200
    assert session.exec(select(Proposal)).all() == []


# ── Proposal update ────────────────────────────────────────────────────────


@pytest.mark.characterization
def test_proposal_update_persists_fields_and_redirects(engine, session):
    lead = make_lead_de_b2b(session)
    p = create_proposal_svc(session, lead_id=lead.id, title="Alt")
    before_updated = p.updated_at
    pid = p.id

    app = build_minimal_app(proposals_route.router, session=session)
    with TestClient(app) as c:
        resp = c.post(
            f"/proposals/{pid}/update",
            data={
                "title": "Neuer Titel",
                "intro_text": "Neue Intro",
                "services_json": "[]",
                "total_value": "4200",
                "duration": "6 Wochen",
            },
            follow_redirects=False,
        )

    assert resp.status_code == 303
    assert resp.headers["location"] == f"/proposals/{pid}"

    session.expire_all()
    updated = session.get(Proposal, pid)
    assert updated.title == "Neuer Titel"
    assert updated.intro_text == "Neue Intro"
    assert updated.total_value == 4200.0
    assert updated.duration == "6 Wochen"
    assert updated.updated_at >= before_updated


# ── Proposal mark-sent ─────────────────────────────────────────────────────


@pytest.mark.characterization
def test_proposal_mark_sent_sets_status_and_redirects(engine, session):
    lead = make_lead_de_b2b(session)
    p = create_proposal_svc(session, lead_id=lead.id, title="Zu senden")
    pid = p.id
    assert p.status == ProposalStatus.draft

    app = build_minimal_app(proposals_route.router, session=session)
    with TestClient(app) as c:
        resp = c.post(f"/proposals/{pid}/mark-sent", follow_redirects=False)

    assert resp.status_code == 303
    assert resp.headers["location"] == f"/proposals/{pid}"

    session.expire_all()
    sent = session.get(Proposal, pid)
    assert sent.status == ProposalStatus.sent
    assert sent.sent_at is not None
