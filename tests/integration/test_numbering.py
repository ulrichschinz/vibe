"""Phase 4 — invoice numbering: format, monotonicity, year boundary."""
from __future__ import annotations

import pytest
from sqlmodel import Session, select

from models import InvoiceNumberSequence
from services.invoicing.numbering import assign_next_number, format_number


@pytest.mark.integration
def test_format():
    assert format_number(2026, 1) == "RE-2026-0001"
    assert format_number(2026, 9999) == "RE-2026-9999"
    assert format_number(2027, 42) == "RE-2027-0042"


@pytest.mark.integration
def test_assigns_first_number_for_new_year(engine):
    with Session(engine) as s:
        seq, num = assign_next_number(s, 2026)
        s.commit()
    assert seq == 1
    assert num == "RE-2026-0001"


@pytest.mark.integration
def test_sequence_increments_within_year(engine):
    with Session(engine) as s:
        seq1, num1 = assign_next_number(s, 2026)
        seq2, num2 = assign_next_number(s, 2026)
        seq3, num3 = assign_next_number(s, 2026)
        s.commit()
    assert (seq1, seq2, seq3) == (1, 2, 3)
    assert (num1, num2, num3) == ("RE-2026-0001", "RE-2026-0002", "RE-2026-0003")


@pytest.mark.integration
def test_year_boundary_independent(engine):
    with Session(engine) as s:
        assign_next_number(s, 2026)
        assign_next_number(s, 2026)
        seq_2027, num_2027 = assign_next_number(s, 2027)
        s.commit()
    assert seq_2027 == 1
    assert num_2027 == "RE-2027-0001"


@pytest.mark.integration
def test_implausible_year_rejected(engine):
    with Session(engine) as s:
        with pytest.raises(ValueError):
            assign_next_number(s, 1900)
        with pytest.raises(ValueError):
            assign_next_number(s, 3500)
