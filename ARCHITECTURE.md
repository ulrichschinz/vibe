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
| Python LOC gesamt | 8.749 | `find -name '*.py'` |
| davon Produktivcode | 6.248 | ohne `tests/` |
| davon Tests | 2.501 | `tests/` |
| Test/Prod-Verhältnis | ~40 % | |
| SQLModel-Tabellen | 14 | `grep -c 'table=True' models.py` |
| HTTP-Endpoints | 72 | `@router.(get\|post\|...)` in `routes/` |
| Route-Module | 7 | `routes/*.py` ohne `__init__.py` u. `mcp.py`-Mount |
| MCP-Tools | 16 | `@mcp.tool` in `services/mcp_server.py` |
| HTML-Templates | 20 | `templates/**/*.html` |
| Invoicing-Subsystem | 2.135 LOC | `find services/invoicing -name '*.py' \| xargs wc -l` |
| `os.getenv`-Fundstellen | 6 Dateien | s. „Cross-cutting" |

> ✅ **CI-erzwungen (Schritt 0):** Diese Tabelle ist die einzige Quelle der
> Wahrheit für die Kennzahlen. `scripts/check_architecture_metrics.py`
> *asserted* jede Zeile gegen den Code (Doc-Drift bricht den Build). Ändert
> sich der Code, **muss** diese Tabelle mitgezogen werden — oder CI ist rot.
> `scripts/` zählt selbst nicht mit (Doc-CI-Tooling, kein Produktivcode).

## Architektur in einem Satz

Single-process FastAPI-App, **synchron** (keine async-DB), SQLite via
SQLModel, Jinja2-UI + WeasyPrint-PDF, Claude-Anbindung, plus REST- und
MCP-Schnittstelle für Agenten. Technisch (nicht domänen-) geschichtet:
`routes/` → `services/` → `models.py` → SQLite.

## Verzeichnisbaum (mit Verantwortung & LOC)

```
vibe/
├── main.py                     132  App-Factory, attach_user-Middleware,
│                                    Lifespan (MCP session_manager), Seeding
├── database.py                 170  SQLite-Engine, Pragmas (WAL, FK,
│                                    busy_timeout), BEGIN IMMEDIATE
├── models.py                   610  ALLE 14 Tabellen + ~15 Enums +
│                                    Label-Dicts + Pydantic-Schemas
├── routes/                    1933  Web-UI + REST + MCP-Mount
│   ├── leads.py                539  Lead-CRUD, Notes, LinkedIn-Import-UI,
│   │                                Lead→Proposal — mischt UI+Logik
│   ├── invoices.py             441  Invoice-CRUD, finalize, Archiv, VAT-
│   │                                Override — mischt UI+Orchestrierung
│   ├── api.py                  362  12 JSON-Endpoints für Agenten,
│   │                                X-API-Key, validate_api_key()
│   ├── ai.py                   282  Planning-Chat, Outline→Proposal
│   ├── admin.py                279  User/API-Key/Issuer/VIES-Verwaltung
│   ├── proposals.py            212  Proposal-CRUD + Editor + Dokument
│   ├── mcp.py                   45  ASGI-Mount /mcp + X-API-Key-Middleware
│   └── auth.py                  45  Login/Logout (Session)
├── services/                  3116  Business-Logik (inkonsistent genutzt)
│   ├── mcp_server.py           531  FastMCP + 16 Tools — dupliziert tw.
│   │                                Lead/Proposal-Logik statt Service-Call
│   ├── ai.py                   145  Anthropic-Wrapper, Prompts hartcodiert
│   ├── linkedin_import.py      136  LinkedIn-PDF → Lead-Extraktion
│   ├── pdf.py                   72  Jinja2→WeasyPrint (saubere Funktion)
│   ├── proposals.py             54  create/mark_sent (sauberer Service)
│   ├── auth.py                  46  Hashing, require_login/_editor/_admin
│   ├── numbering.py             12  Proposal-Nummer
│   └── invoicing/             1819  COMPLIANCE-KERN, stark getestet
│       ├── finalize.py         542  Atomare Finalisierung (Orchestrator)
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
├── docs/                           adr/ (6 ADRs), runbook.md,
│                                   verfahrensdokumentation.md, discovery.md,
│                                   open-questions.md
├── tests/  (2489 LOC)              unit/ integration/ e2e/ fixtures/
├── .coveragerc                     90 % Schwelle (Fokus: invoicing)
└── (kein pyproject.toml / Linter / mypy / Alembic)
```

## Schichten — und wo die Schichtung bricht

```
   Browser (Jinja)      Agent (REST /api)      Agent (MCP /mcp)
        │                     │                      │
        ▼                     ▼                      ▼
   routes/leads,        routes/api.py          services/mcp_server.py
   invoices, ...        (X-API-Key)            (X-API-Key, 16 Tools)
        │                     │                      │
        │   ╲ Logik bricht    │  ╲ Fehler-Mapping    │  ╲ DUPLIZIERT
        │    ╲ in Route       │   ╲ inline           │   ╲ Lead/Proposal
        ▼     ▼               ▼                       ▼    ╲ statt Service
        services/  ◄────────── (nur teilweise genutzt) ────╯
        │      proposals.py / pdf.py / invoicing/  = sauber
        ▼
   models.py  (alle Domänen in EINER Datei)
        │
        ▼
   SQLite (WAL, BEGIN IMMEDIATE — single-writer)
```

**Bruchstellen konkret:**
- `routes/leads.py` — Dashboard-Aggregation, LinkedIn-Import-Orchestrierung,
  Lead→Proposal-Erzeugung direkt im Handler.
