"""Pure VAT-Engine — keine DB, keine I/O, voll testbar.

Implementiert R-06: Steuerermittlung pro Konstellation
``(Issuer, Customer, Performance-Date)``.

Vorrang der Hinweise (wenn mehrere zuträfen):
    Kleinunternehmer  >  Reverse-Charge  >  Drittland  >  Regelfall

Begründung: Wer §19 nutzt, weist nie USt aus — damit erübrigt sich Reverse-Charge,
selbst wenn der Kunde EU-B2B mit USt-IdNr. ist.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Optional

from .eu_countries import is_eu_country
from .money import D, q2

# Default-Steuersatz, wenn keine Line einen ``vat_rate_hint`` setzt.
DEFAULT_RATE = Decimal("19.00")


# ─── EN16931 VAT category codes ──────────────────────────────────────────────
# S  = Standard rate
# AE = VAT Reverse Charge
# E  = Exempt from VAT (incl. §19 UStG Kleinunternehmer)
# G  = Free export item (Drittland, nicht im Inland steuerbar)
# O  = Services outside scope of tax
# Z  = Zero-rated goods


@dataclass(frozen=True)
class IssuerSnapshot:
    country_code: str
    ust_id: Optional[str]
    is_kleinunternehmer: bool


@dataclass(frozen=True)
class CustomerSnapshot:
    country_code: str
    vat_id: Optional[str]
    is_business: bool


@dataclass(frozen=True)
class LineInput:
    position: int
    description: str
    quantity: Decimal
    unit_price_net: Decimal
    vat_rate_hint: Optional[Decimal] = None  # None → DEFAULT_RATE


@dataclass(frozen=True)
class VatLine:
    position: int
    description: str
    quantity: Decimal
    unit_price_net: Decimal
    vat_rate: Decimal
    vat_code: str
    line_net: Decimal
    line_vat: Decimal
    line_gross: Decimal


@dataclass(frozen=True)
class VatBreakdownRow:
    rate: Decimal     # e.g. Decimal("19.00")
    base: Decimal     # net sum at this rate
    tax: Decimal      # VAT amount


@dataclass(frozen=True)
class VatResult:
    lines: list[VatLine]
    subtotal_net: Decimal
    vat_total: Decimal
    total_gross: Decimal
    breakdown: list[VatBreakdownRow]
    hints: dict[str, bool] = field(default_factory=dict)
    mandatory_text_keys: list[str] = field(default_factory=list)


# ─── Implementation ──────────────────────────────────────────────────────────


def _resolve_constellation(issuer: IssuerSnapshot, customer: CustomerSnapshot) -> tuple[bool, str, list[str]]:
    """Return (zero_rate, vat_code_when_zero, mandatory_text_keys).

    Wenn ``zero_rate`` False, gilt der per-Line-Hint (oder DEFAULT_RATE) und der
    Code ist ``S``. Wenn ``zero_rate`` True, wird die Rate aller Lines auf 0
    gezwungen und der zurückgegebene Code verwendet.
    """
    iss_country = (issuer.country_code or "").upper()
    cust_country = (customer.country_code or "").upper()

    # Aktuell unterstützen wir nur DE als Aussteller (R-06 Tabelle).
    if iss_country != "DE":
        raise NotImplementedError(
            f"Aussteller außerhalb DE ({iss_country!r}) wird in v1 nicht unterstützt. "
            "Siehe docs/open-questions.md."
        )

    # Kleinunternehmer (§19 UStG) — höchste Priorität, blockiert alle anderen Hinweise.
    if issuer.is_kleinunternehmer:
        return True, "E", ["kleinunternehmer"]

    # EU B2B mit gültiger USt-IdNr. → Reverse-Charge.
    if (
        cust_country != "DE"
        and is_eu_country(cust_country)
        and customer.is_business
        and customer.vat_id
    ):
        return True, "AE", ["reverse_charge"]

    # Drittland B2B → nicht im Inland steuerbar.
    if cust_country and not is_eu_country(cust_country) and cust_country != "DE" and customer.is_business:
        return True, "G", ["third_country"]

    # Regelfall: DE B2B / DE B2C / EU B2C → dt. USt nach Line-Hint.
    return False, "S", []


def compute_vat(
    issuer: IssuerSnapshot,
    customer: CustomerSnapshot,
    items: list[LineInput],
    performance_date: date,  # noqa: ARG001 — heute ungenutzt; reserviert für zukünftige Sondersätze
) -> VatResult:
    """Berechne USt pro Line + Totals + per-Rate-Breakdown.

    Rundung pro Line auf 2 NK (ROUND_HALF_UP), dann Per-Rate-Summe aus den
    bereits gerundeten Line-Nets, erneut quantisiert (BMF-konform).
    """
    if not items:
        raise ValueError("compute_vat: items must not be empty")

    zero_rate, zero_code, text_keys = _resolve_constellation(issuer, customer)

    lines: list[VatLine] = []
    for item in items:
        quantity = D(item.quantity)
        unit_price = D(item.unit_price_net)
        if zero_rate:
            rate = Decimal("0.00")
            code = zero_code
        else:
            rate = D(item.vat_rate_hint) if item.vat_rate_hint is not None else DEFAULT_RATE
            code = "S"
        line_net = q2(quantity * unit_price)
        line_vat = q2(line_net * rate / Decimal(100))
        line_gross = q2(line_net + line_vat)
        lines.append(VatLine(
            position=item.position,
            description=item.description,
            quantity=quantity,
            unit_price_net=unit_price,
            vat_rate=rate,
            vat_code=code,
            line_net=line_net,
            line_vat=line_vat,
            line_gross=line_gross,
        ))

    # Per-rate breakdown — gruppiere nach rate, summiere bereits gerundete Werte.
    per_rate: dict[Decimal, list[VatLine]] = {}
    for ln in lines:
        per_rate.setdefault(ln.vat_rate, []).append(ln)
    breakdown: list[VatBreakdownRow] = []
    for rate in sorted(per_rate.keys()):
        ls = per_rate[rate]
        base = q2(sum((ln.line_net for ln in ls), Decimal("0")))
        tax = q2(sum((ln.line_vat for ln in ls), Decimal("0")))
        breakdown.append(VatBreakdownRow(rate=rate, base=base, tax=tax))

    subtotal_net = q2(sum((b.base for b in breakdown), Decimal("0")))
    vat_total = q2(sum((b.tax for b in breakdown), Decimal("0")))
    total_gross = q2(subtotal_net + vat_total)

    hints = {
        "kleinunternehmer": "kleinunternehmer" in text_keys,
        "reverse_charge": "reverse_charge" in text_keys,
        "third_country": "third_country" in text_keys,
    }

    return VatResult(
        lines=lines,
        subtotal_net=subtotal_net,
        vat_total=vat_total,
        total_gross=total_gross,
        breakdown=breakdown,
        hints=hints,
        mandatory_text_keys=text_keys,
    )
