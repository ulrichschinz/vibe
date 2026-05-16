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
No linter / type-checker / GitHub-Actions CI yet — these are introduced in
**Schritt 1** of `docs/scaling-roadmap.md` (`ruff` + `mypy` + `import-linter`
+ `make verify` + `make new-domain`). Until then, only the doc-drift gate
above runs in CI.

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
models.py        — all SQLModel table definitions + Pydantic schemas + label/order dicts
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

`LeadStage` order is defined in `STAGE_ORDER` list in `models.py` and drives the pipeline UI in templates.

## Docker notes

The local `docker-compose.yml` uses Caddy as reverse proxy (dev/standalone). The server deployment uses a separate Traefik-based compose in `srvmgmt/services/vibe/docker-compose.yml` — do not conflate the two.

---

# Agent contract

> **Status banner.** The repo is *technically* layered today
> (`routes/` → `services/` → `models.py`). The domain-oriented `app/`
> structure, `make verify` (`ruff`+`mypy`+`pytest`+`import-linter`) and the
> `make new-domain X` scaffold below are the **Soll**-Zustand introduced in
> **Schritt 1–2** of `docs/scaling-roadmap.md` — they do **not** exist yet.
> This section is anchored now (Schritt 0) so the contract is in the place
> the agent reads first; until the toolchain lands, apply the *protocol* and
> *boundaries* onto the current layout (e.g. "domain" ≈ the relevant
> `routes/`+`services/`+`models.py` slice; "`make verify`" ≈ `pytest` +
> `python3 scripts/check_architecture_metrics.py`). Each migration step
> activates the matching rule below; the end state is the full table green.

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
4. **`make verify` green** (= `ruff` + `mypy` + `pytest` + `import-linter`).
   Today: `pytest` + `python3 scripts/check_architecture_metrics.py` green;
   change a metric → update `ARCHITECTURE.md` in the same change.

"What breaks if I change X?" → `make whocalls SYMBOL=...` (LSP wrapper,
Schritt 1) — not a checked-in call graph (a static graph in framework-heavy
dynamic Python is confidently wrong at the interesting edges).

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
make new-domain X      # Schritt 1+: generates the 5-file domain skeleton
```

It emits `models.py` / `schemas.py` / `service.py` / `repository.py`
(empty-with-docstring until a query is duplicated) / `router.py` plus a
green `tests/test_x.py` smoke test, all **import-linter-conformant by
construction** (zero manual edits → CI green). Registration is
auto-discovery (interfaces iterate `app/domains/*`); the scaffold patches no
central registry by hand. Until Schritt 1 lands, mirror the existing closest
domain's file set manually and keep the same edit order.
