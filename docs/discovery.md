# Phase 1 — Discovery

Stand: 2026-05-08. Codebase: vibe (Agentic Reach CRM), Branch `main`.

## 1.1 Projektstruktur

```
vibe/
  main.py                 — FastAPI app factory, lifespan, attach_user middleware, bootstrap_admin
  database.py             — SQLite engine + get_session() + _safe_add_column
  models.py               — alle SQLModel-Tabellen + Pydantic-Schemas + Label-Dicts
  routes/                 — leads, proposals, api, auth, admin, ai, mcp
  services/               — pdf, numbering, auth, ai, proposals, mcp_server
  templates/              — Jinja2-Templates (proposals/document.html, base.html, ...)
  static/                 — App-CSS/JS + brand-Assets unter static/brand/
  generated_pdfs/         — Proposal-PDFs (gitignored, Docker-Volume)
  Dockerfile              — python:3.12-slim + WeasyPrint apt-deps
  docker-compose.yml      — lokal/standalone, Caddy als Reverse-Proxy
  .github/workflows/      — deploy.yml (Build + ghcr.io + SSH-Trigger)
```

- **Sprache:** Python 3.12 (Dockerfile FROM python:3.12-slim)
- **Frameworks:** FastAPI 0.115 + sync SQLModel 0.0.22 + Jinja2 + WeasyPrint 63.1
- **Build:** Plain pip + requirements.txt; keine pyproject.toml, kein Build-Tool
- **Persistenz:** SQLite (`sqlite:///./leads.db`), persistiert per Docker-Volume; kein Migrations-Tool, statt dessen `_safe_add_column()` in `database.py:15` für additive ALTERs beim Boot
- **Testing:** Komplett abwesend — kein `tests/`, keine `pytest.ini`/`pyproject.toml`, keine Test-Dependencies in `requirements.txt`

## 1.2 Bestehende Domäne

Aggregate (alle in `models.py`):

| Tabelle | Zweck | PK |
|---|---|---|
| `Lead` | Vertriebs-Kontakt | `id` autoincrement |
| `Note` | Freitext-Notizen am Lead | `id` |
| `PlanningMessage` | Chat-Verlauf zur AI-Planung pro Lead | `id` |
| `Proposal` | Angebot, mit Service-JSON + PDF-Pfad | `id`, plus `number: str` (`AR-YYYY-NNN`) |
| `User` | Login-User (admin/editor/viewer) | `id` |
| `ApiKey` | API-Key-Verwaltung mit SHA-256-Hash | `id` |
| `AiSettings` | Singleton (id=1), Anthropic-Konfiguration | `id` (=1) |

**Adressen:** existieren **nicht**. `Lead` hat nur `name, company, email, phone, salutation`. Für Rechnungen muss erweitert werden.

**Steuernummer / USt-IdNr.:** existieren **nicht** in der DB. Aussteller-Anschrift "Agentic Reach · Ulrich Schinz · Staltacher Straße 59A, 82393 Iffeldorf" ist hardcoded in `templates/proposals/document.html`.

**Geld-Datentypen:** `Proposal.total_value` ist `Optional[float]`. Service-Preise im JSON sind `None | float`. **Keine Decimal-Verwendung im Bestand.**

**Zeit/Datum:** alle Timestamps sind `datetime` mit `default_factory=datetime.utcnow` → **naive UTC** (kein `tzinfo`). Datum-only-Felder gibt es nicht.

## 1.3 Berührungspunkte

Andocken des Rechnungs-Moduls:
- `models.py` — neue Tabellen + Lead-Spalten
- `database.py` — Migrations-Helper erweitern (Trigger + WAL + Lead-ALTERs)
- `main.py` — Router-Mount `/invoices`, IssuerProfile-Bootstrap, `archive/`-Dir-Anlage
- `routes/admin.py` — Admin-Seite für `IssuerProfile`, VIES-Audit-Übersicht
- `routes/api.py` — REST-Endpoints für Invoice
- `services/mcp_server.py` — MCP-Tools für Invoice
- `templates/base.html` — Nav-Eintrag „Rechnungen"

Existierende Stubs/Belege: **keine**. Kein `Invoice`-Code, kein `Rechnung`-String in Tabellen oder Templates (außer Templatehinweisen wie „Reisekosten in Rechnung gestellt").

Wiederverwendung möglich von:
- `database.py:_safe_add_column` für additive Lead-Spalten
- `services/pdf.py` (BRAND_DIR, `_make_env`-Pattern, Markdown-Rendering)
- `templates/proposals/document.html` als Layout-Vorlage
- `routes/api.py:validate_api_key` für API + MCP Auth
- `services/auth.py:NeedsLoginException` für Route-Schutz

## 1.4 Annahmen & offene Fragen

**Annahmen** (aus Phase 3 mit Auftraggeber bestätigt):
- Stack bleibt FastAPI + sync SQLModel + SQLite + WeasyPrint (kein Postgres-Switch).
- Lead wird um Adressfelder erweitert (kein separates Customer-Aggregat).
- IssuerProfile als Singleton-Tabelle + Admin-UI.
- VIES-Failure: hart blocken, Admin-Override mit Pflichtbegründung.
- Proposal-Nummerierungs-Race bleibt **out-of-scope**, Hinweis in ADR-003.

**Annahmen ohne Rückfrage** (technisch begründet in ADRs):
- Money: `decimal.Decimal` (ADR-005), nicht Integer-Cents.
- ZUGFeRD-XML: `drafthorse` (ADR-002).
- PDF/A-3: WeasyPrint → `pikepdf` (ADR-002, ADR-006).
- Numbering: `BEGIN IMMEDIATE` + Sequence-Tabelle (ADR-003).
- Archive: Filesystem `archive/invoices/{YYYY}/` + chmod 0444 + Hash-Chain (ADR-001).
- Hash-Chain: per-Geschäftsjahr (ADR-001).

**Offene Punkte → `docs/open-questions.md`:**
- ❓ XRechnung-Output für öffentliche Auftraggeber: Datenmodell unterstützt es, Renderer nicht in v1.
- ❓ EU-B2C-OSS-Schwelle: v1 behandelt EU-B2C wie DE-B2C, gibt Warnung.
- ❓ E-Mail-Versand der Rechnung: nicht in v1, `mark_sent` setzt nur Status.
- ❓ Mehrwährung: `currency='EUR'` hardcoded, Schema kennt das Feld.
- ❓ WeasyPrint→PDF/A-3 mit reinem pikepdf: muss in CI durch veraPDF verifiziert werden; Fallback ghostscript ggf. nachrüsten.
