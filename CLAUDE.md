# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with
code in this repository. **Read this first** — it is the agent contract for
this repo. The companion `AGENTS.md` points here (single source).

**Sources of truth (CI-verified, do not paraphrase numbers):**
- `ARCHITECTURE.md` — the *Ist*-Zustand (structure + Kennzahlen). Its metrics
  are asserted against the code by `scripts/check_architecture_metrics.py`;
  drift breaks the build. Don't restate counts here — link there.
- `docs/scaling-roadmap.md` — the *Soll*-Zustand and the (frozen, Rev. 2)
  migration path. Architecture and step order are decided; execute, don't
  re-open.

## Dev commands

```bash
# Setup
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run (dev)
uvicorn main:app --reload --port 8000

# Run with Docker
docker compose up --build
```

```bash
# Run the test suite (it exists — tests/ unit, integration, e2e)
pytest

# Assert ARCHITECTURE.md Kennzahlen against the codebase (doc-drift gate)
python3 scripts/check_architecture_metrics.py
```

Tests live in `tests/` (unit / integration / e2e). `.coveragerc` enforces a
90 % coverage gate focused on the compliance-critical `services/invoicing/`.
**Schritt 1 (Tooling-Fundament) ist gelandet:** `make verify` =
`ruff` (Lint) + `ruff format --check` (nur `app/`) + `mypy` (lax global,
`app.*` strict) + `import-linter` + `make test-fast` + der Schritt-0-
Doc-Gate. Es ist der Akzeptanz-Gate jedes Migrationsschritts und läuft je
PR in `.github/workflows/test.yml` (CI ruft `make PY=python verify`); der
stdlib-Doc-Gate läuft zusätzlich always-on in `doc-metrics.yml`. Neue
Domäne = ein Befehl: `make new-domain X` (Scaffold-Generator
`scripts/new_domain.py`). **Schritt 9 (Alembic) ist gelandet:** das Schema
wird durch **zwei getrennt versionierte Alembic-Bäume** etabliert —
`migrations/crm` (`alembic_version`) + `migrations/billing`
(`alembic_version_billing`) auf der heute gemeinsamen SQLite-Datei;
`database.create_db()` ruft `app.core.db_migrate.run_migrations(engine)`
(an die Live-Engine gebunden) statt implizitem `create_all`. Die
0001-Baseline ist *definiert als* das alte `create_all`-Schema (delegiert →
byte-gleich, move-not-rewrite). Getrennte Historien = späterer Billing-DB-
Split ohne Daten-Migration + Heimat der eigenen Billing-Aufbewahrungsregel
(GoBD↔DSGVO). `tests/conftest.py` nutzt weiter direkt `create_all`
(= identisch zur Baseline) → 132 Char-Tests + 90 %-Suite 0-Diff. Spätere
Schema-Änderungen sind Revisionen, **keine** impliziten `create_all`-
Änderungen mehr. Rationale: `docs/adr/010-alembic-split-versioning.md`.

## Environment

Copy `.env.example` to `.env`. Required vars:
- `DATABASE_URL` — defaults to `sqlite:///./leads.db`
- `API_KEY` — shared secret for the agent REST API (`X-API-Key` header)
- `SECRET_KEY` — session signing key (random 64-char hex string)
- `APP_HOST` — used in templates (e.g. `vibe.agentic-reach.com`)
- `ADMIN_EMAIL` / `ADMIN_PASSWORD` — seeded on first startup if no users exist yet

Brand assets live inside the repo at `static/brand/` (logos, `tokens.css`, `typography.css`, `brand-kit.css`, `components.css/.js`, `portrait/`). They are served via the standard `/static` mount, so templates reference them as `/static/brand/...`. **Note:** the *production* Traefik compose (`/opt/services/vibe/` on the server, separate repo) additionally bind-mounts `/opt/services/brand:/brand:ro` — that path is used by the WeasyPrint PDF generation (`services/pdf.py`, see "PDF generation" below) for absolute-path font/CSS resolution. The local dev `docker-compose.yml` does *not* mount it; the brand assets for the web/Jinja path are bundled in the repo at `static/brand/`. See the README's **Brand-System** section for details on forking for another brand.

