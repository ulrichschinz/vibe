"""Unit tests for the AI proposal-draft parser + generator.

Parser + ``chat_with_context`` adapter live in ``app.core.ai``;
``generate_proposal_drafts`` orchestration in
``app.domains.proposals.service``. The shim ``services/ai.py`` died in
T7-B (ADR-015) — tests now patch the ``app.core.ai`` module object directly.
"""
from __future__ import annotations

import pytest

from app.core import ai
from app.domains.proposals.service import generate_proposal_drafts


# ─── Parser ─────────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_parser_clean_full_input():
    text = (
        "===INTRO===\n"
        "Drei Sätze persönliches Anschreiben.\n"
        "===STRATEGY_DESCRIPTION===\n"
        "Wir entwickeln eine Roadmap.\n"
        "===STRATEGY_DELIVERABLES===\n"
        "Use-Case-Assessment\n"
        "Roadmap\n"
        "Make-or-Buy\n"
        "===CHANGE_DESCRIPTION===\n"
        "Change Begleitung.\n"
        "===CHANGE_DELIVERABLES===\n"
        "Workshops\n"
        "Sparring\n"
        "===TECH_DESCRIPTION===\n"
        "Multi-Agent-Setup.\n"
        "===TECH_DELIVERABLES===\n"
        "Multi-Agent\n"
        "Integration\n"
    )
    out = ai._parse_proposal_drafts(text)
    assert out["intro"] == "Drei Sätze persönliches Anschreiben."
    assert len(out["services"]) == 3
    assert out["services"][0]["id"] == "strategy"
    assert out["services"][0]["description"] == "Wir entwickeln eine Roadmap."
    assert out["services"][0]["deliverables"] == ["Use-Case-Assessment", "Roadmap", "Make-or-Buy"]
    assert out["services"][1]["id"] == "change"
    assert out["services"][1]["deliverables"] == ["Workshops", "Sparring"]
    assert out["services"][2]["id"] == "tech"
    assert out["services"][2]["description"] == "Multi-Agent-Setup."


@pytest.mark.unit
def test_parser_only_intro_present():
    text = "===INTRO===\nNur ein Anschreiben.\n"
    out = ai._parse_proposal_drafts(text)
    assert out["intro"] == "Nur ein Anschreiben."
    for svc in out["services"]:
        assert svc["description"] == ""
        assert svc["deliverables"] == []


@pytest.mark.unit
def test_parser_sections_in_swapped_order():
    """Sections may arrive out of order — parser still maps them correctly."""
    text = (
        "===TECH_DESCRIPTION===\nTech first.\n"
        "===INTRO===\nIntro second.\n"
        "===STRATEGY_DELIVERABLES===\nA\nB\n"
    )
    out = ai._parse_proposal_drafts(text)
    assert out["intro"] == "Intro second."
    assert out["services"][0]["deliverables"] == ["A", "B"]
    assert out["services"][2]["description"] == "Tech first."


@pytest.mark.unit
def test_parser_strips_whitespace_and_blank_lines():
    text = (
        "===INTRO===\n   Anschreiben mit Spaces.   \n\n"
        "===STRATEGY_DELIVERABLES===\n"
        "  Punkt 1  \n"
        "\n"
        "Punkt 2\n"
        "\t\n"
        "Punkt 3\n"
    )
    out = ai._parse_proposal_drafts(text)
    assert out["intro"] == "Anschreiben mit Spaces."
    assert out["services"][0]["deliverables"] == ["Punkt 1", "Punkt 2", "Punkt 3"]


@pytest.mark.unit
def test_parser_empty_text_returns_defaults():
    out = ai._parse_proposal_drafts("")
    assert out["intro"] == ""
    assert [s["id"] for s in out["services"]] == ["strategy", "change", "tech"]
    for svc in out["services"]:
        assert svc["description"] == ""
        assert svc["deliverables"] == []


# ─── generate_proposal_drafts ───────────────────────────────────────────────


class _Lead:
    def __init__(self, name="Max Müller", company="Müller GmbH"):
        self.name = name
        self.company = company


class _Msg:
    def __init__(self, role, content):
        self.role = role
        self.content = content


class _Settings:
    api_key = "sk-test"
    model = "claude-sonnet-4-6"


@pytest.mark.unit
def test_generate_raises_when_chat_empty():
    with pytest.raises(ai.AiDraftError):
        generate_proposal_drafts(_Lead(), [], _Settings())


@pytest.mark.unit
def test_generate_invokes_chat_with_drafts_system(monkeypatch):
    captured = {}

    def fake_chat(messages, system, settings):
        captured["messages"] = messages
        captured["system"] = system
        captured["settings"] = settings
        return (
            "===INTRO===\nAnschreiben.\n"
            "===STRATEGY_DESCRIPTION===\nStrat.\n"
            "===STRATEGY_DELIVERABLES===\nA\nB\n"
        )

    monkeypatch.setattr(ai, "chat_with_context", fake_chat)

    msgs = [_Msg("user", "KI-Strategie für 80-Personen-Firma."),
            _Msg("assistant", "Vorschlag: Roadmap + Pilot.")]

    out = generate_proposal_drafts(_Lead(), msgs, _Settings())

    assert captured["system"] == ai.PROPOSAL_DRAFTS_SYSTEM
    assert captured["settings"].api_key == "sk-test"
    # Chat is forwarded + a final user instruction is appended
    assert len(captured["messages"]) == 3
    assert captured["messages"][0] == {"role": "user", "content": "KI-Strategie für 80-Personen-Firma."}
    assert captured["messages"][1] == {"role": "assistant", "content": "Vorschlag: Roadmap + Pilot."}
    assert captured["messages"][2]["role"] == "user"
    assert "Max Müller" in captured["messages"][2]["content"]
    assert "Müller GmbH" in captured["messages"][2]["content"]

    assert out["intro"] == "Anschreiben."
    assert out["services"][0]["description"] == "Strat."
    assert out["services"][0]["deliverables"] == ["A", "B"]
