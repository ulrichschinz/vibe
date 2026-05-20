# ADR-014: `models.py`-Shim sterben lassen (Remediation-Track T7-A)

**Status:** Akzeptiert (2026-05-20)

## Kontext

Das adversariale Audit (`docs/audit-report-scaling-roadmap.md`, Befund R2)
hielt fest: der Plan spezifizierte explizit „Shim-Sterbe-Gates" für die im
Move-not-rewrite-Umzug zurückgelassenen Re-Export-Shims, aktivierte aber
keinen. Remediation-Track-Item **T7** schließt R2 strukturell, einen Shim
pro PR — gute Sichtbarkeit durch den T6-Inventar-Zähler (`N re-export
shims accounted for`).

Erster T7-Schritt: `models.py`. Begründung der Reihenfolge (sauberster
erster Iterations-Schritt):

- **Kein Prod-Namens-Konsument mehr** (`ADR-009 §F`, S8): kein
  `services|routes|app`-Modul importiert die Shim-Namen — alle zeigen
  bereits direkt auf `app.{core,domains,shared}.*`.
- **Kein Char-Test-Lifecycle-Swap nötig** — anders als bei
  `services/{ai,linkedin_import}.py` (T7-B/C, deferred) sind die
  `from models import …`-Importer der Schritt-0.5-Char-Tests reine
  Namens-Bezüge, keine `monkeypatch`-Naht. Ein Import-Repointing ist
  mechanisch und ändert die Test-*Assertion* nicht.
- **Eine** semantisch nicht-triviale Aufgabe blockierte die Tod-Variante
  bisher: die **Tabellen-Metadaten-Registry-Bootstrap-Rolle**
  (`import models` als deterministischer Aggregations-Sammelpunkt für
  `SQLModel.metadata`). Diese Rolle muss ein Nachfolger übernehmen, sonst
  schlägt `create_all` (Tests) bzw. der Alembic-`target_metadata`-Vergleich
  (Prod) wegen fehlender Tabellen fehl.

## Entscheidungen

### §A — Nachfolger der Aggregations-Rolle: top-level `db_tables.py`

Die Registry-Bootstrap-Rolle wandert in ein neues, **funktionales**
top-level-Modul:

```python
# db_tables.py (top-level — siehe §A.2 für die Pfad-Begründung)
def register_tables() -> None:
    """Side-effect import every SQLModel table module so the shared
    SQLModel.metadata sees every table exactly once."""
    import app.core.identity  # noqa: F401
    import app.core.ai_settings  # noqa: F401
    import app.domains.leads.models  # noqa: F401
    import app.domains.proposals.models  # noqa: F401
    import app.domains.billing.models  # noqa: F401
```

**§A.1 — Begründung der Funktions-Form** (statt Modul-Level-Side-
Effect-Imports):

1. **Explizit, lesbar, lokalisiert.** Der Aufrufer (`database.create_db`,
   die zwei Test-Conftests) deklariert sichtbar `register_tables()` —
   kein magisches `import x  # noqa: F401`-Kommentar mehr.
2. **Disqualifiziert das Modul als triviale Re-Export-Shim** unter der
   T6-AST-Fingerprint-Definition (`_is_reexport_shim`): eine `FunctionDef`
   im Body raus → kein Shim → kein Inventar-Eintrag → der T6-Zähler
   sinkt **echt** von 5 → 4 (statt nur den Pfad zu verschieben).
3. **Idempotent durch Python-Module-Cache.** Mehrfach-Aufrufe sind
   harmlos; das war beim Modul-Level-`import models` implizit dasselbe.

**§A.2 — Begründung des top-level-Pfads** (statt `app/core/db_tables.py`):

