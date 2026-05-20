"""End-to-end tests for /leads/{id}/proposals/new?from_plan=1.

Builds a minimal FastAPI app around routes.proposals with the test engine
and a stubbed `require_editor`, so we don't have to drag in main.py's MCP
lifespan or session middleware.
"""
from __future__ import annotations

from contextlib import contextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlmodel import Session

from database import get_session
from app.core.ai_settings import AiSettings
from app.core.identity import User, UserRole
from routes import proposals as proposals_route
from app.core import ai
from services.auth import require_editor, require_login
from tests.fixtures.factories import make_lead_de_b2b, make_planning_messages


def _build_app(session: Session):
    """Build a minimal app that reuses the test's Session.

    Reusing the seeding session avoids two concurrent SQLite transactions
    fighting over BEGIN IMMEDIATE on a single file engine.
    """
    app = FastAPI()
    app.include_router(proposals_route.router)

    fake_user = User(
        id=1,
        email="t@test",
        name="Tester",
        hashed_password="x",
        role=UserRole.editor,
        is_active=True,
    )

    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[require_editor] = lambda: fake_user
    app.dependency_overrides[require_login] = lambda: fake_user
    return app


def _enable_ai(session: Session):
    s = AiSettings(id=1, api_key="sk-test", model="claude-sonnet-4-6", is_active=True)
    session.merge(s)
    session.commit()


@contextmanager
def _patched_chat(monkeypatch, response_text=None, raise_exc=None):
    calls = {"count": 0}

    def fake(messages, system, settings):
        calls["count"] += 1
        if raise_exc is not None:
            raise raise_exc
        return response_text

    monkeypatch.setattr(ai, "chat_with_context", fake)
    yield calls


# ─── Happy path: chat present + AI active → all 3 blocks prefilled ──────────


@pytest.mark.integration
def test_from_plan_with_chat_prefills_intro_and_services(engine, session, monkeypatch):
    _enable_ai(session)
    lead = make_lead_de_b2b(session, plan_text="Plan-Markdown als Fallback")
    make_planning_messages(session, lead, count=4)

    llm_out = (
        "===INTRO===\nDrei-Satz-Anschreiben aus dem Chat.\n"
        "===STRATEGY_DESCRIPTION===\nStrat-Desc.\n"
        "===STRATEGY_DELIVERABLES===\nDeliv-A\nDeliv-B\n"
        "===CHANGE_DESCRIPTION===\nChange-Desc.\n"
        "===CHANGE_DELIVERABLES===\nWS\n"
        "===TECH_DESCRIPTION===\nTech-Desc.\n"
        "===TECH_DELIVERABLES===\nMulti-Agent\n"
    )

    app = _build_app(session)
    with _patched_chat(monkeypatch, response_text=llm_out) as calls:
        with TestClient(app) as c:
            resp = c.get(f"/leads/{lead.id}/proposals/new?from_plan=1")

    assert resp.status_code == 200
    body = resp.text
    assert calls["count"] == 1
    assert "Drei-Satz-Anschreiben aus dem Chat." in body
    assert "Plan-Markdown als Fallback" not in body
    assert "Strat-Desc." in body
    assert "Deliv-A" in body and "Deliv-B" in body
    assert "Change-Desc." in body
    assert "Tech-Desc." in body
    assert "Multi-Agent" in body


# ─── No chat → fall back to lead.plan_text, no LLM call ─────────────────────


@pytest.mark.integration
def test_from_plan_without_chat_falls_back_to_plan_text(engine, session, monkeypatch):
    _enable_ai(session)
    lead = make_lead_de_b2b(session, plan_text="Plan-Markdown-Fallback-XYZ")

    app = _build_app(session)
    with _patched_chat(monkeypatch, response_text="should-not-be-called") as calls:
        with TestClient(app) as c:
            resp = c.get(f"/leads/{lead.id}/proposals/new?from_plan=1")

    assert resp.status_code == 200
    assert calls["count"] == 0
    assert "Plan-Markdown-Fallback-XYZ" in resp.text


# ─── AI off → no LLM call, fallback to plan_text ────────────────────────────


@pytest.mark.integration
def test_from_plan_with_ai_disabled_skips_llm(engine, session, monkeypatch):
    # AiSettings present but is_active=False
    s = AiSettings(id=1, api_key="sk-x", model="claude-sonnet-4-6", is_active=False)
    session.merge(s)
    session.commit()

    lead = make_lead_de_b2b(session, plan_text="Fallback-bei-AI-aus")
    make_planning_messages(session, lead, count=2)

    app = _build_app(session)
    with _patched_chat(monkeypatch, response_text="nope") as calls:
        with TestClient(app) as c:
            resp = c.get(f"/leads/{lead.id}/proposals/new?from_plan=1")

    assert resp.status_code == 200
    assert calls["count"] == 0
    assert "Fallback-bei-AI-aus" in resp.text


# ─── LLM raises → fallback to plan_text, no 5xx ─────────────────────────────


@pytest.mark.integration
def test_from_plan_with_llm_error_falls_back_gracefully(engine, session, monkeypatch):
    _enable_ai(session)
    lead = make_lead_de_b2b(session, plan_text="Fallback-bei-Fehler")
    make_planning_messages(session, lead, count=2)

    app = _build_app(session)
    with _patched_chat(monkeypatch, raise_exc=RuntimeError("LLM down")):
        with TestClient(app) as c:
            resp = c.get(f"/leads/{lead.id}/proposals/new?from_plan=1")

    assert resp.status_code == 200
    assert "Fallback-bei-Fehler" in resp.text
