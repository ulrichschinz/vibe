# ADR-003: Rechnungsnummern-Vergabe

**Status:** Akzeptiert (2026-05-09)

## Kontext

R-02 fordert atomare, lückenlose, je Geschäftsjahr eindeutige Rechnungsnummern.
SQLite kennt kein `SELECT … FOR UPDATE`. Wir brauchen einen Mechanismus, der
auch unter parallelen Finalize-Aufrufen korrekt serialisiert.

## Optionen geprüft

1. **`BEGIN IMMEDIATE` + Sequence-Tabelle pro Jahr** *(gewählt)*
2. **`max(sequence_number) + 1` ohne explizites Locking** *(Status quo bei `services/numbering.py`)*
3. **Postgres mit `SELECT FOR UPDATE`** (Migration weg von SQLite)
4. **UUID-basierte Nummern** (Ad-hoc, nicht lückenlos)

## Entscheidung

**Option 1.** Eine Tabelle `invoicenumbersequence(fiscal_year PK, last_sequence)`
mit genau einer Zeile pro Geschäftsjahr. Beim Finalize:

```python
# 1. Reservierter SQLite-Lock per BEGIN IMMEDIATE (Engine-Event)
# 2. SELECT … FROM invoicenumbersequence WHERE fiscal_year = Y
# 3. last_sequence += 1
# 4. UPDATE …  → flush
# 5. nutzen für Invoice-Nummer
# 6. Restliche Finalize-Schritte
# 7. COMMIT (oder ROLLBACK bei Fehler — kein Counter verbraucht)
```

`busy_timeout=5000ms` sorgt dafür, dass ein zweiter Writer beim BEGIN IMMEDIATE
wartet, statt mit `database is locked` zu scheitern.

## Begründung

- **SQLite-konform:** Keine Postgres-Migration nötig.
- **Race-safe:** BEGIN IMMEDIATE serialisiert Write-Transaktionen auf Connection-
  Ebene; in Kombination mit busy_timeout halten 30+ parallele Threads die
  Folge dicht (`tests/integration/test_numbering_concurrency.py`).
- **Lückenlosigkeit:** Da die Counter-Inkrementierung in derselben Transaktion
  passiert wie das `UPDATE invoice` mit der neuen Nummer, sorgt ein
  Rollback (z. B. wegen Render-Fehler) dafür, dass die Nummer nicht verbraucht
  wird. Eine Lücke entsteht nur, wenn nach erfolgreichem COMMIT etwas
  Off-System schiefgeht — was per Definition nicht passiert.

## Konsequenzen

**Positiv:**
- Funktioniert mit dem bestehenden Stack ohne Migration.
- Performance-Auswirkung minimal (Schreibrate dutzende/Jahr).

**Negativ:**
- BEGIN IMMEDIATE serialisiert *alle* Writes, nicht nur Invoice-Finalize.
  Bei niedrigem Schreibaufkommen kein Problem; bei höherer Last könnte das
  bottleneck werden. Mitigation: zukünftig auf Postgres umsteigen.
- Wenn jemand `BEGIN DEFERRED` auf einer dedizierten Connection ausführt
  (z. B. eine Background-Aufgabe), könnte er den Counter sehen, bevor die
  Finalize-Transaktion committet hat. Auf unseren Single-Worker, niedrig-
  parallelen Stack hat das keine Auswirkungen.

## Alternativen verworfen

- **Status quo (`count() + 1`):** Race-Anfällig. Bei `services/numbering.py`
  (Proposals) bleibt der Bug bestehen — out of scope für diesen Auftrag, in
  `docs/open-questions.md` dokumentiert.
- **Postgres-Migration:** Lohnt sich erst, wenn die App in Mehrfach-Worker /
  HA-Setups läuft.
- **UUIDs:** Verletzen R-02 (lückenlos, einmalig pro Jahr).

## Verifikation

- `tests/integration/test_numbering.py` deckt Format, Monotonie und Jahres-
  Boundary ab.
- `tests/integration/test_numbering_concurrency.py` startet 30 Threads, die
  alle `assign_next_number` aufrufen; das Ergebnis ist eine dichte
  `1..30`-Folge ohne Doppler.
