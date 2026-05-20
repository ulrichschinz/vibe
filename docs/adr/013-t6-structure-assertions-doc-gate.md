# ADR-013: Struktur-Assertions im Doc-Gate (Remediation-Track T6)

**Status:** Akzeptiert (2026-05-20)

## Kontext

Das adversariale Audit (`docs/audit-report-scaling-roadmap.md`, Befund R5)
hielt fest: die Struktur-Prosa in `ARCHITECTURE.md` (Schichten, Verträge,
verbleibende Shims) ist heute **driftbar ohne CI-Rot**. Die Kennzahlen-
Tabelle wird zwar von `scripts/check_architecture_metrics.py` gegen den
Code gepinnt (Schritt 0); zwischen der Schichten-Prosa und den
ausführbaren `import-linter`-Verträgen bzw. zwischen Doku und den
verbleibenden Re-Export-Shims fehlte die Selbst-Verifikation. Ein
Maintainer konnte einen Contract umbenennen, einen Shim sterben lassen
oder eine zusätzliche Naht einziehen, ohne dass die `ARCHITECTURE.md`
nachgezogen wurde — Doku driftet stiller weiter.

Remediation-Track-Item **T6** (`docs/remediation-backlog.md`): den
bestehenden stdlib-Doc-Gate erweitern, statt einen zweiten Mechanismus
einzuführen — gleiches Tooling (Schritt 0, `scripts/`), gleicher Lauf-Pfad
(PR-`make verify`, always-on `doc-metrics.yml`, Pre-Deploy-`deploy.yml`),
keine neue Build-Stufe. Randbedingung (S4–S9-Lektion, unverändert):
**kein lokaler Interpreter mit App-Deps** → die Erweiterung muss
stdlib-only bleiben.

## Entscheidungen

### §A — Erweiterung des bestehenden Gates, kein Neben-Skript

Die beiden neuen Asserter (`check_importlinter_contracts`,
`check_shim_inventory`) leben in `scripts/check_architecture_metrics.py`
und werden aus dessen `main()` mit aufgerufen. **Begründung:** das Skript
ist bereits der vereinbarte „Doc-Gate" (CLAUDE.md), läuft schon in allen
drei CI-Pfaden + lokal, und ist explizit stdlib-only. Ein Schwester-
Skript zu schreiben würde Pfade duplizieren (Make-Target, CI-Job,
`.gitignore`-Disziplin) ohne Mehrwert. Konsequent zur Schritt-1-
Direktive „der Doc-Gate ist *eine* stdlib-Schraube".

### §B — Zwei Tabellen, gegen zwei separate Quellen

`ARCHITECTURE.md` deklariert die Wahrheit explizit:

1. **`## Struktur-Verträge (CI-erzwungen)`** — der Set aller `name`-Werte
   der `[[tool.importlinter.contracts]]`-Blöcke in `pyproject.toml`.
2. **`## Re-Export-Shim-Inventar (CI-erzwungen)`** — Pfad + LOC jeder
   trivialen Re-Export-Datei.

Der Gate prüft Mengen-Gleichheit (Drift in *beide* Richtungen → CI-Rot).
**Begründung:** die zwei Aspekte haben unterschiedliche Quellen
(`pyproject.toml` vs. AST-Walk der Prod-`.py`-Bäume) und unterschiedliche
Lebenszyklen (Verträge wachsen pro Aktivierungs-Schritt; Shims sterben
einzeln in Remediation-Track T7). Eine Mischtabelle würde beide
Bewegungen verschmieren.

### §C — Detection-Stack: Regex auf TOML, AST auf Python

Für `pyproject.toml`: Zeilen-State-Machine (`[[tool.importlinter.contracts]]`
→ `name = "..."` → bis zur nächsten Section-Marke), `name`-Werte als
Set extrahiert. **Begründung:** identisches Muster wie ADR-012 §B
(Scaffold-Patcher) — Rationale-Kommentare und Layout bleiben unverändert
neben den Verträgen erhalten; ein Roundtrip-Serializer würde sie
verlieren. Stdlib-only, kein `tomli_w`/`tomlkit`.

