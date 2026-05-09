"""VAT-Engine — deckt R-06 (Konstellationen) und R-07 / R-08 ab.

Decision-Matrix gemäß Auftrag, Abschnitt 2 Regel R-06:

| Issuer | Customer        | Kleinunt? | Rate     | Code | Hint           |
|--------|-----------------|-----------|----------|------|----------------|
| DE     | DE B2C          | nein      | per line | S    | —              |
| DE     | DE B2B          | nein      | per line | S    | —              |
| DE     | DE any          | ja        | 0        | E    | kleinunternehmer |
| DE     | EU B2B (vat_id) | nein      | 0        | AE   | reverse_charge |
| DE     | EU B2C          | nein      | per line | S    | —              |
| DE     | non-EU B2B      | nein      | 0        | G    | third_country  |
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from hypothesis import given, strategies as st

from services.invoicing.vat import (
    CustomerSnapshot,
    IssuerSnapshot,
    LineInput,
    compute_vat,
)

PERFORMANCE_DATE = date(2026, 5, 1)


def _issuer(*, kleinunternehmer: bool = False) -> IssuerSnapshot:
    return IssuerSnapshot(
        country_code="DE",
        ust_id="DE123456789" if not kleinunternehmer else None,
        is_kleinunternehmer=kleinunternehmer,
    )


def _customer(*, country: str = "DE", b2b: bool = True, vat_id: str | None = None) -> CustomerSnapshot:
    return CustomerSnapshot(country_code=country, vat_id=vat_id, is_business=b2b)


def _line(qty="1", price="100", rate=None, pos=1, desc="Beratung") -> LineInput:
    return LineInput(
        position=pos,
        description=desc,
        quantity=Decimal(qty),
        unit_price_net=Decimal(price),
        vat_rate_hint=Decimal(rate) if rate is not None else None,
    )


# ── R-06 row: DE → DE B2B Regelbesteuerung (19 %) ───────────────────────────


@pytest.mark.unit
def test_de_b2b_regular_19():
    res = compute_vat(_issuer(), _customer(country="DE", b2b=True), [_line()], PERFORMANCE_DATE)
    assert res.lines[0].vat_rate == Decimal("19.00")
    assert res.lines[0].vat_code == "S"
    assert res.lines[0].line_net == Decimal("100.00")
    assert res.lines[0].line_vat == Decimal("19.00")
    assert res.lines[0].line_gross == Decimal("119.00")
    assert res.subtotal_net == Decimal("100.00")
    assert res.vat_total == Decimal("19.00")
    assert res.total_gross == Decimal("119.00")
    assert res.hints == {"kleinunternehmer": False, "reverse_charge": False, "third_country": False}
    assert res.mandatory_text_keys == []


# ── R-06 row: DE → DE B2C ────────────────────────────────────────────────────


@pytest.mark.unit
def test_de_b2c_regular_19():
    res = compute_vat(_issuer(), _customer(country="DE", b2b=False), [_line()], PERFORMANCE_DATE)
    assert res.lines[0].vat_rate == Decimal("19.00")
    assert res.lines[0].vat_code == "S"
    assert res.mandatory_text_keys == []


# ── R-07: §19 Kleinunternehmer ───────────────────────────────────────────────


@pytest.mark.unit
def test_kleinunternehmer_zero_rate_with_hint():
    res = compute_vat(_issuer(kleinunternehmer=True), _customer(country="DE", b2b=True), [_line()], PERFORMANCE_DATE)
    assert res.lines[0].vat_rate == Decimal("0.00")
    assert res.lines[0].vat_code == "E"
    assert res.lines[0].line_vat == Decimal("0.00")
    assert res.subtotal_net == Decimal("100.00")
    assert res.vat_total == Decimal("0.00")
    assert res.total_gross == Decimal("100.00")
    assert res.hints == {"kleinunternehmer": True, "reverse_charge": False, "third_country": False}
    assert res.mandatory_text_keys == ["kleinunternehmer"]


# ── R-08: EU B2B Reverse-Charge ──────────────────────────────────────────────


@pytest.mark.unit
def test_eu_b2b_reverse_charge_with_vat_id():
    res = compute_vat(
        _issuer(),
        _customer(country="AT", b2b=True, vat_id="ATU12345678"),
        [_line()],
        PERFORMANCE_DATE,
    )
    assert res.lines[0].vat_rate == Decimal("0.00")
    assert res.lines[0].vat_code == "AE"
    assert res.vat_total == Decimal("0.00")
    assert res.hints["reverse_charge"] is True
    assert res.mandatory_text_keys == ["reverse_charge"]


@pytest.mark.unit
def test_eu_b2b_without_vat_id_falls_back_to_b2c_rate():
    """Ohne USt-IdNr. fehlt der Reverse-Charge-Trigger → behandle wie EU-B2C."""
    res = compute_vat(
        _issuer(),
        _customer(country="AT", b2b=True, vat_id=None),
        [_line()],
        PERFORMANCE_DATE,
    )
    assert res.lines[0].vat_rate == Decimal("19.00")
    assert res.lines[0].vat_code == "S"
    assert res.hints["reverse_charge"] is False


# ── R-06 row: EU B2C ─────────────────────────────────────────────────────────


@pytest.mark.unit
def test_eu_b2c_regular_de_rate():
    res = compute_vat(
        _issuer(),
        _customer(country="FR", b2b=False, vat_id=None),
        [_line()],
        PERFORMANCE_DATE,
    )
    assert res.lines[0].vat_rate == Decimal("19.00")
    assert res.lines[0].vat_code == "S"


# ── R-06 row: Drittland B2B ──────────────────────────────────────────────────


@pytest.mark.unit
def test_third_country_b2b():
    res = compute_vat(
        _issuer(),
        _customer(country="US", b2b=True, vat_id=None),
        [_line()],
        PERFORMANCE_DATE,
    )
    assert res.lines[0].vat_rate == Decimal("0.00")
    assert res.lines[0].vat_code == "G"
    assert res.hints["third_country"] is True
    assert res.mandatory_text_keys == ["third_country"]


# ── Vorrang: Kleinunternehmer schlägt Reverse-Charge ────────────────────────


@pytest.mark.unit
def test_kleinunternehmer_overrides_reverse_charge():
    res = compute_vat(
        _issuer(kleinunternehmer=True),
        _customer(country="AT", b2b=True, vat_id="ATU12345678"),
        [_line()],
        PERFORMANCE_DATE,
    )
    assert res.lines[0].vat_code == "E"
    assert res.hints["kleinunternehmer"] is True
    assert res.hints["reverse_charge"] is False


# ── Mehrere Steuersätze (gemischt 19 + 7) ────────────────────────────────────


@pytest.mark.unit
def test_mixed_rates_breakdown():
    res = compute_vat(
        _issuer(),
        _customer(country="DE"),
        [
            _line(pos=1, qty="1", price="100", rate="19"),
            _line(pos=2, qty="1", price="50", rate="7"),
        ],
        PERFORMANCE_DATE,
    )
    rates = {b.rate: (b.base, b.tax) for b in res.breakdown}
    assert rates[Decimal("7.00")] == (Decimal("50.00"), Decimal("3.50"))
    assert rates[Decimal("19.00")] == (Decimal("100.00"), Decimal("19.00"))
    assert res.subtotal_net == Decimal("150.00")
    assert res.vat_total == Decimal("22.50")
    assert res.total_gross == Decimal("172.50")


# ── Rundung HALF_UP, BMF-konform ─────────────────────────────────────────────


@pytest.mark.unit
def test_rounding_half_up_per_line():
    # 33.33 € × 19 % = 6.3327 → 6.33 (HALF_UP)
    res = compute_vat(_issuer(), _customer(country="DE"), [_line(qty="1", price="33.33")], PERFORMANCE_DATE)
    assert res.lines[0].line_net == Decimal("33.33")
    assert res.lines[0].line_vat == Decimal("6.33")


@pytest.mark.unit
def test_rounding_half_up_above_5():
    # 0.025 → 0.03 (not banker's 0.02)
    res = compute_vat(_issuer(), _customer(country="DE"), [_line(qty="1", price="0.13", rate="19")], PERFORMANCE_DATE)
    # 0.13 × 0.19 = 0.0247 → 0.02
    assert res.lines[0].line_vat == Decimal("0.02")


# ── Edge cases ───────────────────────────────────────────────────────────────


@pytest.mark.unit
def test_empty_items_rejected():
    with pytest.raises(ValueError, match="must not be empty"):
        compute_vat(_issuer(), _customer(country="DE"), [], PERFORMANCE_DATE)


@pytest.mark.unit
def test_non_de_issuer_rejected():
    with pytest.raises(NotImplementedError):
        compute_vat(
            IssuerSnapshot(country_code="AT", ust_id="ATU12345678", is_kleinunternehmer=False),
            _customer(country="DE"),
            [_line()],
            PERFORMANCE_DATE,
        )


# ── Property-based: totals consistency ──────────────────────────────────────


@pytest.mark.unit
@given(
    quantities=st.lists(
        st.decimals(min_value="0.01", max_value="100", places=2, allow_nan=False, allow_infinity=False),
        min_size=1, max_size=10,
    ),
    prices=st.lists(
        st.decimals(min_value="0.01", max_value="9999.99", places=2, allow_nan=False, allow_infinity=False),
        min_size=1, max_size=10,
    ),
)
def test_property_totals_match_breakdown(quantities, prices):
    n = min(len(quantities), len(prices))
    items = [
        LineInput(position=i + 1, description=f"Item {i}", quantity=quantities[i], unit_price_net=prices[i])
        for i in range(n)
    ]
    res = compute_vat(_issuer(), _customer(country="DE", b2b=True), items, PERFORMANCE_DATE)
    # subtotal_net == sum of breakdown.base; vat_total == sum of breakdown.tax
    assert res.subtotal_net == sum((b.base for b in res.breakdown), Decimal("0"))
    assert res.vat_total == sum((b.tax for b in res.breakdown), Decimal("0"))
    assert res.total_gross == res.subtotal_net + res.vat_total


@pytest.mark.unit
@given(
    qty=st.decimals(min_value="0.01", max_value="1000", places=2, allow_nan=False, allow_infinity=False),
    price=st.decimals(min_value="0.01", max_value="9999.99", places=2, allow_nan=False, allow_infinity=False),
)
def test_property_kleinunternehmer_zero_vat(qty, price):
    res = compute_vat(
        _issuer(kleinunternehmer=True),
        _customer(country="DE"),
        [LineInput(position=1, description="x", quantity=qty, unit_price_net=price)],
        PERFORMANCE_DATE,
    )
    assert res.vat_total == Decimal("0.00")
    assert res.total_gross == res.subtotal_net


@pytest.mark.unit
@given(
    qty=st.decimals(min_value="0.01", max_value="100", places=2, allow_nan=False, allow_infinity=False),
    price=st.decimals(min_value="0.01", max_value="9999.99", places=2, allow_nan=False, allow_infinity=False),
)
def test_property_eu_b2b_reverse_charge_zero_vat(qty, price):
    res = compute_vat(
        _issuer(),
        _customer(country="ES", b2b=True, vat_id="ESA12345678"),
        [LineInput(position=1, description="x", quantity=qty, unit_price_net=price)],
        PERFORMANCE_DATE,
    )
    assert res.vat_total == Decimal("0.00")
    assert all(ln.vat_code == "AE" for ln in res.lines)
