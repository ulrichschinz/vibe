"""app.core.identity — platform identity & access tables.

Scaling-roadmap Schritt 4: `models.py` is split along the domains. `User`,
`UserRole` and `ApiKey` are **not** a product domain — they are
cross-cutting platform/identity (auth, agent API key). They live in the
reusable kernel (`app.core`), next to the future `core/security.py`
(password hashing, auth dependencies — Schritt 6). The kernel "knows no
domain"; these tables import nothing from `domains/*` so the end-state
`core ↛ domains` rule holds.

Move-not-rewrite: class bodies are byte-identical to the pre-split
`models.py`; only the import surface changed (shared `SQLModel` base from
`app.core.db`). The `USER_ROLE_LABELS` label dict moved to
`app.shared.labels` ("labels sind Daten").
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field

from app.core.db import SQLModel


class UserRole(str, Enum):
    admin = "admin"
    editor = "editor"
    viewer = "viewer"


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
