"""Shared helpers for the Schritt-0.5 characterization (golden) tests.

These tests pin the CURRENT observable behaviour of the handlers/tools that
Schritte 5–8 of docs/scaling-roadmap.md will move/rewire. Assertion
granularity per the Characterization-Vertrag: HTTP status + redirect
`Location` + DB side-effect for web routes; return-payload *shape* + DB
side-effect for MCP tools. NOT HTML body (would be cosmetic-fragile across
the service extraction). External calls (Anthropic, LinkedIn-PDF, VIES) are
stubbed/recorded so the tests are deterministic.

Hardness criterion: these tests must stay UNCHANGED-green across the PRs of
Schritte 5–8. A diff to one of them in those PRs is a red flag and
justification-bound. Lifecycle: a characterization test is deleted only in
the same PR that introduces the equivalent service unit-test — never
earlier. The test→step mapping lives in docs/characterization-map.md.

Patterns mirrored verbatim from the existing suite:
- minimal-app + reused session: tests/integration/test_proposal_from_plan.py
- api-key client: tests/e2e/test_api.py
- engine fixture: tests/conftest.py
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from sqlmodel import Session
from starlette.middleware.sessions import SessionMiddleware

from database import get_session
from app.core.identity import User, UserRole
from services.auth import require_editor, require_login


def build_minimal_app(*routers, session: Session, with_session_mw: bool = False) -> FastAPI:
    """Minimal app around the given router(s), reusing the test's Session.

    Reusing the seeding Session (not a fresh one per request) avoids two
    concurrent SQLite transactions fighting BEGIN IMMEDIATE on a single-file
    engine — the exact rationale documented in test_proposal_from_plan.py.
    Auth deps are overridden with an in-memory admin (not persisted).
    """
    app = FastAPI()
    if with_session_mw:
        app.add_middleware(SessionMiddleware, secret_key="characterization-test")
    for r in routers:
        app.include_router(r)

    fake_user = User(
        id=1,
        email="char@test",
        name="Char Tester",
        hashed_password="x",
        role=UserRole.admin,
        is_active=True,
    )
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[require_editor] = lambda: fake_user
    app.dependency_overrides[require_login] = lambda: fake_user
    return app


def call_tool(tool, **kwargs):
    """Invoke an MCP tool function regardless of how @mcp.tool() wraps it.

    The official FastMCP decorator returns the original function, but stay
    robust if a version wraps it in a Tool object exposing `.fn`.
    """
    fn = getattr(tool, "fn", tool)
    return fn(**kwargs)


@pytest.fixture
def mcp_module(engine, monkeypatch, tmp_path):
    """services.mcp_server with its module-global engine redirected to the
    per-test engine (it does `from database import engine` at import, so
    monkeypatching there is the only seam — analogous to the attach_user
    middleware fix). Each tool opens its own short-lived Session(engine),
    exactly like production; tests therefore seed/assert via their own
    short-lived sessions and never hold one open across a tool call.
    """
    import services.mcp_server as m

    monkeypatch.setattr(m, "engine", engine)
    monkeypatch.setenv("INVOICE_ARCHIVE_ROOT", str(tmp_path / "archive"))
    return m
