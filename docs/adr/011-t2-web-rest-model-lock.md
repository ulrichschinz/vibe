# ADR-011: Web/REST-Modellsperre (Remediation-Track T2)

**Status:** Akzeptiert (2026-05-19)

## Kontext

Das adversariale Audit (`docs/audit-report-scaling-roadmap.md`, Befund R1)
hielt fest: die Contract-Kantentabelle-Zeile `interfaces/* ↛
domains/*/models` ist die **zentrale Anti-Pattern-Sperre für die größte
Fläche** (CRUD-Web/REST), wurde aber in Schritt 8 **bewusst nicht
aktiviert** (ADR-009 §G: „churn owned by no step") — 6+ Modellbau-Sites bei
grünem Build. Remediation-Track-Item **T2** (`docs/remediation-backlog.md`):
zweistufig, T2a (Bestand-Refactor) blockt T2b (Gate).

Vor Umsetzung ergab die volle Inventur (Plan-Befund, in der Backlog-Spec
nachgeschärft): „nur Konstruktion umleiten" **reicht nicht**. Der Gate
verbietet jeden *direkten* Import von
`app.domains.{leads,proposals,billing}.models` aus `app.interfaces` —
dieselben Interface-Dateien importieren die Modelle auch für Queries
(`select(Lead)`, `session.get(Invoice, …)`), Enums (`LeadStage`,
`InvoiceStatus`, `LeadType(...)`) und Jinja-Globals
(`env.globals["LeadStage"]`). T2a ist daher die **volle Read-/Enum-/
Template-Flächen-Verschiebung** der sechs Interface-Module hinter ihre
Services.

Randbedingung (S4–S9-Lektion, unverändert): **kein lokaler Interpreter mit
App-Deps** → Korrektheit ist CI-verifiziert; lokal nur stdlib-Doc-Gate +
Probe-Lint. Invariante: 132 Characterization-Tests + 90 %-Invoicing 0-Diff.

## Entscheidungen

### §A — Indirektion über `*.service`, nicht Massen-Query-Rewrite

Jeder Modell-Name in den Interface-Modulen wird über das **Domänen-
`*.service`-Modul** aufgelöst (`from app.domains.<d>.service import …` bzw.
`<d>_service.<Name>`). import-linter mit `allow_indirect_imports = "True"`
verbietet nur die **direkte** Kante `interfaces → domains/*/models` und
lässt die transitive `interfaces → domains/<d>.service → …models` zu —
**dieselbe Subtilität wie die Schritt-7-MCP-Regel (ADR-008)**, invers zur
Schritt-5-Billing-Regel. Query-Bodies (`select(Lead)…`) bleiben **byte-
identisch** im Handler; nur die Import-Zeile wechselt das Quellmodul. Das
hält den 0-Diff-Invariant maximal sicher (keine SQL-/Verhaltensänderung)
ohne lokale Test-Möglichkeit. Re-Export-only-Namen (`STAGE_ORDER`,
`ViesAuditEntry`) tragen `# noqa: F401` (kein `__all__` in
`leads/service.py` — Bestand).

### §B — Konstruktion ist geteilte Service-Logik (der R1-Kern)

Modell-**Konstruktion** wandert verbatim in dedizierte Service-Funktionen
(`create_lead_web`/`create_lead_api`, `create_note_web`,
`create_invoice_web`, `add_invoice_line_web`, `create_draft_api`,
`add_line_api`, `get_or_create_issuer_web`). Das ist der eigentliche
„eine Logik, drei Clients"-Gewinn: Web/REST teilen jetzt die
Konstruktion mit der MCP-Schicht (`mcp_create_lead`/`create_draft`/…).
Form-Parsing, HTTP-Guards (422-vor-Konstruktion, 404/409),
Decimal-/`_to_decimal`-Parsing, Positions-Query und Netto/USt-Mathematik
**bleiben im Handler** (die Naht): der Caller übergibt die finalen,
bereits geparsten Werte; der Body ist byte-identisch zum alten Inline-
`Model(...)` + `session`-Aufrufen. `services/invoicing/` ist **unangetastet**
(move-not-rewrite; das ist Billing-Draft-Konstruktion, nicht der
Finalize-Compliance-Kern).

### §C — `User`/`ApiKey`/`AiSettings` → `core`-Service (Spec, nicht Gate)

`User`/`ApiKey` (`app.core.identity`) und `AiSettings`
(`app.core.ai_settings`) sind **nicht** in `forbidden_modules` — `core` ist
keine Domäne, der Gate erzwingt sie nicht. Die T2a-Spec verlangt sie
trotzdem („Zuhause klären", R1-Symmetrie über die ganze CRUD-Fläche). Neu:
`app/core/{identity,ai_settings}_service.py` (Contract-Kantentabelle:
`core` darf nur `core` + stdlib/3rd-party). **Hashing bleibt im Handler**
(`services.auth` — `core ↛ services` ist eine verbotene Kante): der Caller
übergibt den bereits gehashten Wert. `get_ai_settings_or_default`
(Display-Fallback, `… or AiSettings()`) und `get_or_create_ai_settings`
(`AiSettings(id=1)`) sind **bewusst zwei** Funktionen — Zusammenlegen wäre
eine Verhaltensänderung.

### §D — Gate aktiviert (T2b)

Neuer `[[tool.importlinter.contracts]]` (`forbidden`,
`source_modules=["app.interfaces"]`,
`forbidden_modules=[app.domains.{leads,proposals,billing}.models]`,
`allow_indirect_imports="True"`). Verifikation: `grep` bestätigt **null**
`app.domains.*.models`-Referenzen in `app/interfaces` (alle sechs Module:
web/{leads,invoices,admin,ai,proposals}, api/router). CI ist der Arbiter.

## Konsequenzen

- R1 strukturell geschlossen für die gate-fähige Fläche; die Sperre
  skaliert mit (jeder neue Interface-Modellzugriff bricht den Build).
- `core`-Service-Module sind ein neues, gate-legales Muster (kein Domänen-
  Zwang) — dokumentiert, damit es nicht als Drift gelesen wird.
- 0-Diff-Risiko konzentriert in §B (Konstruktion verbatim verschoben) und
  §A (Import-Quellwechsel) — Query-/Enum-/Template-Bodies unverändert.
- Bewusst **nicht** Teil: `shared ↛ domains` (Enum-keyed Labels, ADR-009
  §G, unverändert deferred) und der physische Shim-Tod (ADR-009-Liste).
- Roadmap bleibt eingefroren Rev. 2 — dies ist Remediation-Track, kein
  Rev. 3 (E2). Move-not-rewrite-Decke/Schuld 6 unberührt (E1).
