#!/usr/bin/env python3
"""Scaffold a new domain package — the one-command anti-"random files" step.

Scaling-roadmap Schritt 1 (Scaffold-Vertrag). `make new-domain X` emits the
5-file domain skeleton plus a green service-level smoke test, all
import-linter- and ruff-format-conformant *by construction* (zero manual
edits → CI green).

Lives in `scripts/` and is therefore excluded from the ARCHITECTURE.md LOC
metrics by design (doc-CI / dev tooling, not product code) — generating a
domain with it must never move the documented Kennzahlen until the result is
actually committed (that happens from Schritt 2 onward, which owns the
ARCHITECTURE.md update).

The generated domain targets the *Soll* layout (`app/domains/<x>/`,
`app/core/db`). `app/core/db.py` is created here as a minimal seed (shared
SQLModel base + session dependency) only if absent, so a freshly scaffolded
domain is green before Schritt 2/3 formalize the `app/core` skeleton; those
steps supersede the seed, they do not contradict it.

Registration is auto-discovery: interfaces/* (Schritt 8) iterate
`app/domains/*` and bind each `router`. The scaffold patches no central
registry file.

Usage:
    python scripts/new_domain.py <name> [--kind web|api] [--force]
    make new-domain <name> [KIND=web|api]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
APP = REPO / "app"

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def _class_name(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_"))


def _write(path: Path, content: str, *, force: bool) -> None:
    """Write a file, creating parents. Never silently clobber unless forced."""
    if path.exists() and not force:
        raise SystemExit(f"refusing to overwrite existing file: {path.relative_to(REPO)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  wrote {path.relative_to(REPO)}")


def _ensure(path: Path, content: str) -> None:
    """Create a file only if missing (idempotent skeleton/seed files)."""
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  seeded {path.relative_to(REPO)}")


# --- generated-file templates -------------------------------------------------
# Pre-formatted to ruff-format output (double quotes, trailing blank line,
# 4-space indent) so `make format-check` on app/ passes with zero edits.


def _core_db_seed() -> str:
    return '''\
"""app.core.db — persistence seed.

Schritt-1 scaffold seed so freshly scaffolded domains are green by
construction. Schritt 2 formalizes the `app/core` skeleton; Schritt 3
replaces this with the pydantic-settings-driven engine/session. Until then
this exposes the shared SQLModel declarative base and a minimal session
dependency. Do not build on the sqlite path below — it is a placeholder the
later steps own.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlmodel import Session, create_engine
from sqlmodel import SQLModel as SQLModel  # explicit re-export: shared base

_engine = create_engine("sqlite:///./scaffold.db")


def get_session() -> Iterator[Session]:
    with Session(_engine) as session:
        yield session
'''


def _pkg_init(doc: str) -> str:
    return f'"""{doc}"""\n'


def _models(name: str, cls: str) -> str:
    return f'''\
"""{cls} domain — SQLModel tables.

Entry points: the ORM table(s) for the {name} domain. The metadata-aggregation
module (Schritt 4) imports this so SQLModel.create_all sees the table exactly
once. Replace the starter table with the real {name} shape.
"""

from __future__ import annotations

from sqlmodel import Field

from app.core.db import SQLModel


class {cls}(SQLModel, table=True):
    """Minimal starter table — replace with the real {name} shape."""

    id: int | None = Field(default=None, primary_key=True)
    name: str
'''


def _schemas(name: str, cls: str) -> str:
    return f'''\
"""{cls} domain — Pydantic API schemas (no ORM, no FastAPI import)."""

from __future__ import annotations

from pydantic import BaseModel


class {cls}Create(BaseModel):
    name: str


class {cls}Read(BaseModel):
    id: int
    name: str


class {cls}Update(BaseModel):
    name: str | None = None
'''


def _service(name: str, cls: str) -> str:
    return f'''\
"""{cls} domain — business logic.

The Session is passed in by the caller (interfaces own the request/session
lifecycle); no FastAPI import here. This is the single place Web/REST/MCP
all call — no duplicated logic.
"""

from __future__ import annotations

from sqlmodel import Session, select

from app.domains.{name}.models import {cls}
from app.domains.{name}.schemas import {cls}Create


def create_{name}(session: Session, data: {cls}Create) -> {cls}:
    obj = {cls}(name=data.name)
    session.add(obj)
    session.commit()
    session.refresh(obj)
    return obj


