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
`scripts/new_domain.py`). Noch **nicht** vorhanden: Alembic-Migrationen
(Schema via `create_all`) — kommt in **Schritt 9**.

## Environment

Copy `.env.example` to `.env`. Required vars:
- `DATABASE_URL` — defaults to `sqlite:///./leads.db`
- `API_KEY` — shared secret for the agent REST API (`X-API-Key` header)
- `SECRET_KEY` — session signing key (random 64-char hex string)
- `APP_HOST` — used in templates (e.g. `vibe.agentic-reach.com`)
- `ADMIN_EMAIL` / `ADMIN_PASSWORD` — seeded on first startup if no users exist yet

Brand assets live inside the repo at `static/brand/` (logos, `tokens.css`, `typography.css`, `brand-kit.css`, `components.css/.js`, `portrait/`). They are served via the standard `/static` mount, so templates reference them as `/static/brand/...`. There is no external `../brand` mount. See the README's **Brand-System** section for details on forking for another brand.

## Architecture

Single-process FastAPI app. No async DB usage — all routes use synchronous SQLModel sessions via `Depends(get_session)`.

```
main.py          — app factory, middleware (attach_user), lifespan, bootstrap_admin()
database.py      — SQLite engine + get_session() dependency
models.py        — Schritt 4: re-export shim + single table-metadata
                   aggregation module (`__all__`, deterministic order). The
                   13 tables/enums/schemas now live in
                   `app/domains/{leads,proposals,billing}/models.py`(+`schemas.py`)
                   and `app/core/{identity,ai_settings}.py`; label dicts in
                   `app/shared/labels.py`. Callers still `from models import …`
                   via the shim (caller migration is Schritte 6–8)
routes/
  leads.py       — web UI: dashboard, lead CRUD, stage transitions, notes
  invoices.py    — web UI: invoice CRUD, finalize, archive, VAT override
  proposals.py   — web UI: proposal CRUD, PDF download, mark-sent
  api.py         — REST API for agent integration (/api/leads), API key auth
  auth.py        — login / logout (session-based)
  admin.py       — user / API-key / issuer / VIES management
  ai.py          — AI planning tab (chat, summary, prompt export)
  mcp.py         — ASGI mount for /mcp; X-API-Key auth middleware around FastMCP app
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

`LeadStage` order is defined in `STAGE_ORDER` list in `app/domains/leads/models.py` (re-exported via the `models.py` shim) and drives the pipeline UI in templates.

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
> `services.invoicing ↛ routes/models/app.domains.{leads,proposals}`
> geschärft (Rationale: `docs/adr/007-billing-order-contract.md`). Noch
> offen ist der **Service-/Interface-Umzug** (Logik aus
> `routes/`+`services/`, Schritte 6–8) — die *übrigen* (Nicht-Billing-)
> Aufrufer importieren die Modelle weiter über den `models.py`-Shim
> ("domain" ≈ der relevante Slice, bis sie Schritt 6–8 in `app/` zieht);
> die volle Interface-Kantenmenge folgt Schritt 7. Jeder Migrationsschritt
> aktiviert/schärft die zu ihm gehörige Contract-Regel; Endzustand =
> ganze Tabelle grün.

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
`app/shared/labels.py`); the *existing* CRM/billing **logic** still lives
in `routes/`+`services/` and reaches the models via the `models.py` shim
(Service-/Interface-Umzug = Schritte 6–8) — scaffold for genuinely new
domains; edit existing logic in its current slice with the same edit
order.
