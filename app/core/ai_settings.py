"""app.core.ai_settings — persisted AI provider configuration (singleton).

Scaling-roadmap Schritt 4: `AiSettings` is the DB-persisted config for the
AI capability. It is not a product domain; it belongs in the kernel next to
the future `core/ai.py` adapter (Anthropic client + prompt registry +
`===MARKER===` parsing, moved verbatim in Schritt 6). Kept in its own
module so the Schritt-6 verbatim `ai.py` adapter move stays a clean,
isolated change.

Move-not-rewrite: class body byte-identical to the pre-split `models.py`.
The `AI_PROVIDER_LABELS` label dict moved to `app.shared.labels`.
"""

from __future__ import annotations

from enum import Enum

from sqlmodel import Field

from app.core.db import SQLModel


class AiProvider(str, Enum):
    anthropic = "anthropic"


class AiSettings(SQLModel, table=True):
    id: int = Field(default=1, primary_key=True)  # Singleton
    provider: AiProvider = AiProvider.anthropic
    api_key: str = ""
    model: str = "claude-sonnet-4-6"
    is_active: bool = False
