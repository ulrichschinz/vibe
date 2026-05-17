"""leads domain — Pydantic API schemas (no `table=True`).

Scaling-roadmap Schritt 4: the `models → schemas` half of the move. These
DTOs (`LeadCreate`/`LeadRead`/`LeadPatch`) move here byte-identical from the
pre-split `models.py`; they reference the leads enums from
`app.domains.leads.models` (same domain).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from app.core.db import SQLModel
from app.domains.leads.models import (
    BantValue,
    LeadSource,
    LeadStage,
    LeadType,
    ReadinessLevel,
)


class LeadCreate(SQLModel):
    name: Optional[str] = None
    company: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    source: LeadSource = LeadSource.manual
    lead_type: LeadType = LeadType.direct
    owner_id: Optional[int] = None
    notes: Optional[str] = None
    tags: Optional[list] = None
    agent_metadata: Optional[dict] = None
    snooze_until: Optional[date] = None
    bant_budget: Optional[BantValue] = None
    bant_authority: Optional[BantValue] = None
    bant_need: Optional[BantValue] = None
    bant_timing: Optional[BantValue] = None
    ai_readiness: Optional[ReadinessLevel] = None
    pain_points: Optional[str] = None
    next_action: Optional[str] = None
    next_action_date: Optional[date] = None


class LeadRead(SQLModel):
    id: int
    created_at: datetime
    updated_at: datetime
    name: Optional[str]
    company: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    source: LeadSource
    lead_type: LeadType
    owner_id: Optional[int] = None
    stage: LeadStage
    notes: Optional[str]
    snooze_until: Optional[date] = None
    bant_budget: Optional[BantValue] = None
    bant_authority: Optional[BantValue] = None
    bant_need: Optional[BantValue] = None
    bant_timing: Optional[BantValue] = None
    ai_readiness: Optional[ReadinessLevel] = None
    pain_points: Optional[str] = None
    next_action: Optional[str] = None
    next_action_date: Optional[date] = None


class LeadPatch(SQLModel):
    name: Optional[str] = None
    company: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    stage: Optional[LeadStage] = None
    lead_type: Optional[LeadType] = None
    owner_id: Optional[int] = None
    notes: Optional[str] = None
    snooze_until: Optional[date] = None
    bant_budget: Optional[BantValue] = None
    bant_authority: Optional[BantValue] = None
    bant_need: Optional[BantValue] = None
    bant_timing: Optional[BantValue] = None
    ai_readiness: Optional[ReadinessLevel] = None
    pain_points: Optional[str] = None
    next_action: Optional[str] = None
    next_action_date: Optional[date] = None
