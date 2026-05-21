# ARCHITECTURE — Ist-Zustand

> Stand: 2026-05-16. Dieses Dokument hält fest, **wie der Code aktuell
> aufgebaut ist** — als gemeinsame Wissensbasis für Menschen und Agenten.
> Den Soll-Zustand und den Migrationspfad beschreibt
> [`docs/scaling-roadmap.md`](docs/scaling-roadmap.md).
>
> Alle Zahlen sind verifiziert (`wc -l`, `grep`). Wenn du Code änderst und
> eine Zahl hier nicht mehr stimmt, ist *diese Datei* falsch — bitte
> aktualisieren.

## Kennzahlen

| Metrik | Wert | Beleg |
|---|---|---|
| Python LOC gesamt | 12.248 | `find -name '*.py'` |
| davon Produktivcode | 8.640 | ohne `tests/` |
| davon Tests | 3.608 | `tests/` |
| Test/Prod-Verhältnis | ~42 % | Remediation-Track **T7-D** (`services/mcp_server.py` → `app/interfaces/mcp/server.py` Move-not-rewrite, ADR-017): Prod +4 LOC / Tests +4 LOC / Total +8 LOC — reiner physischer Move des 363-LOC-FastMCP-Servers (16 Tools + modul-globaler `engine`-Seam). 2 Prod-Importer (`app/interfaces/mcp/{__init__,mount}.py`) + 1 Test-Importer (`tests/characterization/conftest.py::mcp_module`) auf neuen Pfad retargeted; `import services.mcp_server as m` → `import app.interfaces.mcp.server as m`; `monkeypatch.setattr(m, "engine", …)` byte-identisch (Modul-Cache → selbes `sys.modules`-Objekt). Import-Linter-Regel umbenannt (`source_modules = ["app.interfaces.mcp.server"]` + `name`-String synchron zur Struktur-Verträge-Tabelle). ADR-009 §B-Endpunkt eingelöst (frozen `m.engine`-Seam ist mitgezogen; im selben PR — der einzige Lifecycle-konforme Zeitpunkt). Shim-Inventar unverändert (mcp_server ist keine Re-Export-Shim — Body enthält Funktions-Definitionen; T6-AST-Walk klassifiziert korrekt als Nicht-Shim → Inventar bleibt bei 2 `routes/*.py`-Test-Shims). Datei-eigenes Docstring auf neuen Mount-Pfad korrigiert (referenzierte vorher `routes/mcp.py`, seit Schritt 8 weg — Stale-Korrektur). LOC-Drift +8 (Prod +4 / Tests +4) durch Naht-Docstring-Erweiterungen in `app/interfaces/mcp/{__init__,server}.py` + `tests/characterization/conftest.py::mcp_module` (analog T7-B's +7-Test-LOC); Doc-Gate-Skript `scripts/check_architecture_metrics.py::m_mcp_tools` zählt jetzt am neuen Pfad. Vorgängerzeile **T7-C** (`services/linkedin_import.py`-Shim physisch tot, ADR-016): Prod −28 LOC (28-Zeilen-Shim gelöscht; `app/domains/leads/service.py` Docstring-/Kommentar-Retarget line-neutral; lazy `from services import linkedin_import as _li` → `from app.core import ai as _li`; `app/interfaces/web/leads.py` 1-Zeilen-Importer-Swap), Tests 0 LOC (`tests/characterization/test_leads_routes.py`: zwei 1-Zeilen-Importer-Swaps `import services.linkedin_import as li` → `from app.core import ai as li`; monkeypatch-Naht byte-identisch — `monkeypatch.setattr(li, "extract_lead_from_pdf", …)` greift jetzt direkt auf das `app.core.ai`-Modul-Objekt). Kein Sonderfall analog T7-B/`generate_proposal_drafts` — alle 4 re-exportierten Symbole (`SYSTEM_PROMPT`, `LinkedInImportError`, `_parse_json_block`, `extract_lead_from_pdf`) leben tatsächlich in `app/core/ai.py`. Vorgängerzeile **T7-B** (`services/ai.py`-Shim physisch tot, ADR-015): Prod −36 LOC, Tests +7 LOC (`tests/unit/test_ai_proposal_drafts.py`: Docstring auf „T7-B / ADR-015"-Diagnose erweitert + zusätzlicher Import `from app.domains.proposals.service import generate_proposal_drafts`; 2 Aufrufstellen `ai.generate_proposal_drafts(...)` → `generate_proposal_drafts(...)`; die zwei anderen Importer — `tests/characterization/test_proposals_routes.py` + `tests/integration/test_proposal_from_plan.py` — sind reine 1-Zeilen-Importer-Swaps. monkeypatch-Naht unverändert (`monkeypatch.setattr(ai, "chat_with_context", …)` greift jetzt direkt auf das `app.core.ai`-Modul-Objekt). Vorgängerzeile **T7-A** bleibt sachlich gültig: `models.py`-Shim physisch tot, Aggregations-Rolle in `db_tables.register_tables()` umgezogen (top-level — `core ↛ domains` zwingt es aus `app.core` raus — ADR-014). Vorgängerzeile **T4b** bleibt sachlich gültig: `tests/e2e/conftest.py` überschreibt das geteilte `engine`-Fixture für die e2e-Suite und baut das Schema via `app.core.db_migrate.run_migrations` statt `create_all` + Helfer (Alembic-Pfad in jedem CI-Lauf real exerciert; schemaneutral per T4a). Vorgängerzeile **T4a** bleibt: `tests/test_db_migration_parity.py` vergleicht `create_all`-Schema vs. `run_migrations`-Schema strukturell (`sqlite_master` + `PRAGMA`) → fängt künftige Drift Modell ↔ Alembic-Revision (Schritt-9-Vertrag) |
| SQLModel-Tabellen | 13 | `table=True`-Klassen in `app/**/models.py` + `app/core/{identity,ai_settings}.py`; Registry-Bootstrap (T7-A): `db_tables.register_tables()` (top-level — `core ↛ domains` zwingt es aus `app.core` raus) importiert sie deterministisch (kernel → leads → proposals → billing). Schritt 4 korrigiert: vorher 14 durch eine mitgezählte Kommentarzeile in `models.py`, real 13 Entitäten |
| HTTP-Endpoints | 72 | `@router.(get\|post\|...)` in `app/interfaces/{web,api}/` (Schritt 8: aus `routes/` dorthin verschoben) |
| Route-Module | 7 | `app/interfaces/{web,api}/*.py` ohne `__init__.py` (register) u. `mount.py` (MCP-ASGI-Mount) |
| MCP-Tools | 16 | `@mcp.tool` in `app/interfaces/mcp/server.py` (seit T7-D dort — ADR-009 §B-Endpunkt eingelöst, ADR-017) |
| HTML-Templates | 20 | `templates/**/*.html` |
| Invoicing-Subsystem | 2.158 LOC | `find services/invoicing -name '*.py' \| xargs wc -l` |
| `os.getenv`-Fundstellen | 0 Dateien | Schritt 3: zentral in `app/core/config.py` (s. „Cross-cutting") |

> ✅ **CI-erzwungen (Schritt 0):** Diese Tabelle ist die einzige Quelle der
> Wahrheit für die Kennzahlen. `scripts/check_architecture_metrics.py`
> *asserted* jede Zeile gegen den Code (Doc-Drift bricht den Build). Ändert
> sich der Code, **muss** diese Tabelle mitgezogen werden — oder CI ist rot.
> `scripts/` zählt selbst nicht mit (Doc-CI-Tooling, kein Produktivcode).

## Architektur in einem Satz

Single-process FastAPI-App, **synchron** (keine async-DB), SQLite via
SQLModel, Jinja2-UI + WeasyPrint-PDF, Claude-Anbindung, plus REST- und
MCP-Schnittstelle für Agenten. Seit Schritt 8 läuft die Delivery-Schicht
über `app/interfaces/{web,api,mcp}` (register-Auto-Discovery + zentraler
RFC-7807-Mapper); Domänen-Logik in `app/domains/*`, Kern in `app/core/*`.
`routes/` ist nur noch test-zugewandter Re-Export-Shim (leads, proposals).
Seit Schritt 9 wird das Schema durch zwei getrennt versionierte Alembic-
Bäume (CRM + Billing, eigene version_table je Baum) etabliert — keine
impliziten `create_all`-Schema-Änderungen mehr.

## Verzeichnisbaum (mit Verantwortung & LOC)

```
vibe/
├── main.py                     132  App-Factory, attach_user-Middleware,
│                                    Lifespan (MCP session_manager), Seeding
├── database.py                 ~185 SQLite-Engine, Pragmas (WAL, FK,
│                                    busy_timeout), BEGIN IMMEDIATE;
│                                    Schritt 9: `create_db()` ruft Alembic
│                                    (`app.core.db_migrate.run_migrations`)
│                                    statt implizitem `create_all`; Trigger-/
│                                    Lead-Spalten-DDL als geteilte Helfer
├── db_tables.py                 25  T7-A (ADR-014): `register_tables()`
│                                    — expliziter Tabellen-Metadaten-
│                                    Bootstrap (Nachfolger der toten
│                                    `models.py`-Aggregations-Rolle).
│                                    Top-level (außerhalb import-linter-
│                                    `root_packages`), weil `core ↛
│                                    domains` aktiv ist.
├── alembic.ini                  ~40 Schritt 9: CLI-Config der zwei Bäume
│                                    (`-n crm` / `-n billing`); In-Prozess
│                                    läuft programmatisch (nicht aus dieser)
├── migrations/                 ~340 Schritt 9: zwei **getrennt versionierte**
│   ├── crm/{env,script.mako}        Alembic-Bäume, je eigene version_table
│   │   versions/0001_crm_baseline   (`alembic_version` /
│   └── billing/{env,script.mako}    `alembic_version_billing`) → späterer
│       versions/0001_billing_base   DB-Split ohne Daten-Migration. Baseline
│                                    = altes create_all-Schema (delegiert,
│                                    byte-gleich). Nicht in import-linter-
│                                    /mypy-/ruff-Scope (nur Doc-Gate-LOC)
├── routes/                      ~30  Schritt 8: nur noch test-zugewandte
│   ├── __init__.py               0   Re-Export-Shims (frozen Char-/
│   ├── leads.py                 ~13  Integration-Tests importieren
│   └── proposals.py             ~13  `from routes import {leads,proposals}`)
├── services/                  2377  Reusable-Kernel + Compliance-Kern
│   │                                (seit T7-D ohne Interface-Schicht;
│   │                                FastMCP-Server zog nach app/interfaces/mcp/)
│   ├── pdf.py                   72  Jinja2→WeasyPrint (saubere Funktion)
│   ├── proposals.py             54  create/mark_sent (sauberer Service)
│   ├── auth.py                  46  Hashing, require_login/_editor/_admin
│   ├── numbering.py             12  Proposal-Nummer
│   └── invoicing/             1819  COMPLIANCE-KERN, stark getestet
│       ├── finalize.py         563  Atomare Finalisierung (Orchestrator);
│       │                            Schritt 5: Lead-Reach → BillingOrder
│       ├── document.py         514  PDF-Render + VAT-Tabellen-Aufbau
│       ├── vies.py             224  EU-USt-IdNr.-Prüfung (zeep/SOAP)
│       ├── vat.py              200  VAT-Sätze, Reverse-Charge-Regeln
│       ├── integrity_check.py  152  Post-Finalize-Audit
│       ├── immutability.py     110  SQLAlchemy-Event-Listener (Sperre)
│       ├── hashchain.py         88  Kryptographische Verkettung
│       ├── archive.py           84  PDF-Ablage (Dateisystem)
│       ├── money.py             71  Decimal-Arithmetik
│       ├── numbering.py         56  Lückenlose Rechnungsnummern
│       ├── eu_countries.py      40  ISO-3166 + VAT-Lookup
│       └── state_machine.py     39  Rechnungs-Lebenszyklus
├── templates/  (20 HTML)            base + dashboard + auth/ + admin/ +
│                                    leads/ + invoices/ + proposals/
├── static/brand/                   Logos, tokens.css, components.* (gebundelt)
├── docs/                           adr/ (8 ADRs), runbook.md,
│                                   verfahrensdokumentation.md, discovery.md,
│                                   open-questions.md
├── tests/  (2489 LOC)              unit/ integration/ e2e/ fixtures/
├── .coveragerc                     90 % Schwelle (Fokus: invoicing)
├── pyproject.toml                  Schritt 1: ruff + mypy + import-linter
├── scripts/new_domain.py           Schritt 1: `make new-domain X` Scaffold
├── app/                            Soll-Skelett (Schritt 2) + LIVE-Code:
│   ├── core/config.py          ...  Schritt 3: pydantic-settings (Env-Quelle)
│   ├── core/identity.py         51  Schritt 4: User/UserRole/ApiKey
│   ├── core/ai_settings.py      32  Schritt 4: AiProvider/AiSettings
│   ├── core/identity_service.py 54  T2: create_user/create_api_key
│   │                                (Hashing bleibt im Handler)
│   ├── core/ai_settings_service 29  T2: get_(or_create|_or_default)_ai_settings
│   │   .py
│   ├── core/ai.py              305  Schritt 6: Anthropic-Adapter + Prompt-
│   │                                Registry + ===MARKER===/<json>-Parser
│   │                                (verbatim aus services/ai+linkedin)
│   ├── domains/leads/models.py 164  Schritt 4: Lead/Note/PlanningMessage +
│   │                                Lead-Enums + STAGE_ORDER
│   ├── domains/leads/schemas.py 87  Schritt 4: LeadCreate/Read/Patch
│   ├── domains/leads/              Schritt 5: BillingOrder-Naht (CRM-
│   │   billing_export.py        54  Export: Lead → BillingCustomer)
│   ├── domains/leads/              Schritt 6: Dashboard/LinkedIn/Planning;
│   │   service.py               571  Schritt 7: + Lead/Note-MCP-Ops; T2:
│   │                                + create_lead_web/_api/create_note_web
│   │                                (verbatim aus mcp_server, dict-Serializer)
│   ├── domains/proposals/          Schritt 4: Proposal + ProposalStatus +
│   │   models.py                97  DEFAULT_SERVICES
│   ├── domains/proposals/          Schritt 6: AI-Draft+Merge/Prefill;
│   │   service.py               185  Schritt 7: + serialize_proposal/list/get
│   │                                (create/mark-sent bleiben in services/)
│   ├── domains/billing/            Schritt 4: eigenes Billing-Tabellen-
│   │   models.py               250  Schema (Invoice/LineItem/Sequence/Vies/
│   │                                Integrity + IssuerProfile), byte-gleich
│   ├── domains/billing/            Schritt 8: Billing-MCP-Facade (draft/
│   │   service.py              330  line/get/list/serialize — verbatim aus
│   │                                mcp_server, billing-eigene Modelle; T2:
│   │                                + create_invoice_web/_draft_api/add_line*
│   ├── core/errors.py           70  Schritt 8: zentraler RFC-7807 problem
│   │                                +json-Mapper (REST-Surface only)
│   ├── core/db_migrate.py       89  Schritt 9: Alembic-Runner (bindet an
│   │                                Live-Engine via attributes-connection —
│   │                                e2e-Monkeypatch-Naht erhalten) + CRM/
│   │                                Billing-Tabellen-Partition (nur Strings,
│   │                                kein Domain-Import → core↛domains grün)
│   ├── interfaces/web/             Schritt 8: Jinja-Router verbatim aus
│   │   {leads,proposals,           routes/ + register()-Auto-Discovery
│   │    invoices,admin,ai,auth}    (Scaffold-Vertrag iteriert domains/*)
│   ├── interfaces/api/             Schritt 8: REST-Router + zentraler
│   │   {router,__init__}.py        RFC-7807-Mapper (statt Inline-Coercion)
│   ├── interfaces/mcp/             Schritt 8: /mcp-Mount + register();
│   │   {mount,__init__}.py         T7-D (ADR-017): FastMCP-Server selbst
│   │   server.py               366  als `app/interfaces/mcp/server.py`
│   │                                heimisch (frozen `m.engine`-Seam
│   │                                mitgezogen — ADR-009 §B-Endpunkt)
│   ├── contracts/                  Schritt 5: BillingOrder-DTO (reines
│   │   billing_order.py        125  pydantic; CRM↔Billing-Vertrag, frozen)
│   └── shared/labels.py         95  Schritt 4: alle *_LABELS (Daten)
└── (Alembic gelandet — Schritt 9; Schema über zwei versionierte Bäume,
     keine impliziten create_all-Schema-Änderungen mehr)
```

## Schichten — und wo die Schichtung bricht

```
   Browser (Jinja)      Agent (REST /api)      Agent (MCP /mcp)
        │                     │                      │
        ▼                     ▼                      ▼
   app/interfaces/web   app/interfaces/api     app/interfaces/mcp/mount
   (register-AutoDisc)  (router + zentraler    → app/interfaces/mcp/server
        │               RFC-7807-Mapper)        (16 Tools, dünn, S7+T7-D)
        │                     │                      │
        ▼                     ▼                      ▼
        app/domains/*/service.py + services/{proposals,pdf,invoicing}
        │   (eine Logik, drei Clients — Schritt 6/7/8)
        ▼
   app/domains/*/models  +  app/core/{identity,ai_settings}
        │  (Tabellen-Aggregation = `db_tables.register_tables()` —
        │   top-level, weil `core ↛ domains` aktiv ist;
        │   `models.py`-Shim ist seit T7-A physisch tot — ADR-014)
        ▼
   SQLite (WAL, BEGIN IMMEDIATE — single-writer)
   Schema: 2 Alembic-Bäume (CRM/Billing, getrennte version_table) — S9
```

**Bruchstellen konkret:**
- ~~`routes/leads.py` — Dashboard-Aggregation, LinkedIn-Import-
  Orchestrierung~~ → **Schritt 6 gelandet**: `app/domains/leads/service.py`
  (Routes rufen den Service). Lead→Proposal-Erzeugung läuft weiter über
  `services/proposals.py` (sauber; MCP teilt sie — Schritt 7).
- ~~`routes/proposals.py` — AI-Draft-Erzeugung + Merge-Logik im Handler~~ →
  **Schritt 6 gelandet**: `app/domains/proposals/service.py`; der Anthropic-
  Adapter + Prompts + `===MARKER===`/`<json>`-Parser liegen in
  `app/core/ai.py` (verbatim verschoben, **kein** Robustheits-Fix —
  Struktur-Schuld 6). Beide AI-Adapter-Shims sind tot: `services/ai.py`
  seit T7-B (ADR-015), `services/linkedin_import.py` seit T7-C (ADR-016) —
  Tests patchen direkt das `app.core.ai`-Modul-Objekt.
- `routes/ai.py` — Planning-Chat-Endpoints; Prompt-Builder + PlanningMessage-
  Historie sind **Schritt 6** nach `app/domains/leads/service.py` (Planning
  gehört zum Lead) gewandert, der Router hält nur HTTP + den AI-Transport.
- ~~`routes/api.py` — RFC-7807-Fehler-Coercion inline pro Endpoint~~ →
  **Schritt 8 gelandet**: zentraler `application/problem+json`-Mapper in
  `app/core/errors.py`, in `app/interfaces/api` registriert; die
  Inline-`try/except`→`HTTPException`-Coercion entfällt. Statuscodes +
  **422-vor-409** (`InvoiceValidationError ⊂ FinalizeError`) erhalten;
  Body-Format ist der einzige sanktionierte, charakterisierte Diff
  (`test_api_errors`→`test_rfc7807_mapper`-Lifecycle-Swap, ADR-009 §C).
- ~~`services/mcp_server.py` — `create_lead`/`update_lead` instanziieren
  `Lead(...)` selbst (Duplikat)~~ → **Schritt 7 gelandet** (Lead/Note/
  Proposal-Tools dünn → `app/domains/{leads,proposals}/service.py`);
  **Schritt 8 gelandet**: die Invoice-Draft/Line/Get/List-Tools delegieren
  jetzt an die `app/domains/billing/service.py`-Facade (kein
  `Invoice(...)`-Konstruktor mehr im MCP-Layer); Finalize/Storno weiter
  über den `BillingOrder`-Vertrag (Resolver im Interface verdrahtet —
  S5-Muster). **T7-D (ADR-017) gelandet**: die Datei zog
  byte-äquivalent von `services/mcp_server.py` nach
  `app/interfaces/mcp/server.py` (frozen `m.engine`-Seam mitgezogen —
  ADR-009 §B-Endpunkt eingelöst).

## Datenmodell

```
User            (standalone; Admins verwalten via /admin)
ApiKey          (SHA-256-Hash; REST + MCP teilen validate_api_key)
AiSettings      (Singleton: Provider/Key/Modell)
IssuerProfile   (Rechnungssteller-Stammdaten)

Lead 1──* Note
Lead 1──* Proposal ──* (ProposalLineItem; in app/domains/proposals/models.py)
Lead 1──* PlanningMessage          (Claude-Chat-Verlauf)
Lead.tags / Lead.agent_metadata    = JSON-String in SQLite (json.dumps/loads)

Invoice 1──* InvoiceLineItem       ── eigene Domäne (compliance) ──
InvoiceNumberSequence              lückenlose Nummerierung
ViesAuditEntry                     USt-IdNr.-Prüf-Audit
IntegrityCheckRun                  Unveränderlichkeits-Nachweis
```
`LeadStage`-Reihenfolge: `STAGE_ORDER` (seit Schritt 4 in
`app/domains/leads/models.py` — direkter Import seit T7-A, kein
Shim-Umweg mehr) treibt die Pipeline-UI.

## Cross-cutting

- **Auth (gut):** `services/auth.py` → `require_login/_editor/_admin` als
  FastAPI-`Depends`. `main.py:attach_user` lädt `request.state.user` pro
  Request, **überspringt** `/static`, `/mcp`, `/api` (vermeidet SQLite-Lock
  je Asset).
- **API-Key (gut, geteilt):** `app/interfaces/api/router.py:validate_api_key()`
  — DB-Lookup SHA-256, Legacy-`API_KEY`-Env-Fallback.
  `app/interfaces/mcp/mount.py` nutzt dieselbe Funktion → Key-Widerruf wirkt
  sofort für REST **und** MCP.
- **PDF:** `services/pdf.py` rendert Jinja2-String → WeasyPrint.
- **AI:** `app/core/ai.py` — Anthropic-SDK, Modell aus `AiSettings` (DB),
  System-Prompts hartcodiert, Antwort-Parsing über `===MARKER===` (fragil).
  Orchestrierung in `app/domains/proposals/service.py` (Draft-Generierung) +
  `app/domains/leads/service.py` (Planning-Chat). Seit T7-B (ADR-015) kein
  `services/ai.py`-Shim mehr — Tests patchen das `app.core.ai`-Modul direkt.
- **MCP:** `app/interfaces/mcp/server.py` (FastMCP, streamable-HTTP; seit
  T7-D physisch dort, ADR-017), in `app/interfaces/mcp/mount.py` mit
  X-API-Key gewrappt, in `main.py`-Lifespan via `session_manager.run()`
  gestartet (Mounts haben keinen eigenen Lifespan).
- **DB:** `database.py` — `journal_mode=WAL`, `foreign_keys=ON`,
  `busy_timeout=30000`, `BEGIN IMMEDIATE` zur Finalize-Serialisierung.
- **Schema/Migrationen (Schritt 9):** zwei getrennt versionierte Alembic-
  Bäume — `migrations/crm` (version_table `alembic_version`) und
  `migrations/billing` (version_table `alembic_version_billing`) — auf der
  heute gemeinsamen SQLite-Datei. `database.create_db()` ruft
  `app.core.db_migrate.run_migrations(engine)` (CRM dann Billing,
  an die Live-Engine gebunden — e2e-Monkeypatch-Naht erhalten) statt
  implizitem `create_all`. Die 0001-Baseline ist *definiert als* das alte
  `create_all`-Schema (delegiert an `SQLModel.metadata.create_all` +
  verbatim Trigger-/Lead-Spalten-DDL → byte-gleich, move-not-rewrite, ohne
  lokalen Interpreter sicher). Getrennte Historien = späterer Billing-DB-
  Split ohne Daten-Migration **und** Heimat der eigenen Billing-
  Aufbewahrungsregel (GoBD↔DSGVO). `tests/conftest.py` nutzt weiter direkt
  `create_all` (= identisch zur Baseline) → 132 Char-Tests + 90 %-
  Invoicing-Suite 0-Diff. `migrations/` ist **kein** import-linter-
  root_package und nicht im mypy/ruff-Scope (nur Doc-Gate-LOC). Rationale:
  `docs/adr/010-alembic-split-versioning.md`.
- **Config (zentral, Schritt 3):** `app/core/config.py` — pydantic-
  settings `Settings`; `get_settings()` ist die einzige Env-Quelle und
  ersetzt die vormals in 6 Modulen verstreuten Ad-hoc-Env-Reads
  (`database.py`, `main.py`, `routes/admin.py`, `routes/api.py`,
  `services/mcp_server.py`, `services/invoicing/archive.py`). Bewusst
  **verhaltensgleich**: Defaults byte-identisch zu den alten Fallbacks,
  `get_settings()` **nicht** gecacht (frische `Settings()` je Aufruf →
  per-call-Env-Semantik + Test-`monkeypatch.setenv` erhalten), alle
  Nachbearbeitung (`or None`, `.lower()=="true"`) bleibt wörtlich an den
  Call-Sites. `main.py` behält `load_dotenv()` (kein `.env`-Shift).
  Start-Validierung (fail-fast) bleibt Soll — kein Feld ist heute
  `required`, da keine Ist-Stelle bei fehlender Var hart bricht.
- **Logging/Tracing:** nicht vorhanden (keine Request-IDs, kein Structured
  Logging).

## Bekannte Struktur-Schulden (neutral)

1. ~~`models.py` (610 Z.) bündelt alle Tabellen + Enums + Labels +
   Schemas~~ → **Schritt 4 gelandet**: nach
   `app/domains/{leads,proposals,billing}/models.py` +
   `app/core/{identity,ai_settings}.py` + `app/shared/labels.py`
   gesplittet. **T7-A (ADR-014) gelandet**: der Re-Export-Shim ist
   physisch gelöscht; die Tabellen-Aggregations-Rolle lebt jetzt als
   expliziter `db_tables.register_tables()`-Aufruf (top-level —
   `core ↛ domains` zwingt es aus `app.core` raus; drei Aufrufer:
   `database.create_db`, `tests/conftest.py`, `tests/e2e/conftest.py`).
   Schritt 6 hatte zusätzlich die *AI-Adapter*-Shims `services/ai.py` und
   `services/linkedin_import.py` erzeugt; beide sind tot — `services/ai.py`
   seit **T7-B (ADR-015)**, `services/linkedin_import.py` seit
   **T7-C (ADR-016)**. Tests patchen jetzt direkt das `app.core.ai`-Modul-
   Objekt (gleicher Patch-Mechanismus, eine Indirektion weniger).
2. Dicke Route-Module: `leads.py` 539→481, `proposals.py` 212→187,
   `ai.py` 282→193 — **Schritt 6** zog Dashboard-Aggregation, LinkedIn-
   Orchestrierung, AI-Draft-Merge und Planning-Historie/Prompt-Builder in
   `app/domains/{leads,proposals}/service.py`. Verbleibend dick:
   `invoices.py` 441 (mischt UI+Orchestrierung) — eigener späterer Schnitt.
3. ~~Service-Layer inkonsistent: fehlt für Lead-Aggregation/Import/
   AI-Merge~~ → **Schritt 6 gelandet**: `app/domains/leads/service.py` +
   `app/domains/proposals/service.py` + `app/core/ai.py` (Adapter). Sauber
   bei `proposals`/`pdf`/`invoicing` bleibt; MCP-Entdopplung = Schritt 7.
4. ~~`mcp_server.py` dupliziert Lead/Proposal-Logik statt Services zu
   rufen~~ → **Schritt 7 gelandet**: die Lead/Note/Proposal-Tools rufen
   `app/domains/{leads,proposals}/service.py` (Konstruktion/Query/
   Serialisierung byte-für-byte dorthin verschoben); eine `import-linter`-
   Regel (`app.interfaces.mcp.server ↛ app.domains.{leads,proposals,billing}.models`,
   `allow_indirect_imports`; Pfad seit T7-D, ADR-017) verhindert die
   Rückkehr des Duplikats. REST +
   MCP + Web teilen damit eine Logik. **Schritt 8 gelandet**: die
   billing-internen Invoice-Draft/Line/Get/List-Tools delegieren an die
   `app/domains/billing/service.py`-Facade (kein `Invoice(...)`-Konstruktor
   im MCP-Layer mehr); die S7-`import-linter`-Regel ist um
   `app.domains.billing.models` erweitert. Router-Split routes/→
   `app/interfaces/{web,api,mcp}` + zentraler RFC-7807-Mapper +
   Prod-`models`-Shim-Tod (test-zugewandter Shim bleibt) sind gelandet.
   Rationale: `docs/adr/008` + `docs/adr/009-interface-split-rfc7807.md`.
5. ~~Kein `pyproject.toml`/Linter/Type-Check/CI-Gate~~ → **Schritt 1
   gelandet** (`pyproject.toml`, `ruff`, `mypy`, `import-linter`,
   `make verify`-Gate je PR). ~~Offen: keine Alembic-Migrationen~~ →
   **Schritt 9 gelandet**: zwei getrennt versionierte Alembic-Bäume
   (CRM/Billing, eigene version_table) ersetzen das implizite `create_all`;
   Baseline = altes Schema (delegiert, byte-gleich); spätere Schema-
   Änderungen sind Revisionen. Rationale `docs/adr/010`.
6. AI-Anbindung an Anthropic gekoppelt, Prompts hartcodiert, Parsing
   fragil. **Schritt 6** hat das *isoliert* (alles in `app/core/ai.py`,
   eine Adapter-Stelle) aber bewusst **nicht behoben** — die Prompts und
   die `===MARKER===`/`<json>`-Parser sind byte-für-byte verschoben (keine
   Verhaltensänderung). Der Robustheits-/Provider-Abstraktions-Fix ist ein
   eigenes späteres Item, jetzt mit klarem Single Point of Change.

**Erhaltenswert:** `docs/adr/` + Runbook + Verfahrensdoku, hohe Invoicing-
Coverage (`.coveragerc` 90 %), geteiltes `validate_api_key()`, schlanke
`attach_user`-Middleware, klar gekapseltes `services/invoicing/`.

## Struktur-Verträge (CI-erzwungen)

Die ausführbaren `import-linter`-Verträge des Repos. Diese Tabelle ist die
*selbst-verifizierende* Gegenseite zur Prosa-Beschreibung in
„Schichten — und wo die Schichtung bricht": der Doc-Gate
(`scripts/check_architecture_metrics.py`, Remediation-Track T6) bricht den
Build, sobald die Menge der `name`-Werte hier von der Menge in
`pyproject.toml` abweicht (Drift in beide Richtungen, Wortlaut-genau). Die
Reihenfolge spiegelt die Aktivierungs-Schritte 5 → 7 → 8 → 8 → T2b. Jede
Zeile hat ihre Rationale-Begründung im verlinkten ADR — die `name`-Strings
verdichten den Vertrags-Inhalt, nicht das *Warum*.

| Name | Typ | Rationale |
|------|-----|-----------|
| `billing core (services.invoicing) must not import CRM/interfaces — Naht via the BillingOrder contract (Schritt 5, +interfaces Schritt 8)` | forbidden | [ADR-007](adr/007-billing-order-contract.md) (S8-Erweiterung: ADR-009) |
| `MCP interface (app.interfaces.mcp.server) must not directly import/construct domain models — MCP-Entdopplung (Schritt 7, +billing Schritt 8, +T7-D relocation)` | forbidden | [ADR-008](adr/008-mcp-dedup-interface-edge.md) (S8-Erweiterung: ADR-009, T7-D-Relokation: [ADR-017](adr/017-t7d-mcp-server-relocation.md)) |
| `reusable kernel (app.core) is domain-agnostic — knows no domain/interface/contract (Schritt 8)` | forbidden | [ADR-009](adr/009-interface-split-rfc7807.md) §G |
| `domains are independent — cross-domain only via app.contracts (Schritt 8)` | independence | [ADR-009](adr/009-interface-split-rfc7807.md) §G; Domänen-Set wird vom Scaffold gepflegt ([ADR-012](adr/012-t5-scaffold-independence-contract.md), T5) |
| `web/REST interfaces must not directly import/construct domain models — Web/REST-Modellsperre (Remediation-Track T2b)` | forbidden | [ADR-011](adr/011-t2-web-rest-model-lock.md) |

Bewusst **nicht** aktiv (mit Begründung in ADR-009 §G):
`shared ↛ domains` (enum-keyed Labels — Enum-Relokation, eigenem Schritt
nicht zugeordnet). Das frühere Bare-`models`-Modul ist seit T7-A
(ADR-014) physisch tot — die Datei-Löschung ist das Gate, kein
`forbidden`-Ziel nötig.

## Re-Export-Shim-Inventar (CI-erzwungen)

Jede Datei mit ausschließlich Imports + optionalem `__all__` ist
strukturell ein „trivialer Re-Export-Shim" — ein bewusst lebender
Naht-Punkt aus dem Move-not-rewrite-Umzug, **kein** Refactoring-Rückstand.
Der Doc-Gate (T6) zählt sie AST-präzise (Body = `Import`/`ImportFrom` ±
`__all__`-Assign, sonst nichts), und die Tabelle ist die einzige Stelle, an
der sie deklariert sind: AST-Fund ≠ Tabelle → CI-Rot. Damit ist auch das
Sterbe-Inventar für Remediation-Track T7 selbst-verifizierend.

| Pfad | LOC | Naht / Aufgabe |
|------|-----|----------------|
| `routes/leads.py` | 14 | Test-Shim. Re-exportiert `app.interfaces.web.leads.router`. Stirbt, sobald die Char-Tests `from routes import leads as leads_route` ablegen. |
| `routes/proposals.py` | 13 | Test-Shim. Re-exportiert `app.interfaces.web.proposals.router`. Stirbt, sobald die Char-Tests `from routes import proposals as proposals_route` ablegen. |

## Invoicing↔CRM-Naht (Vertrags-Schnitt — Schritt 5 gekappt)

Seit Schritt 5 ist die Naht **explizit als Vertrag** geschnitten — der
direkte CRM-Reach existiert nicht mehr:

- **Kein `Lead`-Import in Billing.** `services/invoicing/finalize.py`
  importiert `Lead` nicht mehr; `_snapshot_customer()` nimmt den
  `BillingCustomer`-Snapshot aus `app/contracts/billing_order.py` entgegen.
  Die CRM-Seite (`app/domains/leads/billing_export.build_billing_customer`)
  projiziert `Lead.{salutation,street,street2,postal_code,city,
  country_code,vat_id,is_business,email,name,company}` → `BillingCustomer`;
  er wird wie `renderer`/`archiver`/`vies_gate` über
  `FinalizeOptions.customer_resolver` in den Prod-Aufrufern
  (`app/interfaces/web/invoices.py`, `app/interfaces/api/router.py`,
  `app/interfaces/mcp/server.py`)
  injiziert. Die `name or company`-Präzedenz und der Merge bleiben
  **byte-äquivalent** — nur die Datenquelle änderte sich (die einzige
  inhaltliche Änderung im Plan; sonst move-not-rewrite).
- **Kein `models`-Shim in Billing.** Alle 8 Invoicing-Module importieren
  ihre — seit Schritt 4 billing-eigenen — Modelle direkt aus
  `app.domains.billing.models` statt über den aggregierenden
  `models`-Shim (der `domains/*` re-exportiert).
- **`IssuerProfile`-Read bleibt billing-intern** (seit Schritt 4 ist
  `IssuerProfile` ein Billing-Modell — keine verbotene Kante; bewusst
  nicht über den Vertrag umgeleitet, da das eine zweite, unnötige
  Verhaltensänderung wäre). Der Vertrag *definiert* `issuer{}`/`lines[]`/
  `meta{}` für Vollständigkeit (extraktions-fähig), verdrahtet aber nur
  `customer{}`.
- **Bereits CRM-unabhängig nach Finalize:** Snapshot in `cust_*`/`iss_*`-
  Spalten der `Invoice`; Soft-FK `Invoice.lead_id` **ohne Cascade** →
  Lead-Löschung lässt finalisierte Rechnungen unberührt.

Erzwungen durch die geschärfte `import-linter`-Regel
„`services.invoicing` ↛ `routes`/`app.domains.leads`/
`app.domains.proposals`" (`pyproject.toml`; der `models`-Shim ist über
die transitive `forbidden`-Erkennung mit abgedeckt — Rationale
`docs/adr/007-billing-order-contract.md`; in Schritt 8 um `app.interfaces`
als verbotenes Ziel ergänzt). Geteiltes `get_session`/`engine`
(`database.py`) bleibt bewusst geteilt (Single-Process; DB-Split erst
Stufe B). Schritt 7 aktivierte die **`interfaces/mcp`-Zeile**, **Schritt 8**
erweitert sie um `app.domains.billing.models` (Billing-Facade) und
aktiviert die **`core ↛ domains/interfaces/contracts`**- und die
**`domains/<x> ↛ domains/<y>`**-(`independence`)-Zeile der Kantentabelle.
**Remediation-Track T2 (ADR-011) hat die web/REST-`interfaces ↛
domains/*/models`-Zeile aktiviert** (Audit-Befund R1): die Read-/Enum-/
Konstruktions-Fläche aller 6 Interface-Module wandert hinter die
Domänen-`*.service` (Indirektion = ADR-008-Subtilität,
`allow_indirect_imports="True"`); Konstruktion in dedizierte
Service-Funktionen + neue `app/core/{identity,ai_settings}_service.py`.
Bewusst **weiterhin nicht** aktiviert: `shared ↛ domains` (enum-keyed
Labels, ADR-009 §G — Enum-Relokation, eigenem Schritt nicht zugeordnet).
Rationale `docs/adr/008` + `docs/adr/009-interface-split-rfc7807.md` +
`docs/adr/011-t2-web-rest-model-lock.md`.

## Code-Navigation für Agenten

`context-mode` ist in diesem Repo installiert und aktiv (FTS5/Bun,
AST-bewusstes Chunking) — die **deskriptive „Ist"-Schicht** (Schicht 1)
des Agent-Navigations-Modells. **Primärer Weg, Code zu finden:**
`ctx_search` statt blindes `grep`/Datei-Lesen. Das „Soll" ist *nicht* hier
beschrieben, sondern als ausführbarer Zwang erzwungen (`import-linter` +
Scaffold, Schicht 2); ein eingecheckter Knowledge-/Call-Graph wurde
**verworfen** (statischer Graph in dynamischem Python = selbstbewusst
falsch). Drei-Schichten-Modell (Ist/Soll/Warum), Begründung & Ausbau:
siehe [`docs/scaling-roadmap.md`](docs/scaling-roadmap.md).