## Architecture

Single-process FastAPI app. No async DB usage — all routes use synchronous SQLModel sessions via `Depends(get_session)`.

```
main.py          — app factory, middleware (attach_user), lifespan, bootstrap_admin()
database.py      — SQLite engine + get_session() dependency
db_tables.py     — Tabellen-Metadaten-Bootstrap (Erbe der toten
                   `models.py`-Aggregations-Rolle, T7-A / ADR-014).
                   `register_tables()` macht die deterministischen
                   Side-Effect-Imports der 5 Tabellen-Module (kernel →
                   leads → proposals → billing) explizit. Top-level
                   (außerhalb import-linter-`root_packages`), weil der
                   seit Schritt 8 aktive `core ↛ domains`-Vertrag jede
                   Aggregation im `app.core`-Paket verbieten würde.
                   Drei Aufrufer: `database.create_db`,
                   `tests/conftest.py`, `tests/e2e/conftest.py`.
                   13 tables/enums/schemas live in
                   `app/domains/{leads,proposals,billing}/models.py`
                   (+`schemas.py`) and `app/core/{identity,ai_settings}.py`;
                   labels in `app/shared/labels.py`
routes/          — Schritt 8: thin test-facing re-export shims only
  leads.py       — re-exports `app.interfaces.web.leads.router`
  proposals.py   — re-exports `app.interfaces.web.proposals.router`
app/interfaces/  — Schritt 8 delivery layer (register()-auto-discovery):
  web/{leads,proposals,invoices,admin,ai,auth}.py — Jinja UI (verbatim)
  api/router.py  — REST API for agents (/api/*), X-API-Key auth
  api/__init__.py — register() + central RFC-7807 problem+json mapper
  mcp/mount.py   — ASGI /mcp mount + X-API-Key wrapper
  mcp/__init__.py — register() + FastMCP session-manager ctx
app/core/errors.py — central RFC-7807 problem+json mapper (REST surface)
services/
  pdf.py         — renders proposals to HTML then PDF via WeasyPrint
  numbering.py   — generates AR-YYYY-NNN proposal numbers
  auth.py        — password hashing, NeedsLoginException
  ai.py          — Claude API integration (prompts hardcoded, ===MARKER=== parsing)
  linkedin_import.py — LinkedIn-PDF → Lead extraction
  proposals.py   — shared create/mark-sent helpers (used by routes/proposals.py and MCP)
  mcp_server.py  — FastMCP server + 16 tools (leads/notes/proposals/invoices)
  invoicing/     — compliance core (heavily tested): finalize, VAT, VIES,
                   hashchain, immutability, archive, numbering, integrity
templates/       — Jinja2; base.html is the shared layout
static/          — app CSS/JS + bundled brand assets
generated_pdfs/  — PDF output, gitignored, persisted via Docker volume
```

## Key patterns

**Form-based mutations:** All state changes (create, update, delete, stage change) use `POST` forms with `RedirectResponse`. There are no JSON-returning UI routes — those live exclusively under `/api`.

**Jinja2 globals:** `routes/leads.py` injects `STAGE_LABELS`, `SOURCE_LABELS`, `STAGE_ORDER`, `LeadStage`, `LeadSource`, `PROPOSAL_STATUS_LABELS` into the template environment so templates can reference them directly without per-route injection.

**JSON fields on Lead:** `tags` and `agent_metadata` are stored as JSON strings in SQLite (not a JSON column). Always `json.dumps()` before write and `json.loads()` before use.

**PDF generation:** `services/pdf.py` renders `templates/proposals/document.html` with Jinja2, then passes the HTML string to WeasyPrint. Brand CSS and fonts are resolved via absolute path from the mounted `brand/` directory.