Das alte `models.py` lebte top-level. Erster Versuch dieser PR plazierte
den Nachfolger nach `app/core/db_tables.py` (logischer Heim-Platz —
„kernel"-Bootstrap). CI fing den Fehler: der seit Schritt 8 aktive
`import-linter`-Vertrag **`core ↛ domains`** (ADR-009 §G) verbietet
genau die `import app.domains.{leads,proposals,billing}.models`-
Aufrufe, die das Modul fachlich braucht. Es bleibt darum top-level —
identisch zum alten `models.py`-Wohnort und identisch zur dokumentierten
Begründung: `main.py`, `database.py` und `db_tables.py` sind die drei
top-level-Module außerhalb der import-linter-`root_packages`, bewusst,
weil sie die Bootstrap-Schicht *unter* der vertraglichen Architektur
sind.

### §B — Drei Bootstrap-Aufrufer (statt drei dupliziter Import-Listen)

Die `import models  # noqa: F401`-Aufrufe wandern auf
`register_tables()`:

| Stelle | Vorher | Nachher |
|---|---|---|
| `database.py:create_db()` | `import models  # noqa: F401` | `register_tables()` |
| `tests/conftest.py` | `import models  # noqa: F401  registers tables on the metadata` | `register_tables()` |
| `tests/e2e/conftest.py` | `import models  # noqa: F401  registers every table on SQLModel.metadata` | `register_tables()` |

Eine Stelle (das `def`), drei Aufrufer — kein Duplikat der 5-Module-Liste.

### §C — Test-Import-Repointing als reines Namens-Repaste

17 Test-Dateien tragen `from models import X (, Y, …)`. Repointing nach
der `__all__`-Karte des sterbenden Shims (= dem Mapping in seiner
Docstring):

| Name(n) | Neue Quelle |
|---|---|
| `ApiKey, User, UserRole` | `app.core.identity` |
| `AiProvider, AiSettings` | `app.core.ai_settings` |
| `Lead, Note, PlanningMessage, LeadSource, LeadStage, LeadType, BantValue, ReadinessLevel, STAGE_ORDER` | `app.domains.leads.models` |
| `LeadCreate, LeadRead, LeadPatch` | `app.domains.leads.schemas` |
| `Proposal, ProposalStatus, DEFAULT_SERVICES` | `app.domains.proposals.models` |
| `IssuerProfile, Invoice, InvoiceLineItem, InvoiceNumberSequence, ViesAuditEntry, IntegrityCheckRun, IntegrityCheckResult, InvoiceStatus, InvoiceKind, ViesResponseStatus, INVOICE_STATUS_ORDER` | `app.domains.billing.models` |
| `*_LABELS` | `app.shared.labels` |

Die Assertions/Bodies der Char-Tests bleiben **byte-identisch** — nur
die `from`-Klausel wechselt. Damit ist das einzige Verhaltens-Risiko
ein vergessener Importer, und CI fängt das in Sekunden ab (132
Char-Tests + 90 %-Invoicing-Suite + Integration + e2e).

### §D — Keine neue `import-linter`-Regel

Ein einzelnes `.py`-Modul (`models.py`) ist kein valides
`grimp`-`root_package` (dokumentierte Schritt-5-Limitation, ADR-007).
Eine `forbidden_modules = ["models"]`-Regel wäre also nicht aktivierbar.
**Die Datei-Löschung selbst ist das Gate**: ohne `models.py` schlägt
jeder Reach mit `ModuleNotFoundError` fehl — kein laufbarer Pfad
übersteht CI. Der T6-Shim-Inventar-Gate hält die *Doku* nach: Tabelle
ohne Zeile, AST-Walk findet keine, Zähler sinkt auf 4. Drift wäre nur
durch Wiedereinführen der Datei möglich, was wiederum T6 fängt
(`extra shim — add or restore`).

### §E — Was bewusst **nicht** Teil dieser PR ist

- **T7-B/C** (`services/{ai,linkedin_import}.py`): Char-Test-Lifecycle-
  Swap der `monkeypatch.setattr("services.ai.…")`-Naht. Eigene PRs,
  eigener ADR.
- **T7-D** (`services/mcp_server.py` → `app/interfaces/mcp/server.py`):
  physische Relokation + Mount-Pfad-Anpassung, eigener PR, eigener ADR.
- **`routes/{leads,proposals}.py`-Shim-Tod**: kein eigener T-Item;
  fällt mit der nächsten Char-Test-Reorganisation, nicht hier.

## Konsequenzen

- **Strukturell:** Re-Export-Shim-Inventar geht von 5 auf 4; der
  T6-Gate-Output meldet `5 import-linter contracts and 4 re-export
  shims accounted for`.
- **Aggregation lokalisiert:** Tabellen-Metadaten-Bootstrap ist jetzt
  ein expliziter Funktions-Aufruf in drei Stellen — keine implizite
  Side-Effect-Import-Magie mehr.
- **Move-not-rewrite respektiert:** Die 5 Quell-Module
  (`app.core.identity`, …, `app.domains.billing.models`) bleiben
  byte-identisch. Geändert wird ausschließlich die Aggregations-Naht
  und das Importer-Set ihrer Test-Konsumenten.
- **132 Char-Tests + 90 %-Invoicing-Suite + e2e: 0-Behavior-Diff**
  (CI-verifiziert; lokal nicht laufbar — kein App-Deps-Interpreter,
  Schritt-1-Constraint).
- **Doc-Gate-Sync im selben Change:** ARCHITECTURE.md (Verzeichnisbaum,
  Shim-Inventar, LOC-Kennzahlen) + CLAUDE.md (`models.py`-Block) ziehen
  mit — sonst CI-Rot (T0-Doc-Gate).

## Folge-Schritte

T7-B (services.ai-Lifecycle-Swap), T7-C (linkedin_import-Lifecycle-Swap),
T7-D (mcp_server-Relokation) — jeder als eigene PR, jeder mit eigenem
ADR, jeder erkennbar im T6-Inventar-Zähler.