- `routes/proposals.py` — AI-Draft-Erzeugung + Merge-Logik im Handler.
- `routes/api.py` — RFC-7807-Fehler-Coercion inline pro Endpoint.
- `services/mcp_server.py` — `create_lead`/`update_lead` instanziieren
  `Lead(...)` selbst (Duplikat); nur `create_proposal`/`mark_proposal_sent`
  rufen den Service. Jedes Tool öffnet eigene `Session(engine)`.

## Datenmodell

```
User            (standalone; Admins verwalten via /admin)
ApiKey          (SHA-256-Hash; REST + MCP teilen validate_api_key)
AiSettings      (Singleton: Provider/Key/Modell)
IssuerProfile   (Rechnungssteller-Stammdaten)

Lead 1──* Note
Lead 1──* Proposal ──* (ProposalLineItem; in models.py)
Lead 1──* PlanningMessage          (Claude-Chat-Verlauf)
Lead.tags / Lead.agent_metadata    = JSON-String in SQLite (json.dumps/loads)

Invoice 1──* InvoiceLineItem       ── eigene Domäne (compliance) ──
InvoiceNumberSequence              lückenlose Nummerierung
ViesAuditEntry                     USt-IdNr.-Prüf-Audit
IntegrityCheckRun                  Unveränderlichkeits-Nachweis
```
`LeadStage`-Reihenfolge: `STAGE_ORDER` in `models.py` treibt die Pipeline-UI.

## Cross-cutting

- **Auth (gut):** `services/auth.py` → `require_login/_editor/_admin` als
  FastAPI-`Depends`. `main.py:attach_user` lädt `request.state.user` pro
  Request, **überspringt** `/static`, `/mcp`, `/api` (vermeidet SQLite-Lock
  je Asset).
- **API-Key (gut, geteilt):** `routes/api.py:validate_api_key()` — DB-Lookup
  SHA-256, Legacy-`API_KEY`-Env-Fallback. `routes/mcp.py` nutzt dieselbe
  Funktion → Key-Widerruf wirkt sofort für REST **und** MCP.
- **PDF:** `services/pdf.py` rendert Jinja2-String → WeasyPrint.
- **AI:** `services/ai.py` — Anthropic-SDK, Modell aus `AiSettings` (DB),
  System-Prompts hartcodiert, Antwort-Parsing über `===MARKER===` (fragil).
- **MCP:** `services/mcp_server.py` (FastMCP, streamable-HTTP), in
  `routes/mcp.py` mit X-API-Key gewrappt, in `main.py`-Lifespan via
  `session_manager.run()` gestartet (Mounts haben keinen eigenen Lifespan).
- **DB:** `database.py` — `journal_mode=WAL`, `foreign_keys=ON`,
  `busy_timeout=30000`, `BEGIN IMMEDIATE` zur Finalize-Serialisierung.
- **Config (verstreut):** `os.getenv` in `database.py`, `main.py`,
  `routes/admin.py`, `routes/api.py`, `services/mcp_server.py`,
  `services/invoicing/archive.py` — **kein** zentrales Settings-Modul,
  keine Start-Validierung.
- **Logging/Tracing:** nicht vorhanden (keine Request-IDs, kein Structured
  Logging).

## Bekannte Struktur-Schulden (neutral)

1. `models.py` (610 Z.) bündelt alle 14 Tabellen + Enums + Labels +
   Schemas — jeder Import zieht alle Domänen.
2. Dicke Route-Module (`leads.py` 539, `invoices.py` 441) mischen UI,
   Business-Logik und Orchestrierung → schwer testbar ohne HTTP.
3. Service-Layer inkonsistent: sauber bei `proposals`/`pdf`/`invoicing`,
   fehlt für Lead-Aggregation/Import/AI-Merge.
4. `mcp_server.py` dupliziert Lead/Proposal-Logik statt Services zu rufen.
5. Kein `pyproject.toml`/Linter/Type-Check/CI-Gate; keine Alembic-
   Migrationen (Schema via `create_all` beim Start).
6. AI-Anbindung an Anthropic gekoppelt, Prompts hartcodiert, Parsing fragil.

**Erhaltenswert:** `docs/adr/` + Runbook + Verfahrensdoku, hohe Invoicing-
Coverage (`.coveragerc` 90 %), geteiltes `validate_api_key()`, schlanke
`attach_user`-Middleware, klar gekapseltes `services/invoicing/`.

## Invoicing↔CRM-Naht (der künftige Vertrags-Schnitt)

Trotz Sammeldatei `models.py` ist Invoicing schon **lose gekoppelt** —
relevant für die geplante Billing-Bounded-Context-Trennung
(siehe [`docs/scaling-roadmap.md`](docs/scaling-roadmap.md)):

- **Einziger echter Inward-Reach:**
  `services/invoicing/finalize.py::_snapshot_customer()` liest
  `Lead.{salutation,street,street2,postal_code,city,country_code,
  vat_id,is_business,email,name,company}`.
- Zusätzlich: `IssuerProfile`-Singleton-Read in `finalize.py`,
  geteiltes `get_session`/`engine` (`database.py`), `require_editor`.
- **Bereits CRM-unabhängig nach Finalize:** Snapshot in `cust_*`/`iss_*`-
  Spalten der `Invoice`; Soft-FK `Invoice.lead_id` **ohne Cascade** →
  Lead-Löschung lässt finalisierte Rechnungen unberührt.
- VAT-/Dokument-/Numbering-/Hashchain-Logik ist rein bzw. self-contained
  (kein `models`-/CRM-Import außer den o.g. Punkten).

Konsequenz: Diese Naht ist der genaue Schnittpunkt für den künftigen
`BillingOrder`-Vertrag — der `_snapshot_customer`-Reach wird durch ein
explizites Export-DTO ersetzt; danach importiert Billing nichts CRM-seitig.

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
