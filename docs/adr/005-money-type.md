# ADR-005: Money-Datentyp

**Status:** Akzeptiert (2026-05-09)

## Kontext

Das bestehende Proposal-Modul speichert Beträge als `Optional[float]` —
fehleranfällig (binäre Float-Repräsentation, Akkumulationsfehler) und für
Rechnungen ungeeignet. Wir müssen entscheiden, wie wir Geld in der neuen
Welt repräsentieren.

## Optionen geprüft

1. **`decimal.Decimal`** *(gewählt)*
2. **Integer Cents (z. B. `100` für 1,00 €)**
3. **Library wie `py-moneyed`** (Decimal + Currency-Typ)

## Entscheidung

**Option 1.** Stdlib `decimal.Decimal`, gespeichert in SQLAlchemy
`Numeric(precision=12, scale=2)`. Helper in `services/invoicing/money.py`:
- `D(x)` — Coercion (mit string-roundtrip für floats).
- `q2(x)` — Quantize auf 2 NK, ROUND_HALF_UP.
- `q4(x)` — Quantize auf 4 NK (für Mengen).
- `format_eur_de(x)` — `1.234.567,89 €`.

Alle Arithmetik in der Invoicing-Engine läuft durch `q2`/`q4`. Floats werden
nirgends verwendet.

## Begründung

- **Stdlib-only**: Keine zusätzliche Library, keine Wartungskosten.
- **Decimal**: Native Pydantic/SQLAlchemy-Unterstützung; Decimals serialisieren
  verlustfrei in JSON (als String) und in das EN16931-XML.
- **ROUND_HALF_UP**: BMF-konform für USt-Berechnung. Banker's Rounding
  (ROUND_HALF_EVEN) ist hier explizit *nicht* gewünscht.
- **`Numeric(12, 2)`**: Erlaubt Beträge bis ±999.999.999,99 — für unseren Use-
  Case völlig ausreichend.
- **Quantity scale=4**: Erlaubt z. B. 0,5 Stunden oder 12,5 km ohne Verlust.

## Konsequenzen

**Positiv:**
- Korrekte Arithmetik (kein 0,1 + 0,2 = 0,30000…04).
- BMF-konformes Runden out of the box.
- Verlustfreie XML-/JSON-Serialisierung.

**Negativ:**
- Performance: Decimal ist ~10× langsamer als float. Bei dutzenden Lines pro
  Rechnung und dutzenden Rechnungen pro Jahr irrelevant.
- Pydantic v1 hatte Edge Cases mit Decimal-Validierung; SQLModel + Pydantic v2
  funktionieren sauber.

## Alternativen verworfen

- **Integer Cents:** Lesbarkeit leidet (alles ×100, ÷100), und für USt-Sätze in
  Prozent (19, 7) braucht man entweder einen zweiten Typ oder verliert
  Cent-Genauigkeit beim Multiplizieren. Decimal löst beides natürlich.
- **`py-moneyed`:** Bringt Currency-Typ, der bei Mehrwährung wertvoll wäre —
  aber wir machen v1 Single-Currency (EUR). Library-Pin + zusätzliche
  Wartungslast lohnen nicht.

## Verifikation

- `tests/unit/test_money.py` — Coercion, Rounding, Format, Property-Tests.
- `tests/unit/test_vat_engine.py::test_rounding_half_up_per_line` — BMF-konformes
  Runden auf Line-Ebene.
- `tests/unit/test_vat_engine.py::test_property_totals_match_breakdown` — über
  hypothesis: Subtotals == Sum(Line-Nets), unabhängig von der Verteilung.