def list_{name}(session: Session) -> list[{cls}]:
    return list(session.exec(select({cls})).all())
'''


def _repository(name: str, cls: str) -> str:
    return f'''\
"""{cls} domain — data-access layer.

Intentionally empty. Add a repository function only once a query is
duplicated across the service ("Repository nur bei Bedarf"). Until then the
service talks to the Session directly.
"""
'''


def _router(name: str, cls: str, kind: str) -> str:
    tag = "web" if kind == "web" else "api"
    return f'''\
"""{cls} domain — HTTP router ({kind}). Thin: handlers call service only.

Auto-discovered by interfaces/* (Schritt 8 iterates app/domains/*); the
scaffold patches no central registry.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.db import get_session
from app.domains.{name} import service
from app.domains.{name}.models import {cls}
from app.domains.{name}.schemas import {cls}Create, {cls}Read

router = APIRouter(prefix="/{name}", tags=["{tag}:{name}"])


@router.post("", response_model={cls}Read)
def create_{name}_endpoint(
    data: {cls}Create, session: Session = Depends(get_session)
) -> {cls}:
    return service.create_{name}(session, data)


@router.get("", response_model=list[{cls}Read])
def list_{name}_endpoint(session: Session = Depends(get_session)) -> list[{cls}]:
    return service.list_{name}(session)
'''


def _test(name: str, cls: str) -> str:
    return f'''\
"""Smoke test for the {name} domain scaffold.

Scaffold-Vertrag: a freshly scaffolded domain is green with zero manual
edits. Service-level (no HTTP), in-memory SQLite, deterministic.
"""

from __future__ import annotations

from sqlmodel import Session, create_engine

from app.core.db import SQLModel
from app.domains.{name} import service
from app.domains.{name}.schemas import {cls}Create


def test_{name}_create_and_list_roundtrip() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        created = service.create_{name}(session, {cls}Create(name="smoke"))
        assert created.id is not None
        rows = service.list_{name}(session)
    assert [r.name for r in rows] == ["smoke"]
'''


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="new-domain", description=__doc__)
    parser.add_argument("name", help="domain name (lowercase, snake_case)")
    parser.add_argument(
        "--kind",
        choices=["web", "api"],
        default="web",
        help="router flavour (default: web)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="overwrite an existing domain (use with care)",
    )
    args = parser.parse_args(argv)

    name: str = args.name
    if not _NAME_RE.match(name):
        print(
            f"error: invalid domain name {name!r} — must match {_NAME_RE.pattern}",
            file=sys.stderr,
        )
        return 2

    cls = _class_name(name)
    domain_dir = APP / "domains" / name

    if domain_dir.exists() and not args.force:
        print(
            f"error: domain {name!r} already exists at "
            f"{domain_dir.relative_to(REPO)} (use --force to overwrite)",
            file=sys.stderr,
        )
        return 2

    print(f"scaffolding domain {name!r} (class {cls}, {args.kind} router):")

    # Idempotent skeleton/seed files (created only if missing).
    _ensure(APP / "__init__.py", _pkg_init("Application package (Soll layout)."))
    _ensure(
        APP / "core" / "__init__.py",
        _pkg_init("Reusable core: db, config, security, errors, ai (Schritt 2+)."),
    )
    _ensure(APP / "core" / "db.py", _core_db_seed())
    _ensure(
        APP / "domains" / "__init__.py",
        _pkg_init("Domain packages — auto-discovered by interfaces/* (Schritt 8)."),
    )

    # The new domain (refuses to clobber unless --force).
    _write(
        domain_dir / "__init__.py",
        _pkg_init(f"{cls} domain package."),
        force=args.force,
    )
    _write(domain_dir / "models.py", _models(name, cls), force=args.force)
    _write(domain_dir / "schemas.py", _schemas(name, cls), force=args.force)
    _write(domain_dir / "service.py", _service(name, cls), force=args.force)
    _write(domain_dir / "repository.py", _repository(name, cls), force=args.force)
    _write(domain_dir / "router.py", _router(name, cls, args.kind), force=args.force)
    _write(REPO / "tests" / f"test_{name}.py", _test(name, cls), force=args.force)

    print(
        "done. Edit order: models -> schemas -> service -> router -> test. "
        "Verify with `make verify`."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
