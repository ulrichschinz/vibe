"""leads domain — table models.

Scaling-roadmap Schritt 4 (move-not-rewrite): the `Lead`, `Note` and
`PlanningMessage` tables + their enums (`LeadSource`, `LeadStage`,
`LeadType`, `BantValue`, `ReadinessLevel`) move here from the pre-split
`models.py`, byte-identical. `STAGE_ORDER` (pipeline ordering) and the
internal `_BANT_SCORE` map are domain data and stay with the domain.

Label dicts (`STAGE_LABELS`, `SOURCE_LABELS`, …) are *not* here — they
moved to `app.shared.labels` ("labels sind Daten"). Pydantic API schemas
moved to `app.domains.leads.schemas`.

Cross-domain references are SQLite string FKs only (e.g. `Note.lead_id`),
never Python imports — the domain stays self-contained for the
`domains/<x> ↛ domains/<y>` end-state rule.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from enum import Enum
from typing import Optional

from sqlalchemy import Column, Date, String, Text
from sqlmodel import Field

from app.core.db import SQLModel


class LeadSource(str, Enum):
    website = "website"
    referral = "referral"
    agent = "agent"
    manual = "manual"
    linkedin = "linkedin"


class LeadStage(str, Enum):
    new = "new"
    contacted = "contacted"
    proposal_sent = "proposal_sent"
    negotiating = "negotiating"
    won = "won"
    lost = "lost"


class LeadType(str, Enum):
    direct = "direct"
    partner = "partner"


STAGE_ORDER = [
    LeadStage.new,
    LeadStage.contacted,
    LeadStage.proposal_sent,
    LeadStage.negotiating,
    LeadStage.won,
    LeadStage.lost,
]


class BantValue(str, Enum):
    yes = "yes"
    open = "open"
    no = "no"


class ReadinessLevel(str, Enum):
    high = "high"
    medium = "medium"
    low = "low"


_BANT_SCORE = {
    BantValue.yes.value: 25,
    BantValue.open.value: 10,
    BantValue.no.value: 0,
}


class Lead(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    name: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True))
    company: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True))
    email: Optional[str] = None
    phone: Optional[str] = None
    salutation: Optional[str] = None  # "Frau" / "Herr" / ""
    source: LeadSource = LeadSource.manual
    lead_type: LeadType = Field(default=LeadType.direct)
    owner_id: Optional[int] = Field(default=None, foreign_key="user.id")
    stage: LeadStage = LeadStage.new
    notes: Optional[str] = None
    tags: Optional[str] = None  # JSON array string
    agent_metadata: Optional[str] = None  # JSON object string
    plan_text: Optional[str] = Field(default=None, sa_column=Column(Text))
    # Invoicing extension (added 2026-05): for §14 UStG-compliant recipient block.
    street: Optional[str] = None
    street2: Optional[str] = None
    postal_code: Optional[str] = None
    city: Optional[str] = None
    country_code: Optional[str] = Field(default="DE")  # ISO-3166-1 alpha-2
    vat_id: Optional[str] = None  # USt-IdNr.
    is_business: Optional[bool] = Field(default=True)
    tax_country: Optional[str] = None  # falls abweichend von country_code
    # Wiedervorlage / Qualifizierung (added 2026-05).
    snooze_until: Optional[date] = Field(default=None, sa_column=Column(Date, nullable=True))
    bant_budget: Optional[str] = None  # BantValue
    bant_authority: Optional[str] = None
    bant_need: Optional[str] = None
    bant_timing: Optional[str] = None
    ai_readiness: Optional[str] = None  # ReadinessLevel
    pain_points: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    next_action: Optional[str] = None
    next_action_date: Optional[date] = Field(default=None, sa_column=Column(Date, nullable=True))

    def display_name(self) -> str:
        return self.name or self.company or "—"

    def is_snoozed(self, today: Optional[date] = None) -> bool:
        if not self.snooze_until:
            return False
        ref = today or date.today()
        return self.snooze_until > ref

    def bant_score(self) -> int:
        return sum(
            _BANT_SCORE.get(v, 0)
            for v in (self.bant_budget, self.bant_authority, self.bant_need, self.bant_timing)
            if v is not None
        )

    def get_tags(self) -> list:
        if not self.tags:
            return []
        try:
            return json.loads(self.tags)  # type: ignore[no-any-return]
        except Exception:
            return []

    def get_agent_metadata(self) -> dict:
        if not self.agent_metadata:
            return {}
        try:
            return json.loads(self.agent_metadata)  # type: ignore[no-any-return]
        except Exception:
            return {}


class Note(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    lead_id: int = Field(foreign_key="lead.id")
    body: str = Field(sa_column=Column(Text))


class PlanningMessage(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    lead_id: int = Field(foreign_key="lead.id")
    role: str  # "user" | "assistant"
    content: str = Field(sa_column=Column(Text))
