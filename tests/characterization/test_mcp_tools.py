"""Characterization — services/mcp_server.py tools.

Pins the CURRENT return-payload *shape* + DB side-effect of the tools
Schritt 7 rewires: the duplicated Lead-construction tools
(`create_lead`/`update_lead`), the proposal tools, and the finalize chain
(which Schritt 7 routes through the BillingOrder contract). Tools open
their own Session(engine); the mcp_module fixture redirects that global to
the per-test engine. We seed/assert via our own short-lived sessions and
never hold one open across a tool call (matches production; avoids
single-file SQLite BEGIN IMMEDIATE contention). See
docs/characterization-map.md.
"""
from __future__ import annotations

import pytest
from sqlmodel import Session

from models import (
    Invoice,
    InvoiceStatus,
    Lead,
    LeadSource,
    LeadStage,
    Proposal,
    ProposalStatus,
)
from services.proposals import create_proposal as create_proposal_svc
from tests.characterization.conftest import call_tool
from tests.fixtures.factories import make_issuer, make_lead_de_b2b

pytestmark = pytest.mark.characterization

# Stable key sets — pin the payload shape without over-asserting values.
_LEAD_KEYS = {
    "id", "created_at", "updated_at", "name", "company", "email", "phone",
    "salutation", "source", "stage", "notes", "tags", "agent_metadata",
    "snooze_until", "is_snoozed", "bant_budget", "bant_authority",
    "bant_need", "bant_timing", "bant_score", "ai_readiness", "pain_points",
    "next_action", "next_action_date",
}
_INVOICE_KEYS = {
    "id", "number", "status", "kind", "fiscal_year", "sequence_number",
    "invoice_date", "leistungsdatum", "due_date", "currency",
    "subtotal_net", "vat_total", "total_gross", "hint_kleinunternehmer",
    "hint_reverse_charge", "hint_third_country", "lead_id",
    "related_invoice_id", "lines",
}


# ── create_lead / update_lead (the duplicated construction logic) ──────────


@pytest.mark.characterization
def test_create_lead_payload_shape_and_row(engine, mcp_module):
    out = call_tool(
        mcp_module.create_lead,
        name="Agent Lead",
        company="Agent GmbH",
        tags=["mcp", "inbound"],
    )

    assert set(out) == _LEAD_KEYS
    assert out["name"] == "Agent Lead"
    assert out["source"] == LeadSource.agent.value  # default
    assert out["tags"] == ["mcp", "inbound"]
    assert out["id"]

    with Session(engine) as s:
        row = s.get(Lead, out["id"])
        assert row is not None
        assert row.company == "Agent GmbH"
        assert row.source == LeadSource.agent


@pytest.mark.characterization
def test_create_lead_requires_name_or_company(engine, mcp_module):
    with pytest.raises(ValueError):
        call_tool(mcp_module.create_lead)


@pytest.mark.characterization
def test_update_lead_patches_only_given_fields(engine, mcp_module):
    with Session(engine) as s:
        lead = Lead(name="Before", company="C")
        s.add(lead)
        s.commit()
        s.refresh(lead)
        lead_id = lead.id
        before_updated = lead.updated_at

    out = call_tool(
        mcp_module.update_lead,
        lead_id=lead_id,
        stage=LeadStage.contacted,
        notes="patched",
    )

    assert set(out) == _LEAD_KEYS
    assert out["stage"] == LeadStage.contacted.value
    assert out["notes"] == "patched"
    assert out["name"] == "Before"  # untouched

    with Session(engine) as s:
        row = s.get(Lead, lead_id)
        assert row.stage == LeadStage.contacted
        assert row.notes == "patched"
        assert row.updated_at >= before_updated


@pytest.mark.characterization
def test_update_lead_unknown_id_raises_lookup(engine, mcp_module):
    with pytest.raises(LookupError):
        call_tool(mcp_module.update_lead, lead_id=999999, notes="x")


# ── proposal tools ─────────────────────────────────────────────────────────


@pytest.mark.characterization
def test_create_proposal_shape_and_row(engine, mcp_module):
    with Session(engine) as s:
        lead = make_lead_de_b2b(s)
        lead_id = lead.id

    out = call_tool(mcp_module.create_proposal, lead_id=lead_id, title="MCP Angebot")

    assert {"id", "number", "title", "status", "lead_id"} <= set(out)
    assert out["title"] == "MCP Angebot"
    assert out["number"]
    assert out["lead_id"] == lead_id

    with Session(engine) as s:
        row = s.get(Proposal, out["id"])
        assert row is not None
        assert row.lead_id == lead_id


@pytest.mark.characterization
def test_mark_proposal_sent_shape_and_row(engine, mcp_module):
    with Session(engine) as s:
        lead = make_lead_de_b2b(s)
        p = create_proposal_svc(s, lead_id=lead.id, title="Zu senden")
        pid = p.id

    out = call_tool(mcp_module.mark_proposal_sent, proposal_id=pid)

    assert out["id"] == pid
    assert out["status"] == ProposalStatus.sent.value

    with Session(engine) as s:
        row = s.get(Proposal, pid)
        assert row.status == ProposalStatus.sent
        assert row.sent_at is not None


# ── finalize chain (Schritt 7 routes this through BillingOrder) ────────────


@pytest.mark.characterization
def test_finalize_chain_draft_to_finalized(engine, mcp_module):
    with Session(engine) as s:
        make_issuer(s)
        lead = make_lead_de_b2b(s)
        lead_id = lead.id

    draft = call_tool(
        mcp_module.create_invoice_draft,
        lead_id=lead_id,
        leistungsdatum="2026-05-01",
        title="MCP Rechnung",
    )
    assert set(draft) == _INVOICE_KEYS
    assert draft["status"] == InvoiceStatus.draft.value
    inv_id = draft["id"]

    line = call_tool(
        mcp_module.add_invoice_line,
        invoice_id=inv_id,
        description="Beratung",
        quantity="10",
        unit_price_net="100",
    )
    assert set(line) == {"position", "line_net"}
    assert line["position"] == 1

    final = call_tool(mcp_module.finalize_invoice, invoice_id=inv_id)
    assert set(final) == _INVOICE_KEYS
    assert final["status"] == InvoiceStatus.finalized.value
    assert final["number"]
    assert len(final["lines"]) == 1

    with Session(engine) as s:
        row = s.get(Invoice, inv_id)
        assert row.status == InvoiceStatus.finalized
        assert row.number
