# ADR-015: `services/ai.py`-Shim sterben lassen (Remediation-Track T7-B)

**Status:** Akzeptiert (2026-05-20)

## Kontext

Zweiter T7-Schritt — nach T7-A (`models.py`, ADR-014) der zweite der
ursprünglich 3–4 Shim-Sterbe-Gates aus Audit-Befund R2. Anders als T7-A
ist `services/ai.py` **kein** Aggregations-Modul, sondern eine reine
**monkeypatch-Naht** für die frozen Schritt-0.5-Char-Tests
(`tests/characterization/test_proposals_routes.py`,
`tests/integration/test_proposal_from_plan.py`) plus den
Schritt-6-Unit-Test `tests/unit/test_ai_proposal_drafts.py`. Die zu
beantwortende Frage war nicht „wer übernimmt die Rolle" (keine), sondern
„wie verschiebt man den Patch-Punkt **ohne** die Test-Assertions zu
ändern und ohne neue Verhaltensänderung".

### Ist-Aufnahme (Recon, vor dem Schnitt)

- **Shim**: 35 LOC. Re-exportiert 8 Symbole — 7 aus `app.core.ai`
  (`AiDraftError`, `PROPOSAL_DRAFTS_SYSTEM`, `SYSTEM_PROMPTS`,
  `_call_anthropic`, `_parse_proposal_drafts`, `chat_with_context`,
  `generate_text`) + 1 aus `app.domains.proposals.service`
  (`generate_proposal_drafts`).
- **Produktiv-Importer**: genau **1 Stelle** —
  `app/domains/proposals/service.py:62`, lazy im Body von
  `generate_proposal_drafts` (`from services import ai as _seam`). Alle
  anderen Prod-Pfade (`app/interfaces/web/ai.py`,
  `app/interfaces/web/proposals.py`, `app/core/ai.py`) importieren **direkt**
  aus `app.core.ai` — nicht betroffen.
- **Test-Importer**: 3 Dateien, alle mit `from services import ai`.
  monkeypatch-Aufrufe (5×) **alle** auf `chat_with_context` — kein anderes
  Symbol wird je gepatcht. Zusätzliche Attribut-*Reads* (kein Patch) im
  Unit-Test: `ai._parse_proposal_drafts`, `ai.AiDraftError`,
  `ai.PROPOSAL_DRAFTS_SYSTEM`, `ai.generate_proposal_drafts`.

## Entscheidungen

### §A — Patch-Naht: das `app.core.ai`-Modul-Objekt selbst

Der Shim war nie etwas anderes als ein **Modul-Objekt-Alias**: alle
Patches gehen über `monkeypatch.setattr(ai, "chat_with_context", …)`, was
ein Modul-Attribut mutiert. Wenn die Produktion das *gleiche* Modul-Objekt
zur Call-Zeit auflöst (lazy `from app.core import ai as _seam`), greift der
Patch unverändert — die Pfad-Renamen ist mechanisch.

**§A.1 — Lazy bleibt lazy.** `app/domains/proposals/service.py` behält das
lazy-im-Body-Import-Idiom (`from app.core import ai as _seam` direkt im
Body von `generate_proposal_drafts`). Begründung:

1. **Idiom-Erhalt**: gleicher Patch-Mechanismus wie unter dem Shim — keine
   Test-Diff-Welle, weil der Import-Ort an seiner Patch-Semantik nichts
   ändert (Modul-Cache resolves to the same `sys.modules`-Eintrag).
2. **Keine Import-Cycle-Sorge mehr**: der historische Grund (`services.ai`
   re-exportierte `generate_proposal_drafts` zurück) ist mit dem Shim-Tod
   weg. Lazy ist hier kein Cycle-Workaround, nur Stil-Konsistenz mit der
   Vorgängerzeile (siehe Inline-Kommentar — der Cycle-Hinweis wurde
   entsprechend umformuliert).

**§A.2 — Tests patchen jetzt `app.core.ai`.** Der einzige Mechanik-
Unterschied: `from services import ai` → `from app.core import ai`. Damit
referenziert die Test-Variable `ai` direkt das Adapter-Modul, das die
Produktion via `_seam` auflöst — beide zeigen auf dasselbe `sys.modules`-
Objekt. Die monkeypatch-Aufrufe selbst sind **byte-identisch**.

### §B — Sonderfall `generate_proposal_drafts` im Unit-Test

