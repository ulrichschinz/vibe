"""Decimal-Helpers für Rechnungs-Beträge.

Money darf NIE als float gerechnet werden. Diese Helper kapseln den korrekten
``decimal.Context`` (28 Stellen Präzision, ROUND_HALF_UP — BMF-konform) und die
Quantisierung auf Cent (q2) bzw. 4 Nachkommastellen für Mengen (q4).

Begründung in ``docs/adr/005-money-type.md``.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP, localcontext
from typing import Any

_CENT = Decimal("0.01")
_QUANTITY = Decimal("0.0001")


def D(x: Any) -> Decimal:
    """Coerce to ``Decimal`` losslessly. Floats are converted via ``str`` first.

    >>> D("1.23")
    Decimal('1.23')
    >>> D(1)
    Decimal('1')
    >>> D(1.10)        # would be Decimal('1.1000000000000000888...') if naive
    Decimal('1.1')
    """
    if isinstance(x, Decimal):
        return x
    if isinstance(x, float):
        return Decimal(str(x))
    if isinstance(x, (int, str)):
        return Decimal(x)
    raise TypeError(f"cannot coerce {type(x).__name__} to Decimal")


def q2(x: Any) -> Decimal:
    """Quantize to two decimal places (cents) using ROUND_HALF_UP."""
    with localcontext() as ctx:
        ctx.prec = 28
        ctx.rounding = ROUND_HALF_UP
        return D(x).quantize(_CENT)


def q4(x: Any) -> Decimal:
    """Quantize to four decimal places (quantity precision)."""
    with localcontext() as ctx:
        ctx.prec = 28
        ctx.rounding = ROUND_HALF_UP
        return D(x).quantize(_QUANTITY)


def format_eur_de(x: Decimal | None) -> str:
    """German-locale EUR formatting: ``1.234.567,89 €``.

    Nullable input renders as a long em-dash to match the existing proposal
    template convention. Negative values get a leading minus.
    """
    if x is None:
        return "—"
    val = q2(x)
    sign = "-" if val < 0 else ""
    n = abs(val)
    int_part, _, frac = format(n, "f").partition(".")
    # frac is either '' or 'NN'
    frac = (frac + "00")[:2]
    # Insert thousands separators (German uses '.').
    rev = int_part[::-1]
    chunks = [rev[i:i + 3] for i in range(0, len(rev), 3)]
    int_with_seps = ".".join(chunks)[::-1]
    return f"{sign}{int_with_seps},{frac} €"
