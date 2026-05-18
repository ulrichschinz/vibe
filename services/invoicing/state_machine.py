"""Explicit invoice state machine (Phase 3 Pattern 2 of the plan).

States: ``draft → finalized → {sent → paid} | cancelled``.

Cancellation goes through the storno flow (R-05): a new storno invoice with
its own number is created and the original is set to ``cancelled``. Direct
cancellation without storno is not allowed for any state other than draft (where it equals deletion).
"""
from __future__ import annotations

from typing import Mapping

from app.domains.billing.models import InvoiceStatus


class InvoiceStateError(Exception):
    """Raised when a requested state transition is not permitted."""


ALLOWED_TRANSITIONS: Mapping[InvoiceStatus, frozenset[InvoiceStatus]] = {
    InvoiceStatus.draft:     frozenset({InvoiceStatus.finalized}),
    InvoiceStatus.finalized: frozenset({InvoiceStatus.sent, InvoiceStatus.cancelled}),
    InvoiceStatus.sent:      frozenset({InvoiceStatus.paid, InvoiceStatus.cancelled}),
    InvoiceStatus.paid:      frozenset({InvoiceStatus.cancelled}),
    InvoiceStatus.cancelled: frozenset(),
}


def can_transition(current: InvoiceStatus, target: InvoiceStatus) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, frozenset())


def assert_can_transition(current: InvoiceStatus, target: InvoiceStatus) -> None:
    if not can_transition(current, target):
        raise InvoiceStateError(
            f"Transition not allowed: {current.value} → {target.value}. "
            f"Allowed from {current.value}: "
            f"{[s.value for s in ALLOWED_TRANSITIONS.get(current, frozenset())]}"
        )
