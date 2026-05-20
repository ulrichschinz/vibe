# ADR-016: `services/linkedin_import.py`-Shim sterben lassen (Remediation-Track T7-C)

**Status:** Akzeptiert (2026-05-20)

## Kontext

Dritter T7-Schritt — nach T7-A (`models.py`, ADR-014) und T7-B
(`services/ai.py`, ADR-015) das vorletzte der Shim-Sterbe-Gates aus
Audit-Befund R2. Wie T7-B ist `services/linkedin_import.py` **kein**
Aggregations-Modul, sondern eine reine **monkeypatch-Naht** für die
frozen Schritt-0.5-Char-Tests
(`tests/characterization/test_leads_routes.py`). Die zu beantwortende
Frage war nicht „wer übernimmt die Rolle" (keine), sondern „wie
verschiebt man den Patch-Punkt **ohne** die Test-Assertions zu ändern
und ohne neue Verhaltensänderung" — exakt wie bei T7-B.

### Ist-Aufnahme (Recon, vor dem Schnitt)

- **Shim**: 28 LOC. Re-exportiert genau 4 Symbole **alle** aus
  `app.core.ai` — `SYSTEM_PROMPT` (Konstante), `LinkedInImportError`
  (Exception), `_parse_json_block` (Hilfsfunktion), `extract_lead_from_pdf`
  (Hauptfunktion).
- **Produktiv-Importer**: genau **2 Stellen** —
  `app/domains/leads/service.py:127` (lazy im Body von `linkedin_preview()`,
  `from services import linkedin_import as _li`) und
  `app/interfaces/web/leads.py:222` (modul-lokal im Body von
  `import_linkedin_pdf()`, `from services.linkedin_import import
  LinkedInImportError`). Alle anderen Prod-Pfade greifen direkt auf
  `app.core.ai` zu — nicht betroffen.
- **Test-Importer**: 1 Datei (`tests/characterization/test_leads_routes.py`),
  2 lokale Importer-Statements (`import services.linkedin_import as li`,
  Z. 58 + 105). monkeypatch-Aufrufe (2×) **beide** auf
  `extract_lead_from_pdf` — kein anderes Symbol wird je gepatcht.

### Kein Sonderfall analog T7-B

T7-B (ADR-015 §B) hatte einen Sonderfall: `generate_proposal_drafts`
lebt in `app.domains.proposals.service`, **nicht** in `app.core.ai`, weil
es Orchestrierung ist (Schritt-6-Layering). Die Test-Naht musste dafür
einen getrennten Import bekommen.

Bei T7-C ist das **nicht** so — die Recon hat bestätigt, dass alle 4
re-exportierten Symbole tatsächlich in `app/core/ai.py` definiert sind
(Z. 172 / 176 / 239 / 295). Der Lifecycle-Swap ist damit rein mechanisch:
**1 Importer-Zeile pro Datei**, nichts darüber hinaus.

## Entscheidungen

### §A — Patch-Naht: das `app.core.ai`-Modul-Objekt selbst

Identisch zu T7-B (ADR-015 §A): der Shim war nie etwas anderes als ein
**Modul-Objekt-Alias**. `monkeypatch.setattr(li, "extract_lead_from_pdf",
…)` mutiert ein Modul-Attribut. Wenn die Produktion das *gleiche*
Modul-Objekt zur Call-Zeit auflöst (lazy `from app.core import ai as _li`),
greift der Patch unverändert.

**§A.1 — Lazy bleibt lazy.** `app/domains/leads/service.py` behält das
lazy-im-Body-Import-Idiom in `linkedin_preview()`. Begründung:

1. **Idiom-Erhalt**: gleicher Patch-Mechanismus wie unter dem Shim — keine
   Test-Diff-Welle, weil der Import-Ort an seiner Patch-Semantik nichts
   ändert (Modul-Cache → selber `sys.modules`-Eintrag).
2. **Konsistenz mit T7-B**: `app/domains/proposals/service.py:62` löst den
   AI-Adapter via `from app.core import ai as _seam` lazy auf. Beide
   Domain-Services folgen jetzt demselben Naht-Idiom (Aliase `_seam`/`_li`
   sind kosmetisch).

**§A.2 — Modul-lokaler Importer in `app/interfaces/web/leads.py`.** Der
zweite Prod-Importer ist nicht lazy, sondern liegt am Anfang des
Route-Handler-Bodies. Er importiert nur die Exception-Klasse
(`LinkedInImportError`) — kein Patch-relevanter Pfad. Retarget auf
`from app.core.ai import LinkedInImportError` ist trivial und ändert
nichts an der Patch-Semantik.

**§A.3 — Tests patchen jetzt `app.core.ai`.** Der einzige Mechanik-
Unterschied: `import services.linkedin_import as li` →
`from app.core import ai as li`. Damit referenziert die Test-Variable
`li` direkt das Adapter-Modul, das die Produktion via `_li` auflöst —
beide zeigen auf dasselbe `sys.modules`-Objekt. Die monkeypatch-Aufrufe
selbst (`monkeypatch.setattr(li, "extract_lead_from_pdf", …)` und der
Zugriff `li.LinkedInImportError` im `boom`-Helper) sind
**byte-identisch**.

