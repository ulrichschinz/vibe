# ADR-017: `services/mcp_server.py` → `app/interfaces/mcp/server.py` relozieren (Remediation-Track T7-D)

**Status:** Akzeptiert (2026-05-21)

## Kontext

Vierter und letzter T7-Schritt — nach T7-A (`models.py`, ADR-014), T7-B
(`services/ai.py`, ADR-015) und T7-C (`services/linkedin_import.py`,
ADR-016) der einzige verbleibende Knoten aus Audit-Befund R2 (Schicht-
Hygiene `services/` ↔ `app/`).

**Andere Mechanik als T7-A/B/C.** T7-A/B/C waren Shim-Tode: physisch tote
Re-Export-Shims, deren letzte Importer retargetet wurden, dann Datei
weg. T7-D ist ein **Move-not-rewrite eines lebenden 363-LOC-Moduls** —
der FastMCP-Server selbst, mit allen 16 `@mcp.tool`-Definitionen +
modul-globalem `engine`. Inhalt unverändert (außer Datei-eigenes
Docstring — §C); nur Pfad.

ADR-009 §B (Schritt 8) hat den Move explizit zum *deferred Lifecycle-
Endpunkt* erklärt — der `m.engine`-Monkeypatch-Seam (in
`tests/characterization/conftest.py::mcp_module`) durfte unter Schritt 8
nicht brechen, also blieb die Datei verbatim in `services/`. T7-D ist
*genau* dieser Endpunkt; CLAUDE.md (Statusbanner) markiert ihn
ausdrücklich („T7-D-Move-Endpunkt").

### Ist-Aufnahme (Recon, vor dem Schnitt)

- **Datei**: 363 LOC, FastMCP-Instanz `mcp` (Modul-Global, Z. 26) + 16
  `@mcp.tool`-Decorator-Definitionen + Modul-Global `engine` (importiert
  aus `database`, Z. 13, der eigentliche Seam-Anker). Schritt 7 hat die
  Lead/Note/Proposal-Tools dünn gemacht (Delegation an
  `app/domains/*/service.py`); Schritt 8 die Invoice-Tools durch die
  Billing-MCP-Facade gezogen. Inhalt damit byte-stabil seit Schritt 8.
- **Produktiv-Importer**: genau **2 Stellen** —
  `app/interfaces/mcp/__init__.py:17` (`from services.mcp_server import
  mcp`) und `app/interfaces/mcp/mount.py:20` (gleiche Zeile). Beide
  ziehen nur `mcp` (das FastMCP-Objekt). `main.py` importiert nur
  indirekt via `from app.interfaces import mcp as mcp_iface` — unverändert.
- **Test-Importer**: genau **1 Stelle** —
  `tests/characterization/conftest.py:81` im `mcp_module`-Fixture
  (`import services.mcp_server as m` →
  `monkeypatch.setattr(m, "engine", …)`). **Das** ist der frozen Seam
  aus ADR-008/009 §B. Sonst keine.
- **Import-Linter-Regel**: 1 Eintrag in `pyproject.toml`
  (Z. 213-222), Forbidden-Contract `services.mcp_server ↛
  app.domains.{leads,proposals,billing}.models`. Sowohl `name` als auch
  `source_modules` tragen den alten Pfad.

### Keine neuen Sonderfälle

Anders als T7-B (`generate_proposal_drafts` lebt in
`proposals.service`, nicht in `core.ai`) gibt es bei T7-D keine
Layering-Subtilität — der Move zieht die ganze Datei verbatim um. Auch
anders als T7-A/B/C: das Shim-Inventar ändert sich **nicht**, weil
`mcp_server` keine Re-Export-Shim ist (Body enthält Funktions-
Definitionen, kein reines `Import`+`__all__`-Muster); der T6-AST-Walk
in `scripts/check_architecture_metrics.py::_is_reexport_shim` klassifiziert
das Modul korrekt als Nicht-Shim.

## Entscheidungen

### §A — `git mv` statt Neuschreiben

Inhalt der Datei bleibt **semantisch byte-identisch** (außer dem datei-
eigenen Docstring §C; F401-`select`-Drop §G; Format-Konformitäts-Bump §H).
Begründung: das Modul ist seit Schritt 7/8 strukturell sauber (Tools dünn,
keine Modell-Konstruktion), und der move-not-rewrite-Modus aus Audit-
Decision E1 verbietet inhaltliche Bonus-Sweeps in Track-PRs. Die
Compliance-Naht (`engine` als modul-globales Symbol) zieht 1:1 mit.

### §B — Patch-Naht: das `app.interfaces.mcp.server`-Modul-Objekt selbst

Identisch zum T7-B/T7-C-Muster (ADR-015 §A, ADR-016 §A): der Test
patcht ein **Modul-Attribut** (`engine`). `monkeypatch.setattr(m,
"engine", …)` bindet sich nicht an einen Pfad-String, sondern an das
Modul-Objekt `m`. Solange Produktion und Test dasselbe `sys.modules`-
Objekt auflösen — und das tun sie, weil der Modul-Cache pfad-eindeutig
ist — bleibt die Patch-Semantik byte-identisch. Einzige Mechanik-
Änderung: `import services.mcp_server as m` → `import
app.interfaces.mcp.server as m` in der einen `mcp_module`-Fixture-Zeile.

### §C — Datei-eigenes Docstring aktualisieren (einzige Inhaltsabweichung)

Das Docstring von `services/mcp_server.py` (jetzt
`app/interfaces/mcp/server.py`, Z. 1-5) referenziert noch `routes/mcp.py`
als Mount-Punkt. `routes/mcp.py` existiert seit Schritt 8 nicht mehr (der
Mount lebt in `app/interfaces/mcp/mount.py`). Das Docstring wird
mitgezogen auf den aktuellen Pfad — formal eine Inhalts-Abweichung
gegenüber der reinen Move-Disziplin, aber begründet:

1. Die Doku war seit Schritt 8 bereits **falsch** (Stale, kein zusätzlicher
   Drift, sondern Korrektur eines historischen Drifts);
2. Im selben PR den korrekten neuen Pfad nachzuziehen ist billiger als
   einen Folge-PR;
3. Der Doc-Gate prüft keine inneren Docstrings (nur ARCHITECTURE.md-
   Kennzahlen + Strukturverträge + Shim-Inventar).

### §D — Import-Linter-Regel umbenennen (kein Schärfen)

`pyproject.toml`-Contract behält Typ + Forbidden-Set; **nur**
`source_modules` und `name`-String ziehen auf
`app.interfaces.mcp.server` um. Die Regel-Wirkung bleibt identisch
(direkter Modell-Import bleibt verboten), aber sie folgt jetzt dem neuen
Modul-Pfad — und der `name=`-Eintrag bleibt synchron zur
`ARCHITECTURE.md`-Struktur-Verträge-Tabelle (sonst kippt der T6-Doc-Gate).
Keine neue Regel; keine zusätzliche Härtung über das hinaus, was Schritt
7/8 bereits gesetzt haben.

### §E — Doku-Sweep

- `ARCHITECTURE.md`: Tree-Eintrag (`services/` verliert `mcp_server.py`,
  `app/interfaces/mcp/` gewinnt `server.py`), Kennzahlen-Tabelle Zeile
  „MCP-Tools" zeigt neuen Pfad, Datenmodell-Block + Schritt-7-/Schritt-8-
  Bezüge, Struktur-Verträge-Regel-Name synchron zu `pyproject.toml`.
  **LOC-Kennzahlen bleiben unverändert** (Move; Gesamt + Prod gleich).
- `README.md`: Tree-Eintrag (Zeile 77) — alte `mcp_server.py`-Zeile
  retargeted auf neuen Pfad.
- `CLAUDE.md`: Statusbanner-Sync — T7-D-Endpunkt ist jetzt erfüllt
  (ADR-009 §B ist „eingelöst").
- `docs/remediation-backlog.md`: T7-D ✅ mit Mechanik-Beschreibung
  (analog T7-A/B/C-Format).
- ADRs 008/009 **nicht editiert** (historischer Record — gleiche Disziplin
  wie bei T7-A/B/C). Cross-Referenz auf ADR-017 lebt im
  Statusbanner + Backlog, nicht im historischen ADR-Text.

### §G — F401-`select`-Drop

`from sqlmodel import Session, select` mit ungenutztem `select`: F401-
Befund, der erst durch den Move ins ruff-Scope sichtbar wurde
(`services/` war pre-T7-D nicht gelintet). `select` ist seit Schritt 7
(MCP-Entdopplung — Queries wandern nach `app/domains/*/service.py`)
genuin tot. 1-Symbol-Drop, 0-LOC-Diff (`from sqlmodel import Session`
bleibt eine Zeile). Disziplin-konform mit der `web/api`-Präzedenz
(F401 bleibt aktiv, E712/E741 ignored).

### §H — Format-Konformitäts-Bump

`ruff format` reformatiert `app/`-Bewohner; `services/`-Bewohner waren
ausgenommen (siehe `pyproject.toml [tool.ruff.format]`-Scope-Kommentar +
Makefile `format-check`). Mit dem Move zieht die Format-Conformance mit —
`ruff format app/interfaces/mcp/server.py` liefert +6 LOC (Leerzeilen
nach Section-Komment-Bannern + zwei Mehrzeilen-Aufrufe in
`finalize_invoice`/`create_storno`). Rein kosmetisch, keine semantische
Änderung. Eine zusätzliche per-file-ignore
`"app/interfaces/mcp/server.py" = ["E402"]` in
`[tool.ruff.lint.per-file-ignores]` deckt die deliberaten Late-Imports der
Invoice-Tool-Gruppe (Z. 253ff. — Schritt-8-Schema, Layout-Debt analog
`web/*`/`api/*`).

### §F — Was bewusst **nicht** Teil dieser PR ist

- **`routes/{leads,proposals}.py`-Shim-Tod**: kein eigenes T-Item, fällt
  mit der nächsten Char-Test-Reorganisation. Inventar-Zähler-Ziel: 0
  (heute 2).
- **`services/`-Verzeichnis-Tod**: nach T7-D verbleiben in `services/`:
  `auth.py`, `numbering.py`, `pdf.py`, `proposals.py`, `__init__.py`,
  `invoicing/`. Das ist kein „Random Code in Random Files" mehr —
  `auth/numbering/pdf/proposals` sind echte Reusable-Kernel-Services
  (von `app/interfaces/*` und `app/domains/*/service` genutzt) +
  `invoicing/` ist Compliance-Move-not-rewrite (Audit-Decision E1).
  Die optionale Konsolidierung dieser vier zu `app/core/*` ist
  Roadmap-Folge-Material, kein Remediation-Track-Item.

## Konsequenzen

- **Strukturell:** `app/interfaces/mcp/server.py` ist jetzt der physische
  Home von `mcp` + 16 Tools + `engine`. `services/` enthält keine
  Interface-Schicht mehr — die Schicht-Hygiene aus dem Soll-Skelett
  (Schritt 2) ist auf der Interface-Achse vollständig.
- **Shim-Inventar unverändert** (mcp_server war nie ein Re-Export-Shim):
  T6-Gate-Output meldet weiter `5 import-linter contracts and 2 re-export
  shims accounted for`.
- **Patch-Naht lokalisiert:** Eine Test-Importer-Zeile retargeted; zwei
  Prod-Importer-Zeilen retargeted; eine Linter-Regel umbenannt. Sonst
  byte-identisch.
- **Compliance-Naht unangetastet:** der `engine`-Modul-Global zieht 1:1
  mit, der monkeypatch-Mechanismus bleibt; `services/invoicing/`-
  Verhalten (90 %-Gate, ZUGFeRD, §14 UStG) ist nicht berührt.
- **132 Char-Tests + 90 %-Invoicing-Suite + Integration + e2e:
  0-Behavior-Diff** (CI-verifiziert; lokal nicht laufbar — Schritt-1-
  Constraint).
- **Doc-Gate-Sync im selben Change:** ARCHITECTURE.md (Tree-Refs,
  Datenmodell-Refs, Struktur-Verträge-Regel-Name, LOC-Subtotals) + README.md
  + CLAUDE.md Banner-Sync + Backlog-Eintrag + Doc-Gate-Skript
  (`scripts/check_architecture_metrics.py::m_mcp_tools` zählt jetzt am
  neuen Pfad). Doc-Gate grün: `12.254 / 8.646 / 3.608` (Prod +10, Tests +4,
  Total +14 — Naht-Docstring-Erweiterungen +8 wie geplant, plus
  Format-Conformance-Bump +6 §H). Datei-Inhalt = semantisch byte-äquivalent
  bis auf Docstring §C, F401-Drop §G und Format §H — alles dreierlei
  rein kosmetisch, kein Verhaltens-Diff.

## Folge-Schritte

R2 strukturell **vollständig** zu (T7-A + T7-B + T7-C + T7-D). T7
abgeschlossen.

Offen im Remediation-Track: D2b (Off-Host-Backup-Automatik, Ops, Infra-
Entscheidung erforderlich) und optional D5 (Staging-Umgebung). Die
`routes/{leads,proposals}.py`-Test-Shims sterben mit der nächsten Char-
Test-Reorganisation (kein eigenes T-Item).