Für Shim-Discovery: `ast.parse` + Body-Klassifikation. Ein Modul ist ein
„trivialer Re-Export-Shim", wenn sein Body — nach optionalem Docstring —
**ausschließlich** `Import`/`ImportFrom` plus höchstens eine
`__all__`-Assign-Statement enthält (keine `def`/`class`, keine andere
Assign). **Begründung:** das ist die strukturelle Signatur aller fünf
heute existierenden Shims; andere Dateien (`app/shared/labels.py` mit
Daten-Dicts, `app/__init__.py` als reine Docstring-Datei,
`routes/__init__.py` leer) fallen *automatisch* raus. Ein Marker-String
in der Docstring (z. B. „Re-export shim") wäre fragiler (drei der fünf
Shims schreiben „Re-export shim", `models.py` schreibt „Backward-compat
shim" — Wortlaut driftet, Struktur driftet selten).

### §D — Tests/-Bäume außerhalb der Shim-Discovery

Die Discovery überspringt `tests/` zusätzlich zu `_EXCLUDED_DIRS`.
**Begründung:** Shims sind ein strukturelles Artefakt des
Produktiv-Code-Umzugs (Move-not-rewrite-Naht), nicht des Tests. Ein
Test-Fixture mit derselben AST-Signatur (Imports + `__all__`) wäre kein
Sterbe-Kandidat für T7 und gehört nicht in den Inventar-Gate.

### §E — Drift-Meldungen nennen die Aktion, nicht nur das Symptom

Drift-Meldungen sind formuliert als *„drop the row"* / *„restore the
shim"* / *„T7 shim-death gates"* — der Maintainer bekommt aus dem CI-Log
direkt die Handlungsanweisung. **Begründung:** Audit-Lektion R5 war
nicht „Doku ist falsch", sondern „Doku-Korrektur ist unklar"; ein
selbst-erklärender Gate spart einen Doc-Lookup.

## Konsequenzen

**Positiv:**
- Vier Drift-Wege schließen: Contract umbenannt / hinzugefügt / entfernt
  ohne Doku-Sync, Shim-LOC drifted, Shim entstanden ohne Inventar-Eintrag,
  Shim gestorben ohne Inventar-Bereinigung.
- T7 hat einen lebenden Zähler (`5 re-export shims accounted for` im
  Gate-Output): jeder Shim-Tod erscheint dort und in der Tabelle.
- Schichten-Prosa und ausführbarer Vertrag haben jetzt eine *prüfbare*
  Brücke, statt nebeneinander zu existieren.

**Negativ / akzeptiert:**
- Die `name`-Strings der Verträge sind lang und enthalten Em-Dashes,
  Parens, Kommas. Sie zu refaktorieren bedeutet jetzt Doku-Sync in
  einem Atemzug — bewusst (das ist der R5-Hebel).
- Die AST-Shim-Discovery toleriert keinen Shim, der z. B. eine
  Hilfsfunktion exportiert. Wird ein heutiger Shim um eine Funktion
  erweitert, fällt er aus der Discovery — der Gate fordert dann
  entweder Bereinigung oder Inventar-Anpassung (genau das Verhalten,
  das R5 schließt). Das ist nicht eine Lockerung von „what is a shim",
  sondern die explizite Antwort.

**Versiegelt:** Die zwei Tabellen sind die einzige Stelle, an der
Struktur-Verträge und Shims dokumentiert werden — Prosa kann
weiterleben, ist aber nicht mehr die Wahrheits-Schicht.

## Verifikation

- **Lokal (stdlib-only, ohne App-Deps):**
  - `python3 scripts/check_architecture_metrics.py` (grün; bestätigt
    `5 import-linter contracts and 5 re-export shims accounted for`).
  - Drift-Self-Test (siehe PR-Beschreibung): 6 Mutationen,
    je passender Befund — phantom-contract / removed-contract /
    LOC-drift / phantom-shim-path / removed-shim-row / missing-heading.
- **CI (`make verify` + `doc-metrics.yml` + `deploy.yml`):**
  Skript-Erweiterung greift in allen drei Pfaden ohne YAML-Änderung,
  weil sie alle dasselbe Skript ausführen.
- **Doc-Gate selbst:** 0-Diff zur Kennzahlen-Tabelle (Änderungen
  liegen in `scripts/` und `ARCHITECTURE.md`; keine Python-LOC bewegt).
- **Probe-Lint:** 0-Diff (T6 berührt keine `.expected`-Dateien).

## Referenzen

- Audit-Befund R5: `docs/audit-report-scaling-roadmap.md`
- Backlog-Item T6: `docs/remediation-backlog.md`
- Doc-Gate (Schritt 0): `scripts/check_architecture_metrics.py`
- Schwester-ADRs: ADR-009 (Interface-Split — Schichten-Prosa),
  ADR-011 (T2 Web/REST-Modellsperre — neueste aktive Regel),
  ADR-012 (T5 Scaffold-Independence-Contract — gleicher TOML-Patch-Stil)
