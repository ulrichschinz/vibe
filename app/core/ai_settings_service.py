"""core.ai_settings — service layer (Remediation-Track T2a).

The two distinct `AiSettings` constructions from
`app/interfaces/web/admin.py` move here verbatim:
``get_ai_settings_or_default`` is the **display fallback** (not persisted —
``session.get(...) or AiSettings()``), ``get_or_create_ai_settings`` is the
**get-or-create** for the save handler (``AiSettings(id=1)`` when absent).
They are deliberately separate functions — conflating the two would change
behaviour (default ``AiSettings()`` vs. ``AiSettings(id=1)``). `core`
service (Contract-Kantentabelle: `core` may import `core` + stdlib only);
the enum parsing / field mutation / commit stay in the handler (the seam).
"""

from __future__ import annotations

from sqlmodel import Session

from app.core.ai_settings import AiSettings


def get_ai_settings_or_default(session: Session) -> AiSettings:
    return session.get(AiSettings, 1) or AiSettings()


def get_or_create_ai_settings(session: Session) -> AiSettings:
    settings = session.get(AiSettings, 1)
    if not settings:
        settings = AiSettings(id=1)
    return settings