`tests/unit/test_ai_proposal_drafts.py` rief `ai.generate_proposal_drafts(...)`
auf (Shim re-exportierte sie aus `app.domains.proposals.service`). Diese
Funktion lebt **nicht** in `app.core.ai` — sie ist Orchestrierung, nicht
Adapter (Schritt-6-Layering). Lösung: getrennter Import an der Naht:

```python
from app.core import ai
from app.domains.proposals.service import generate_proposal_drafts
```

…und zwei Aufrufstellen `ai.generate_proposal_drafts(...)` →
`generate_proposal_drafts(...)`. Das ist die einzige nicht-rein-mechanische
Änderung der Test-Suite und macht die Layer-Trennung im Test-Importer
explizit (Adapter ≠ Orchestrierung — die Schritt-6-Entscheidung
materialisiert sich im Test-Code).

### §C — Keine neue `import-linter`-Regel

Identisch zu T7-A (ADR-014 §D): ein einzelnes `.py`-Modul (`services/ai.py`)
ist kein valides `grimp`-`root_package`. **Die Datei-Löschung selbst ist
das Gate**: ohne `services/ai.py` schlägt jeder Reach mit
`ModuleNotFoundError` fehl. Der T6-Shim-Inventar-Gate
(`scripts/check_architecture_metrics.py`) hält die Doku nach — Tabelle
ohne Zeile, AST-Walk findet 3 Shims (vorher 4), Drift in beide Richtungen
bricht CI.

### §D — Was bewusst **nicht** Teil dieser PR ist

- **T7-C** (`services/linkedin_import.py`): analoger Lifecycle-Swap, eigener
  ADR, eigener PR. Inventar-Zähler-Ziel: 3 → 2.
- **T7-D** (`services/mcp_server.py` → `app/interfaces/mcp/server.py`):
  Move-not-rewrite + Mount-Pfad-Anpassung; ADR-009 §B benennt den
  `m.engine`-Seam als frozen, der Move ist der Lifecycle-Endpunkt. Eigener
  PR, eigener ADR.
- **`routes/{leads,proposals}.py`-Shim-Tod**: kein eigenes T-Item, fällt mit
  der nächsten Char-Test-Reorganisation.

### §E — `app/core/ai.py`-Docstring-Sync

Die Docstring-Stelle in `app/core/ai.py` (Z. 17–21) listete bisher beide
Shims als „remain as thin re-export shims". Sie wird in dieser PR auf
„nur noch `services/linkedin_import.py` lebt; `services/ai.py` ist seit
T7-B (ADR-015) tot" retargetet — line-neutral, keine LOC-Verschiebung.

## Konsequenzen

- **Strukturell:** Re-Export-Shim-Inventar 4 → 3; T6-Gate-Output meldet
  `5 import-linter contracts and 3 re-export shims accounted for`.
- **Patch-Naht lokalisiert:** statt einer Indirektion durch `services/ai.py`
  patchen Tests jetzt direkt das `app.core.ai`-Modul. Eine
  Test-Importer-Zeile pro Datei (3 Files); eine Produktiv-Import-Zeile in
  `app/domains/proposals/service.py`. Sonst byte-identisch.
- **Layer-Trennung sichtbar:** der Unit-Test importiert Adapter (`ai`) und
  Orchestrierung (`generate_proposal_drafts` aus
  `app.domains.proposals.service`) getrennt — was die Schritt-6-Architektur
  schon implizit voraussetzte, ist jetzt im Import-Block lesbar.
- **132 Char-Tests + 90 %-Invoicing-Suite + Integration: 0-Behavior-Diff**
  (CI-verifiziert; lokal nicht laufbar — Schritt-1-Constraint).
- **Doc-Gate-Sync im selben Change:** ARCHITECTURE.md (LOC-Kennzahlen,
  Verzeichnisbaum, Shim-Inventar, T7-A-Block) + CLAUDE.md (Banner-Sync) +
  remediation-backlog.md (T7-Sektion: T7-A ✅ / T7-B ✅ / T7-C/D pending).
  Doc-Gate grün: `12.269 / 8.665 / 3.604` (Prod −35 / Tests +7 / Total −28).

## Folge-Schritte

T7-C (linkedin_import-Lifecycle-Swap, analog) und T7-D (mcp_server-
Relokation) — beide P2, jeder als eigene PR, jeder mit eigenem ADR,
jeder erkennbar im T6-Inventar-Zähler.
