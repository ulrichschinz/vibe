"""Phase 4: invoice state machine."""
from __future__ import annotations

import pytest

from models import InvoiceStatus
from services.invoicing.state_machine import (
    InvoiceStateError,
    assert_can_transition,
    can_transition,
)


@pytest.mark.unit
class TestTransitions:
    def test_draft_to_finalized_allowed(self):
        assert can_transition(InvoiceStatus.draft, InvoiceStatus.finalized)

    def test_finalized_to_sent_allowed(self):
        assert can_transition(InvoiceStatus.finalized, InvoiceStatus.sent)

    def test_sent_to_paid_allowed(self):
        assert can_transition(InvoiceStatus.sent, InvoiceStatus.paid)

    def test_finalized_to_cancelled_allowed_via_storno(self):
        assert can_transition(InvoiceStatus.finalized, InvoiceStatus.cancelled)

    def test_paid_to_cancelled_allowed_via_storno(self):
        assert can_transition(InvoiceStatus.paid, InvoiceStatus.cancelled)

    def test_cancelled_is_terminal(self):
        for target in InvoiceStatus:
            assert not can_transition(InvoiceStatus.cancelled, target)

    def test_draft_cannot_skip_to_paid(self):
        assert not can_transition(InvoiceStatus.draft, InvoiceStatus.paid)

    def test_paid_cannot_revert_to_sent(self):
        assert not can_transition(InvoiceStatus.paid, InvoiceStatus.sent)

    def test_finalized_cannot_revert_to_draft(self):
        assert not can_transition(InvoiceStatus.finalized, InvoiceStatus.draft)


@pytest.mark.unit
def test_assert_raises_on_disallowed():
    with pytest.raises(InvoiceStateError, match="not allowed"):
        assert_can_transition(InvoiceStatus.finalized, InvoiceStatus.draft)
