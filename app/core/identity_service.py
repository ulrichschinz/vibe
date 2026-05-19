"""core.identity — service layer (Remediation-Track T2a).

`User`/`ApiKey` construction that lived inline in `app/interfaces/web/admin.py`
moves here so the model is built in exactly one place (the "one logic,
three clients" payoff of the Web/REST-Modellsperre). `User`/`ApiKey` are
platform/identity tables, *not* a domain — so this is a `core` service, not
a `domains/*` one (Contract-Kantentabelle: `core` may import `core` +
stdlib/3rd-party only). Password/key **hashing stays in the handler**
(`services.auth` — a `core ↛ services` forbidden edge): the caller passes
the already-hashed value in. Bodies are byte-identical to the old inline
`User(...)`/`ApiKey(...)` + `session` calls.
"""

from __future__ import annotations

from sqlmodel import Session

from app.core.identity import ApiKey, User, UserRole


def create_user(
    session: Session,
    *,
    name: str,
    email: str,
    hashed_password: str,
    role: UserRole,
) -> User:
    user = User(
        name=name,
        email=email,
        hashed_password=hashed_password,
        role=role,
    )
    session.add(user)
    session.commit()
    return user


def create_api_key(
    session: Session,
    *,
    label: str,
    key_hash: str,
    created_by_id: int,
) -> ApiKey:
    key = ApiKey(
        label=label,
        key_hash=key_hash,
        created_by_id=created_by_id,
    )
    session.add(key)
    session.commit()
    return key
