"""app.core.db — shared persistence base + session dependency.

Scaling-roadmap Schritt 2 formalizes this module: it is now a *committed*,
owned part of the `app/core` skeleton (it began life as the Schritt-1
scaffold seed dropped by `scripts/new_domain.py`, which from now on defers
to this committed file — `_ensure` only writes it when absent).

Behaviour is deliberately **identical** to that seed so `make new-domain X`
and the CI scaffold-smoke stay green with zero edits: it exposes the shared
`SQLModel` declarative base (explicit re-export) and a minimal
`get_session` dependency.

Do **not** build on the sqlite path below — it is a placeholder. Schritt 3
replaces the internals here with the pydantic-settings-driven
engine/session (`app.core.config`); the public surface (`SQLModel`,
`get_session`) stays stable so callers and the scaffold do not churn.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlmodel import Session, create_engine
from sqlmodel import SQLModel as SQLModel  # explicit re-export: shared base

_engine = create_engine("sqlite:///./scaffold.db")


def get_session() -> Iterator[Session]:
    with Session(_engine) as session:
        yield session