**Session auth:** `routes/auth.py` handles login/logout. `main.py` has an `attach_user` middleware that loads `request.state.user` from the session on every request. Protected routes raise `NeedsLoginException` which redirects to `/login`.

**API auth:** `routes/api.py` validates `X-API-Key` via `validate_api_key()` — DB lookup of SHA-256 hashed keys in the `ApiKey` table (admin-managed at `/admin/api-keys`), with a legacy `API_KEY` env-var fallback. The MCP middleware in `routes/mcp.py` reuses the same function, so revoking a key takes effect for both REST and MCP on the next request.

**MCP server:** `services/mcp_server.py` registers 16 tools (leads / notes / proposals / invoices-finalize) on a FastMCP instance. `routes/mcp.py` wraps its streamable-HTTP ASGI app in an `X-API-Key` middleware and exports `mcp_app`, which `main.py` mounts at `/mcp`. The MCP session manager is started in `main.py`'s lifespan via `async with mcp_server.session_manager.run()` — required because mounted sub-apps don't run their own lifespan. Clients connect to `https://<APP_HOST>/mcp/` (trailing slash matters when accessed without going through Starlette's redirect). The `pdf_url` returned by `get_proposal` points at the existing `/proposals/{id}/pdf` route, which requires a logged-in browser session — it is not fetchable with `X-API-Key` alone.

## Data model relationships

The full, current entity model (14 SQLModel tables incl. the Invoice
compliance domain) lives in **`ARCHITECTURE.md` → Datenmodell** — that is the
single, CI-verified source. Core CRM shape:

```
Lead 1──* Note
Lead 1──* Proposal 1──* ProposalLineItem
Lead 1──* PlanningMessage          (Claude chat history)
Invoice 1──* InvoiceLineItem       (compliance domain; soft-FK Invoice.lead_id, no cascade)
User    (standalone; admins manage other users via /admin)
```

`LeadStage` order is defined in `STAGE_ORDER` list in `app/domains/leads/models.py` (imported directly since T7-A — no shim anymore) and drives the pipeline UI in templates.

## Docker notes

The local `docker-compose.yml` uses Caddy as reverse proxy (dev/standalone). The server deployment uses a separate Traefik-based compose in `srvmgmt/services/vibe/docker-compose.yml` — do not conflate the two.

---

# Agent contract

> **Status banner.** The repo is *technically* layered today
> (`routes/` → `services/` → `models.py`). **Schritt 1 ist gelandet:**
> `make verify` (`ruff` + `mypy` + `import-linter` + `make test-fast` +
> Doc-Gate) und der `make new-domain X`-Scaffold **existieren und sind das
> Gate** — `make verify` ist ab jetzt wörtlich gemeint, kein Surrogat
> mehr. Das `app/`-Soll-Skelett steht (**Schritt 2**), `core/config.py`
> ist live (**Schritt 3**), `models.py` ist gesplittet (**Schritt 4**:
> `app/domains/{leads,proposals,billing}/models.py` (+`leads/schemas.py`)
> + `app/core/{identity,ai_settings}.py` + `app/shared/labels.py`;
> `models.py` ist nur noch Re-Export-Shim + Tabellen-Aggregations-Modul),
> und **Schritt 5 ist gelandet**: der `BillingOrder`-Vertrag
> (`app/contracts/billing_order.py`) + die CRM-Export-Naht
> (`app/domains/leads/billing_export.py`) sind live; `services/invoicing/`
> importiert `Lead`/den `models`-Shim nicht mehr (Modelle direkt aus
> `app.domains.billing.models`), `_snapshot_customer()` nimmt den
> `BillingCustomer`-Snapshot via injiziertem `customer_resolver` entgegen
> (byte-äquivalent — einzige inhaltliche Änderung im Plan). Die
> `import-linter`-Billing-Regel ist auf
> `services.invoicing ↛ routes/app.domains.{leads,proposals}` geschärft
> (der `models`-Shim ist transitiv mit abgedeckt; Rationale:
> `docs/adr/007-billing-order-contract.md`). **Schritt 6 ist gelandet:**
> die Business-Logik ist aus den Routes gezogen — Dashboard-Aggregation,
> LinkedIn-Import-Orchestrierung und die Planning-Chat-Historie/Prompt-
> Builder liegen in `app/domains/leads/service.py`, AI-Draft-Erzeugung +
> Merge in `app/domains/proposals/service.py`, der Anthropic-Adapter +
> Prompt-Registry + `===MARKER===`/`<json>`-Parser **verbatim** in
> `app/core/ai.py` (kein Robustheits-Fix — Struktur-Schuld 6).
> `services/linkedin_import.py` ist Re-Export-Shim = die frozen
> monkeypatch-Naht der Schritt-0.5-Char-Tests (stirbt mit ihnen in T7-C).
> `services/ai.py` war analog gelagert, ist seit **T7-B (ADR-015)** physisch
> tot — die drei Test-Importer (`tests/unit/test_ai_proposal_drafts.py` +
> `tests/{characterization,integration}/`) patchen jetzt direkt das
> `app.core.ai`-Modul-Objekt; `app/domains/proposals/service.py` resolved
> den Adapter via lazy `from app.core import ai as _seam`. `routes/{leads,proposals,ai}.py` rufen
> nur noch den Service; 140 Char-Tests 0-Diff. **Schritt 7 ist
> gelandet:** die MCP-Entdopplung — die Lead/Note/Proposal-Tools in
> `services/mcp_server.py` sind dünn und delegieren an
> `app/domains/{leads,proposals}/service.py` (Konstruktion/Query/
> Serialisierung **byte-für-byte** dorthin verschoben; einzige
> nicht-verbatim Änderung: `with Session(engine)` → caller-owned
> `session`, plus `# type: ignore` auf ORM-Ausdrücke). Das geteilte
> `services/proposals.py` bleibt **unangetastet** (auch von
> `routes/proposals.py` verbatim genutzt). Eine neue
> `import-linter`-`forbidden`-Regel `services.mcp_server ↛
> app.domains.{leads,proposals}.models` mit `allow_indirect_imports`
> aktiviert die **`interfaces/mcp`-Zeile** der Kantentabelle
> (verbietet *direkte* Modell-Importe, lässt den intra-domain
> `service → models`-Pfad zu — invers zur Schritt-5-Billing-Regel;
> Rationale `docs/adr/008-mcp-dedup-interface-edge.md`); die
> Schritt-5-Billing-Regel wurde nur umbenannt. **Schritt 8 ist
> gelandet:** der Interface-Split — die Web-/REST-Router liegen verbatim
> (move-not-rewrite) in `app/interfaces/{web,api}` (Bodies unverändert,
> nur Modell-Importe → `app.*`), `app/interfaces/*` haben `register()`
> mit Domains-Auto-Discovery (Scaffold-Vertrag), `main.py` ist verschlankt;
> `routes/{leads,proposals}.py` sind nur noch test-zugewandte
> Re-Export-Shims (übrige `routes/*` gelöscht). Zentraler RFC-7807
> `application/problem+json`-Mapper (`app/core/errors.py`, in
> `app/interfaces/api` registriert) statt Inline-Coercion — Statuscodes +
> **422-vor-409** erhalten, Body-Format ist der einzige sanktionierte,
> charakterisierte Diff (`test_api_errors`→`tests/unit/
> test_rfc7807_mapper.py`-Lifecycle-Swap im selben PR; übrige 132
> Char-Tests 0-Diff). Billing-MCP-Facade (`app/domains/billing/
> service.py`) — die Invoice-Draft/Line/Get/List-Tools konstruieren kein
> `Invoice(...)` mehr; S7-Regel um `app.domains.billing.models`
> erweitert; neu aktiv: `core ↛ domains/interfaces/contracts` +
> `domains/<x> ↛ domains/<y>` (independence). Prod-`models`-Shim-Tod
> (kein `services|routes|app`-Modul importiert die Shim-Namen mehr;
> `models.py` blieb test-Shim + Aggregator; **physischer Datei-Tod +
> Test-Migration = Remediation-Track T7-A gelandet** — Aggregations-
> Rolle in `app.core.db_tables.register_tables()`, ADR-014). In Schritt 8 bewusst **nicht** aktiviert
> (Zustand galt noch nicht): web/REST-`interfaces ↛ domains/*/models`
> (CRUD-Handler konstruierten weiter Modelle) + `shared ↛ domains`
> (enum-keyed Labels). **Update: die `interfaces ↛ domains/*/models`-Zeile
> ist seit Remediation-Track T2 aktiv** (ADR-011 — Read-/Konstruktions-
> Fläche hinter die Domänen-`*.service`; `shared ↛ domains` bleibt
> deferred).
> `services/mcp_server.py` + `services/linkedin_import.py`-Shim bleiben
> (frozen Seams, ADR-008/009 §B/§E; `services/ai.py` ist seit T7-B/ADR-015
> tot). Rationale
> `docs/adr/009-interface-split-rfc7807.md`. **Schritt 9 ist gelandet:**
> Alembic — zwei **getrennt versionierte** Bäume (`migrations/crm` →
> `alembic_version`, `migrations/billing` → `alembic_version_billing`) auf
> der heute gemeinsamen SQLite-Datei; `database.create_db()` ruft
> `app.core.db_migrate.run_migrations(engine)` (an die Live-Engine
> gebunden — e2e-Monkeypatch-Naht erhalten) statt implizitem `create_all`.
> 0001-Baseline = *altes Schema per Delegation* (`create_all` +
> verbatim Trigger-/Lead-Spalten-DDL aus `database.py`, byte-gleich,
> move-not-rewrite, ohne lokalen Interpreter sicher; `database.py` nur
> refaktoriert — geteilte SQL-Helfer). Getrennte Historien = späterer
> Billing-DB-Split ohne Daten-Migration + Heimat der eigenen Billing-
> Aufbewahrungsregel (GoBD↔DSGVO). `migrations/` ist **kein** import-
> linter-root_package und nicht im mypy/ruff-Scope (nur Doc-Gate-LOC) →
> **keine** `pyproject.toml`-Regeländerung. `tests/conftest.py` nutzt
> weiter direkt `create_all` (= identisch zur Baseline) → 132 Char-Tests +
> 90 %-Invoicing-Suite 0-Diff; nur Prod-Start/e2e-Lifespan laufen jetzt
> durch Alembic (Netto-Schema identisch). Rationale
> `docs/adr/010-alembic-split-versioning.md`. Jeder Migrationsschritt
> aktiviert/schärft die zu ihm gehörige Contract-Regel.

## Agent-Edit-Protokoll

The edit loop is explicit and scaffold-backed — follow it for every change so
work stays consistent at 5–10× the current size:

1. **Locate** the relevant domain via `ctx_search` (context-mode is installed;
   prefer it over blind `grep`/file-reading).
2. **Tie-break** (this is the actual random-file guard):
   - Exactly one existing domain fits → edit there.
   - **None** fits → it is a *new* domain → `make new-domain X` (Schritt 1+).
   - Several / cross-domain → logic stays in *its own* domain; data flows
     **only via `contracts/`**, never domain→domain directly.
3. **Edit order within a domain:** `models → schemas → service → router → test`.
4. **`make verify` green** (= `ruff check` + `ruff format --check` + `mypy`
   — all three scoped to the new Soll surface `scripts/`+`app/`; legacy
   tightens per migration step, `make lint-all` is the non-gating
   repo-wide run — + `import-linter` + `make test-fast` + the Schritt-0
   doc-gate). CI runs
   `make PY=python verify` per PR; no local interpreter-with-deps here, so
   correctness is CI-verified — the stdlib doc-gate
   (`python3 scripts/check_architecture_metrics.py`) is the only local
   lever. Change a metric → update `ARCHITECTURE.md` in the same change.

"What breaks if I change X?" — **`make whocalls` is not wired yet.** The
roadmap's LSP-Pfad ties it to `pyright`; Schritt 1 deliberately landed
`mypy` (per issue #2 / the explicit Schritt-1 scope), so the LSP wrapper
is a tracked open point, not a shipped command (documenting a missing
command would be exactly the drift Schritt 0 forbids). Until it lands, use
`ctx_search` + `import-linter` (the forbidden edges *are* the
"what may reach this" answer). Still **not** a checked-in call graph (a
static graph in framework-heavy dynamic Python is confidently wrong at the
interesting edges).

Invoicing rule (compliance, §14 UStG / ZUGFeRD, ~90 % coverage): its code is
**moved, never rewritten**; the existing tests are the safety net and stay
green every step. The only behavioural change anywhere in the plan is
replacing `_snapshot_customer()`'s direct `Lead` read with the
`BillingOrder` contract (Schritt 5).

## Contract-Kantentabelle (allowed imports)

The "graph" that pays off is a *constraint*, not a report:
`import-linter` contracts encode the allowed edges and break the build on
violation. Target end state (rules sharpen step-by-step; a rule is inactive
until its package exists). `→` = "may import":

| Source | may import → | forbidden |
|---|---|---|
| `interfaces/*` | `domains/*/router`, `domains/*/service`, `domains/*/schemas`, `core/*`, `shared/*` | `domains/*/models`, `domains/*/repository` |
| `interfaces/mcp` | as above | **constructing domain models** (no `Lead(...)` etc. — kills MCP logic duplication) |
| `domains/<x>/*` | `core/*`, `shared/*`, own `domains/<x>/*` | **other** `domains/<y>/*` (cross-domain only via `contracts/`) |
| `domains/billing/*` | `core/*`, `shared/*`, `contracts/billing_order`, own `billing/*` | **any** `domains/*` **and** `models` (hardest rule) |
| `core/*` | `core/*`, stdlib / 3rd-party | `domains/*`, `interfaces/*`, `contracts/*` |
| `shared/*` | `core/*`, stdlib / 3rd-party | `domains/*`, `interfaces/*` |
| `contracts/*` | stdlib / pydantic | `domains/*`, `core/*`, `interfaces/*` (pure DTO) |

Rationale for each rule lives in `docs/adr/*` (the *why* layer — decisions,
not state, so it doesn't drift like a status description).

## Scaffold-Nutzung

A new domain is a **one-command** step — never hand-assembled (that is how
"random code in random files" starts):

```bash
make new-domain X [KIND=web|api]   # scripts/new_domain.py — exists (Schritt 1)
```

It emits `app/domains/X/` `models.py` / `schemas.py` / `service.py` /
`repository.py` (empty-with-docstring until a query is duplicated) /
`router.py` plus a green `tests/test_X.py` smoke test, all **import-linter-
and ruff-format-conformant by construction** (zero manual edits → CI green;
enforced by the `test.yml` scaffold-smoke step). It also seeds
`app/core/db.py` (shared SQLModel base + session) if absent — a minimal
seed that Schritt 2/3 supersede. Registration is auto-discovery (interfaces
iterate `app/domains/*`, Schritt 8); the scaffold patches no central
registry. Note: as of **Schritt 4** the *models* live in
`app/domains/*/models.py` (+`app/core/{identity,ai_settings}.py`,
`app/shared/labels.py`); since T7-A (ADR-014) every consumer imports
them **directly** (no `models.py`-shim anymore — the file is gone).
Service-/Interface-Umzug = Schritte 6–8. Scaffold for genuinely new
domains; edit existing logic in its current slice with the same edit
order.