### §B — Keine neue `import-linter`-Regel

Identisch zu T7-A/T7-B (ADR-014 §D, ADR-015 §C): ein einzelnes `.py`-
Modul (`services/linkedin_import.py`) ist kein valides `grimp`-
`root_package`. **Die Datei-Löschung selbst ist das Gate**: ohne
`services/linkedin_import.py` schlägt jeder Reach mit
`ModuleNotFoundError` fehl. Der T6-Shim-Inventar-Gate
(`scripts/check_architecture_metrics.py`) hält die Doku nach — Tabelle
ohne Zeile, AST-Walk findet 2 Shims (vorher 3), Drift in beide Richtungen
bricht CI.

### §C — Was bewusst **nicht** Teil dieser PR ist

- **T7-D** (`services/mcp_server.py` → `app/interfaces/mcp/server.py`):
  Move-not-rewrite + Mount-Pfad-Anpassung; ADR-009 §B benennt den
  `m.engine`-Seam als frozen, der Move ist der Lifecycle-Endpunkt. Eigener
  PR, eigener ADR. Inventar-Zähler-Ziel: 2 → 2 (mcp_server ist keine
  Shim-Datei im T6-Sinn, aber der einzige verbleibende `services/`-
  Bewohner; nach T7-D ist `services/` reduziert auf
  `{pdf,proposals,auth,numbering,__init__,invoicing/}`).
- **`routes/{leads,proposals}.py`-Shim-Tod**: kein eigenes T-Item, fällt
  mit der nächsten Char-Test-Reorganisation. Inventar-Zähler-Ziel: 0.

### §D — Doku-Sweep

- `ARCHITECTURE.md`: LOC-Kennzahlen (−28 prod / −28 total),
  Verzeichnisbaum-Zeile (`services/linkedin_import.py` raus,
  services-Subtotal 2768 → 2740), Struktur-Schuld-1-Block (T7-C-Sync),
  Schritt-6-Beschreibung (T7-C-Sync), Shim-Inventar (Zeile raus —
  Tabelle hat jetzt 2 Zeilen).
- `CLAUDE.md`: Banner-Sync (T7-C ergänzt; alias-agnostische `_seam`/`_li`-
  Formulierung).
- `docs/remediation-backlog.md`: T7-C ✅ mit Detail-Eintrag (analog
  T7-A/T7-B), Mechanik-Beschreibung.
- ADRs 008/009/010/015 **nicht angefasst** (historischer Record — gleiche
  Disziplin wie bei T7-A/T7-B).

## Konsequenzen

- **Strukturell:** Re-Export-Shim-Inventar 3 → 2; T6-Gate-Output meldet
  `5 import-linter contracts and 2 re-export shims accounted for`.
- **Patch-Naht lokalisiert:** statt einer Indirektion durch
  `services/linkedin_import.py` patchen Tests jetzt direkt das
  `app.core.ai`-Modul. Eine Test-Importer-Zeile pro Stelle (1 File mit
  2 Stellen), zwei Produktiv-Import-Zeilen (`app/domains/leads/service.py`
  + `app/interfaces/web/leads.py`). Sonst byte-identisch.
- **Beide AI-Adapter-Shims tot.** `services/ai.py` (T7-B) +
  `services/linkedin_import.py` (T7-C) sind weg; T6-Inventar enthält
  jetzt nur noch die zwei `routes/{leads,proposals}.py`-Test-Shims. R2
  strukturell zu 2/3 (T7-D folgt — der mcp_server-Move ist kein
  Inventar-Eintrag, aber der letzte `services/*.py`-Knoten außerhalb von
  Compliance-Move-not-rewrite).
- **132 Char-Tests + 90 %-Invoicing-Suite + Integration: 0-Behavior-Diff**
  (CI-verifiziert; lokal nicht laufbar — Schritt-1-Constraint).
- **Doc-Gate-Sync im selben Change:** ARCHITECTURE.md (LOC-Kennzahlen,
  Verzeichnisbaum, Shim-Inventar, Schuld-1-Block, Schritt-6-Block) +
  CLAUDE.md (Banner-Sync) + remediation-backlog.md (T7-C-Sektion).
  Doc-Gate grün: `12.240 / 8.636 / 3.604` (Prod −28 / Tests 0 / Total −28).

## Folge-Schritte

T7-D (mcp_server-Relokation) bleibt offen — P2, eigener PR, eigener ADR.
Die Char-Test-Reorganisation, die die zwei `routes/{leads,proposals}.py`-
Test-Shims tötet, ist kein T-Item, fällt aber bei nächster Gelegenheit
(Inventar-Zähler dann 0).
