from __future__ import annotations
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, String, Text, Integer, ForeignKey
from typing import Optional, List
from datetime import datetime
from enum import Enum
import json


# ── AI Settings ─────────────────────────────────────────────────────────────

class AiProvider(str, Enum):
    anthropic = "anthropic"


AI_PROVIDER_LABELS = {
    AiProvider.anthropic: "Anthropic (Claude)",
}


class AiSettings(SQLModel, table=True):
    id: int = Field(default=1, primary_key=True)  # Singleton
    provider: AiProvider = AiProvider.anthropic
    api_key: str = ""
    model: str = "claude-sonnet-4-6"
    is_active: bool = False


# ── Users & Auth ────────────────────────────────────────────────────────────

class UserRole(str, Enum):
    admin = "admin"
    editor = "editor"
    viewer = "viewer"


USER_ROLE_LABELS = {
    UserRole.admin: "Admin",
    UserRole.editor: "Editor",
    UserRole.viewer: "Leser",
}


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    email: str = Field(unique=True, index=True)
    name: str
    hashed_password: str
    role: UserRole = UserRole.editor
    is_active: bool = True


class ApiKey(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    label: str
    key_hash: str
    is_active: bool = True
    created_by_id: int = Field(foreign_key="user.id")
    last_used_at: Optional[datetime] = None


# ── Leads ────────────────────────────────────────────────────────────────────

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


STAGE_LABELS = {
    LeadStage.new: "Neu",
    LeadStage.contacted: "Kontaktiert",
    LeadStage.proposal_sent: "Angebot gesendet",
    LeadStage.negotiating: "In Verhandlung",
    LeadStage.won: "Gewonnen",
    LeadStage.lost: "Verloren",
}

SOURCE_LABELS = {
    LeadSource.website: "Website",
    LeadSource.referral: "Empfehlung",
    LeadSource.agent: "KI-Agent",
    LeadSource.manual: "Manuell",
    LeadSource.linkedin: "LinkedIn",
}

STAGE_ORDER = [
    LeadStage.new,
    LeadStage.contacted,
    LeadStage.proposal_sent,
    LeadStage.negotiating,
    LeadStage.won,
    LeadStage.lost,
]


class Lead(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    name: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True))
    company: Optional[str] = Field(default=None, sa_column=Column(String, nullable=True))
    email: Optional[str] = None
    phone: Optional[str] = None
    salutation: Optional[str] = None    # "Frau" / "Herr" / ""
    source: LeadSource = LeadSource.manual
    stage: LeadStage = LeadStage.new
    notes: Optional[str] = None
    tags: Optional[str] = None          # JSON array string
    agent_metadata: Optional[str] = None  # JSON object string
    plan_text: Optional[str] = Field(default=None, sa_column=Column(Text))

    def display_name(self) -> str:
        return self.name or self.company or "—"

    def get_tags(self) -> list:
        if not self.tags:
            return []
        try:
            return json.loads(self.tags)
        except Exception:
            return []

    def get_agent_metadata(self) -> dict:
        if not self.agent_metadata:
            return {}
        try:
            return json.loads(self.agent_metadata)
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
    role: str          # "user" | "assistant"
    content: str = Field(sa_column=Column(Text))


class ProposalStatus(str, Enum):
    draft = "draft"
    sent = "sent"
    accepted = "accepted"
    declined = "declined"


PROPOSAL_STATUS_LABELS = {
    ProposalStatus.draft: "Entwurf",
    ProposalStatus.sent: "Gesendet",
    ProposalStatus.accepted: "Angenommen",
    ProposalStatus.declined: "Abgelehnt",
}

DEFAULT_SERVICES = [
    {
        "id": "strategy",
        "eyebrow": "// 01",
        "title": "Strategie & Consulting",
        "enabled": True,
        "description": "",
        "deliverables": ["Use-Case-Assessment", "Roadmap & Wirtschaftlichkeit", "Make-or-Buy-Entscheidung"],
        "price": None,
    },
    {
        "id": "change",
        "eyebrow": "// 02",
        "title": "Change-Begleitung",
        "enabled": False,
        "description": "",
        "deliverables": ["Sparring für Führungskräfte", "Team-Workshops", "Kommunikation & Befähigung"],
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
            return json.loads(self.services)
        except Exception:
            return DEFAULT_SERVICES[:]

    def get_enabled_services(self) -> list:
        return [s for s in self.get_services() if s.get("enabled")]


# ── API schemas (no table=True) ────────────────────────────────────────────

class LeadCreate(SQLModel):
    name: Optional[str] = None
    company: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    source: LeadSource = LeadSource.manual
    notes: Optional[str] = None
    tags: Optional[list] = None
    agent_metadata: Optional[dict] = None


class LeadRead(SQLModel):
    id: int
    created_at: datetime
    updated_at: datetime
    name: Optional[str]
    company: Optional[str]
    email: Optional[str]
    phone: Optional[str]
    source: LeadSource
    stage: LeadStage
    notes: Optional[str]


class LeadPatch(SQLModel):
    name: Optional[str] = None
    company: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    stage: Optional[LeadStage] = None
    notes: Optional[str] = None
