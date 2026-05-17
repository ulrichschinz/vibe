"""proposals domain — table models.

Scaling-roadmap Schritt 4 (move-not-rewrite): the `Proposal` table, the
`ProposalStatus` enum and the `DEFAULT_SERVICES` seed move here
byte-identical from the pre-split `models.py`. `PROPOSAL_STATUS_LABELS`
moved to `app.shared.labels`.

`Proposal.lead_id` is a SQLite string FK (`foreign_key="lead.id"`), not a
Python import of the leads domain — the package stays self-contained.
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field

from app.core.db import SQLModel


class ProposalStatus(str, Enum):
    draft = "draft"
    sent = "sent"
    accepted = "accepted"
    declined = "declined"


DEFAULT_SERVICES = [
    {
        "id": "strategy",
        "eyebrow": "// 01",
        "title": "Strategie & Consulting",
        "enabled": True,
        "description": "",
        "deliverables": [
            "Use-Case-Assessment",
            "Roadmap & Wirtschaftlichkeit",
            "Make-or-Buy-Entscheidung",
        ],
        "price": None,
    },
    {
        "id": "change",
        "eyebrow": "// 02",
        "title": "Change-Begleitung",
        "enabled": False,
        "description": "",
        "deliverables": [
            "Sparring für Führungskräfte",
            "Team-Workshops",
            "Kommunikation & Befähigung",
        ],
        "price": None,
    },
    {
        "id": "tech",
        "eyebrow": "// 03",
        "title": "Technische Umsetzung",
        "enabled": False,
        "description": "",
        "deliverables": ["Agenten-Architektur", "Knowledge-Graph-Setup", "Integration & Betrieb"],
        "price": None,
    },
]


class Proposal(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    lead_id: int = Field(foreign_key="lead.id")
    number: str               # AR-2026-001
    title: str
    intro_text: Optional[str] = None
    services: str = Field(default=json.dumps(DEFAULT_SERVICES))
    total_value: Optional[float] = None
    duration: Optional[str] = None
    payment_terms: Optional[str] = "50 % bei Projektstart, 50 % bei Abschluss"
    travel_costs: Optional[str] = "Reisekosten werden nach Aufwand und vorheriger Abstimmung gesondert in Rechnung gestellt."
    validity_days: int = 30
    status: ProposalStatus = ProposalStatus.draft
    sent_at: Optional[datetime] = None
    pdf_path: Optional[str] = None

    def get_services(self) -> list:
        try:
            return json.loads(self.services)  # type: ignore[no-any-return]
        except Exception:
            return DEFAULT_SERVICES[:]

    def get_enabled_services(self) -> list:
        return [s for s in self.get_services() if s.get("enabled")]
