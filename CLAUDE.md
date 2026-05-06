# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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

No test suite exists yet. No linter configured.

## Environment

Copy `.env.example` to `.env`. Required vars:
- `DATABASE_URL` — defaults to `sqlite:///./leads.db`
- `API_KEY` — shared secret for the agent REST API (`X-API-Key` header)
- `APP_HOST` — used in templates (e.g. `vibe.agentic-reach.com`)

The `brand/` directory lives one level up (`../brand`) and is mounted read-only at `/brand` in Docker. It provides logo + CSS used in proposal PDFs.

## Architecture

Single-process FastAPI app. No async DB usage — all routes use synchronous SQLModel sessions via `Depends(get_session)`.

```
main.py          — app factory, mounts static dirs, registers routers, calls create_db() on startup
database.py      — SQLite engine + get_session() dependency
models.py        — all SQLModel table definitions + Pydantic schemas + label/order dicts
routes/
  leads.py       — web UI: dashboard, lead CRUD, stage transitions, notes
  proposals.py   — web UI: proposal CRUD, PDF download, mark-sent
  api.py         — REST API for agent integration (/api/leads), API key auth
services/
  pdf.py         — renders proposals to HTML then PDF via WeasyPrint
  numbering.py   — generates AR-YYYY-NNN proposal numbers
templates/       — Jinja2; base.html is the shared layout
static/          — app CSS/JS
generated_pdfs/  — PDF output, gitignored, persisted via Docker volume
```

## Key patterns

**Form-based mutations:** All state changes (create, update, delete, stage change) use `POST` forms with `RedirectResponse`. There are no JSON-returning UI routes — those live exclusively under `/api`.

**Jinja2 globals:** `routes/leads.py` injects `STAGE_LABELS`, `SOURCE_LABELS`, `STAGE_ORDER`, `LeadStage`, `LeadSource`, `PROPOSAL_STATUS_LABELS` into the template environment so templates can reference them directly without per-route injection.

**JSON fields on Lead:** `tags` and `agent_metadata` are stored as JSON strings in SQLite (not a JSON column). Always `json.dumps()` before write and `json.loads()` before use.

**PDF generation:** `services/pdf.py` renders `templates/proposals/document.html` with Jinja2, then passes the HTML string to WeasyPrint. Brand CSS and fonts are resolved via absolute path from the mounted `brand/` directory.

**API auth:** `routes/api.py` compares `X-API-Key` header against `API_KEY` env var. If `API_KEY` is empty the check is skipped (dev convenience).

## Data model relationships

```
Lead 1──* Note
Lead 1──* Proposal
```

`LeadStage` order is defined in `STAGE_ORDER` list in `models.py` and drives the pipeline UI in templates.

## Docker notes

The local `docker-compose.yml` uses Caddy as reverse proxy (dev/standalone). The server deployment uses a separate Traefik-based compose in `srvmgmt/services/vibe/docker-compose.yml` — do not conflate the two.
