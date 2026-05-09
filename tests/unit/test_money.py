"""Decimal-Helpers + EUR-Formatter."""
from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given, strategies as st

from services.invoicing.money import D, format_eur_de, q2, q4


@pytest.mark.unit
class TestCoerce:
    def test_string_input(self):
        assert D("1.23") == Decimal("1.23")

    def test_int_input(self):
        assert D(42) == Decimal("42")

    def test_float_input_lossless(self):
        # Round-trip via str avoids the binary-float tail.
        assert D(1.10) == Decimal("1.1")

    def test_decimal_passthrough(self):
        d = Decimal("3.14")
        assert D(d) is d

    def test_unsupported_type(self):
        with pytest.raises(TypeError):
            D([1, 2, 3])  # type: ignore[arg-type]


@pytest.mark.unit
class TestQuantize:
    def test_q2_truncates_to_cents(self):
        assert q2("1.234") == Decimal("1.23")

    def test_q2_rounds_half_up(self):
        # 1.235 → 1.24 (HALF_UP), not banker's rounding
        assert q2("1.235") == Decimal("1.24")
        assert q2("1.245") == Decimal("1.25")

    def test_q2_negative_half_up(self):
        # -1.235 → -1.24 (HALF_UP rounds away from zero on .5)
        assert q2("-1.235") == Decimal("-1.24")

    def test_q4_quantity(self):
        assert q4("1.23456") == Decimal("1.2346")

    @given(st.decimals(min_value="-1000000", max_value="1000000", places=4, allow_nan=False, allow_infinity=False))
    def test_q2_idempotent_after_first_call(self, d):
        once = q2(d)
        twice = q2(once)
        assert once == twice


@pytest.mark.unit
class TestFormatEurDe:
    def test_zero(self):
        assert format_eur_de(Decimal("0")) == "0,00 €"

    def test_thousands_separator(self):
        assert format_eur_de(Decimal("1234567.89")) == "1.234.567,89 €"

    def test_below_thousand(self):
        assert format_eur_de(Decimal("42.50")) == "42,50 €"

    def test_negative(self):
        assert format_eur_de(Decimal("-100")) == "-100,00 €"

    def test_none(self):
        assert format_eur_de(None) == "—"

    def test_rounds_half_up(self):
        # 0.005 → 0.01 (HALF_UP)
        assert format_eur_de(Decimal("0.005")) == "0,01 €"
