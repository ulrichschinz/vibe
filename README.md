# Agentic Reach — Lead Management

Internes CRM-Werkzeug für Agentic Reach. Verwaltet Leads, generiert gebrandete Angebote als PDF und stellt das System gleichzeitig als **REST-API** und **MCP-Server** zur Verfügung — beides mit denselben, im Admin-Bereich verwalteten API-Keys. KI-Agenten können so Leads, Notizen und Angebote nicht nur einliefern, sondern auch lesen, aktualisieren und versenden.

---

## Stack

| Schicht | Technologie |
|---|---|
| Backend | Python 3.12+ · FastAPI · Uvicorn |
| Datenbank | SQLite via SQLModel (migrierbar zu Postgres) |
| Templates | Jinja2 + Brand-System (`static/brand/`) |
| PDF | WeasyPrint |
| Agent-Schnittstellen | REST-API (`/api`) + MCP-Server (`/mcp`, Streamable HTTP) |
| KI-Provider | Anthropic Claude (Planungs-Tab) |
| Paketmanager | uv |

---

## Lokaler Start

```bash
# 1. Abhängigkeiten installieren (einmalig)
uv venv
uv pip install -r requirements.txt
# Für Tests / Entwicklung zusätzlich:
uv pip install -r requirements-dev.txt

# 2. Umgebungsvariablen einrichten
cp .env.example .env
# .env bearbeiten: alle Variablen setzen (siehe unten)

# 3. Server starten
source .venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Die App ist dann unter `http://localhost:8000` erreichbar. Beim ersten Start wird automatisch ein Admin-Account aus `ADMIN_EMAIL`/`ADMIN_PASSWORD` angelegt.

---

## Umgebungsvariablen

| Variable | Bedeutung | Beispiel |
|---|---|---|
| `DATABASE_URL` | SQLite-Pfad oder Postgres-URL | `sqlite:///./leads.db` |
| `API_KEY` | Bearer-Token für die Agent-API | zufälliger 32-Byte-String |
| `SECRET_KEY` | Session-Signaturschlüssel | zufälliger 64-Zeichen-Hex-String |
| `APP_HOST` | Hostname (für Deployment) | `vibe.agentic-reach.com` |
| `ADMIN_EMAIL` | E-Mail des initialen Admins | `admin@example.com` |
| `ADMIN_PASSWORD` | Passwort des initialen Admins | sicheres Passwort |

---

## Verzeichnisstruktur

```
vibe/
├── main.py                  # FastAPI-App, Middleware, Lifespan, Bootstrap
├── models.py                # SQLModel-Datenmodelle (Lead, Proposal, Note, User)
├── database.py              # Engine, Session, create_db()
├── routes/
│   ├── leads.py             # Web-UI: Dashboard, Lead-Liste, Detail, Formular, Notes
│   ├── proposals.py         # Proposal-Editor, PDF-Download, Status
│   ├── api.py               # Agent-REST-API (/api/leads) + validate_api_key()
│   ├── auth.py              # Login / Logout
│   ├── admin.py             # Benutzerverwaltung, API-Keys, KI-Einstellungen
│   ├── ai.py                # KI-Planungs-Tab (Chat, Zusammenfassung, Prompt-Export)
│   └── mcp.py               # ASGI-Mount /mcp + X-API-Key-Auth-Middleware
├── services/
│   ├── pdf.py               # WeasyPrint: HTML → PDF
│   ├── numbering.py         # Angebotsnummer AR-YYYY-NNN
│   ├── auth.py              # Passwort-Hashing, Session-Utilities
│   ├── ai.py                # Claude-API-Integration
│   ├── proposals.py         # Shared Helpers (create / mark_sent) — UI + MCP
│   └── mcp_server.py        # FastMCP-Server mit 10 Tools (Leads / Notes / Proposals)
├── templates/
│   ├── base.html            # Nav, Brand-CSS/JS
│   ├── dashboard.html       # Pipeline-Übersicht
│   ├── auth/
│   │   └── login.html       # Login-Formular
│   ├── admin/
│   │   ├── users.html       # Benutzerliste
│   │   ├── user_form.html   # Benutzer anlegen / bearbeiten
│   │   ├── api_keys.html    # API-Key-Verwaltung
│   │   └── ai_settings.html # KI-Modell & Systemeinstellungen
│   ├── leads/
│   │   ├── list.html        # Tabelle mit Filter
│   │   ├── detail.html      # Lead-Detail, Pipeline, Notizbuch, KI-Tab
│   │   └── form.html        # Anlegen / Bearbeiten
│   └── proposals/
│       ├── editor.html      # Angebots-Editor mit Live-Preview
│       ├── view.html        # Angebots-Ansicht mit Aktionen
│       └── document.html    # Gebrandetes Dokument (HTML + PDF-Quelle)
├── static/
│   └── app.css              # App-spezifische Styles (ergänzt Brand-Kit)
├── generated_pdfs/          # Erzeugte PDFs (gitignored)
├── Dockerfile
├── docker-compose.yml       # App + Caddy (lokales Dev/Standalone)
├── Caddyfile
├── requirements.txt
└── .env.example
```

Das Brand-System liegt direkt im Repo unter `static/brand/` und wird über den Standard-`/static`-Mount ausgeliefert (`/static/brand/...`). Siehe Abschnitt **Brand-System** weiter unten.

---

## Brand-System

Vibe ist als **Single-Tenant-Anwendung** für eine Brand (aktuell: Agentic Reach) gebaut. Die Brand-Identität verteilt sich auf zwei Orte:

**1. Visuelle Assets — `static/brand/`**

```
static/brand/
├── logos/              # SVG-Lockups (horizontal-color, mark-color, …)
├── portrait/           # Foto des Absenders (z.B. für Signatur)
├── tokens.css          # CSS-Variablen: Farben, Spacing, Radien
├── typography.css      # Schrift-Stack & Type-Scale
├── brand-kit.css       # Aggregator (importiert tokens + typography)
├── components.css      # Brand-spezifische UI-Bausteine
└── components.js       # Optionales JS (z.B. animierte Marken-Elemente)
```

Wird vom Browser unter `/static/brand/...` ausgeliefert. Templates referenzieren Assets über die Variable `asset_base` (z.B. `{{ asset_base }}/logos/lockup-horizontal-color.svg`).

**2. Brand-spezifische Strings im Code**

Aktuell hardcoded — bewusst, weil Single-Tenant:

| Stelle | Was |
|---|---|
| `services/numbering.py` | Angebotsnummer-Präfix `AR-YYYY-NNN` |
| `services/ai.py` | KI-System-Prompts („Du bist Texter für Agentic Reach …") |
| `templates/base.html` | HTML-`<title>`, Logo-`alt` |
| `templates/proposals/document.html` | Firmenname, Anschrift, Mail, Signatur (Letterhead, Footer, Schlussseite) |

### Für eine andere Brand forken

Solange Vibe Single-Tenant bleibt, ist ein Fork der einfachste Weg. Checkliste:

1. **Assets ersetzen** — `static/brand/` 1:1 durch eigene Dateien überschreiben. Gleiche Dateinamen (`logos/lockup-horizontal-color.svg`, `logos/mark-color.svg`, `tokens.css`, …) → kein Code-Change nötig. CSS-Variablen in `tokens.css` (Farben, Spacing) anpassen.
2. **Angebotsnummer** — Präfix in `services/numbering.py:8` ändern (z.B. `AR-` → `BX-`).
3. **KI-Prompts** — Markenname in `services/ai.py` (3 Stellen) ersetzen.
4. **Templates** — Firmenname, Anschrift, Mail, Signatur in `templates/base.html` und `templates/proposals/document.html` ersetzen. Title-Tag in `base.html` anpassen.
5. **Deployment** — eigene `APP_HOST`-Variable, eigener Traefik/Caddy-Hostname.

Wer mehrere Brands aus **derselben Codebase** betreiben will (Multi-Tenant), siehe Roadmap-Punkt „Brand-Konfiguration via ENV/Datenbank".

---

## Datenmodell

### Lead
Zentrales Objekt. Name **oder** Firma ist Pflicht — beide können angegeben werden.

| Feld | Typ | Beschreibung |
|---|---|---|
| `name` | String? | Vorname Nachname |
| `company` | String? | Unternehmensname |
| `salutation` | String? | „Frau" / „Herr" / leer (für Anrede in Angeboten) |
| `email` / `phone` | String? | Kontaktdaten |
| `source` | Enum | `website · referral · agent · manual · linkedin` |
| `stage` | Enum | `new → contacted → proposal_sent → negotiating → won / lost` |
| `notes` | Text? | Legacy-Freitextfeld (ersetzt durch Note-Einträge) |
| `tags` | JSON-Array? | Frei vergebbare Schlagworte |
| `agent_metadata` | JSON? | Metadaten automatisch eingelieferter Leads |
| `plan_text` | Text? | Vom KI-Planungs-Tab erzeugte Zusammenfassung |

### Proposal (Angebot)
Gebunden an einen Lead. Nummer: `AR-YYYY-NNN`.

Enthält 1–3 Leistungsblöcke (Strategie, Change, Technik), Konditionen (Preis, Laufzeit, Zahlung) und wird als HTML + PDF gerendert.

Status: `draft → sent → accepted / declined`

### Note (Notiz)
Timestamped Notizbuch-Einträge pro Lead. Unterstützt Markdown (`**fett**`, `- Liste`, `## Abschnitt`). Wird client-seitig gerendert.

### User
Interne Benutzer mit E-Mail/Passwort-Login. Rollen: `admin` / `editor` / `viewer`. Admins können Benutzer und API-Keys verwalten sowie KI-Einstellungen konfigurieren. Editor und Viewer dürfen Leads/Angebote ansehen; Editor zusätzlich anlegen und bearbeiten.

### ApiKey
Im Admin-Bereich angelegte Tokens für REST- und MCP-Zugriff. Nur der SHA-256-Hash wird gespeichert; der Klartext wird genau einmal beim Erstellen angezeigt. `is_active=False` (Revoke) wirkt ab dem nächsten Request für REST und MCP zugleich. `last_used_at` wird bei jedem authentifizierten Request aktualisiert.

---

## API-Keys

Tokens werden im Admin-Bereich unter **„API-Keys"** erstellt (`/admin/api-keys`). Sie authentifizieren beide Schnittstellen — REST und MCP — über denselben Header `X-API-Key`. Beim Erstellen wird der Klartext genau einmal angezeigt; gespeichert wird nur ein SHA-256-Hash. Revoke (Widerrufen) entwertet einen Key sofort für beide Pfade.

Eine Legacy-Variable `API_KEY` aus `.env` funktioniert weiter als Fallback (für bestehende Agent-Integrationen vor der Admin-Tabelle).

---

## Agent-API (REST)

Alle Endpunkte unter `/api/` · Authentifizierung: `X-API-Key: <token>` im Header.

```
POST   /api/leads          Neuen Lead einliefern
GET    /api/leads          Alle Leads (Filter: ?stage=new&source=agent)
GET    /api/leads/{id}     Lead-Detail
PATCH  /api/leads/{id}     Lead aktualisieren
```

### Beispiel: Lead einliefern

```bash
curl -X POST https://vibe.agentic-reach.com/api/leads \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <token>" \
  -d '{
    "name": "Anna Müller",
    "company": "Mustermann GmbH",
    "email": "a.mueller@mustermann.de",
    "source": "agent",
    "notes": "Interesse an Strategie-Beratung geäußert",
    "agent_metadata": {
      "origin": "website-contact-form",
      "triggered_at": "2026-05-05T14:30:00Z"
    }
  }'
```

Response: `201 Created` + Lead-Objekt als JSON.

---

## MCP-Server

Vibe spricht das **Model Context Protocol** über Streamable HTTP unter `/mcp/` (Trailing Slash beachten — beim Mounten leitet Starlette ohne Slash mit 307 um). Damit lässt sich das System direkt aus Claude Code, Claude Desktop oder einem MCP-Inspector heraus bedienen — ohne Boilerplate-Wrapper um die REST-API.

Auth: gleicher `X-API-Key`-Header wie bei der REST-API. Der MCP-Session-Manager läuft im Lifespan der FastAPI-App (siehe `main.py`); pro HTTP-Request prüft eine ASGI-Middleware (`routes/mcp.py`) den Key gegen die `ApiKey`-Tabelle.

### Verfügbare Tools

| Bereich | Tool | Wirkung |
|---|---|---|
| Leads | `create_lead` | Neuen Lead anlegen (Default-Source: `agent`) |
| Leads | `list_leads` | Alle Leads, optional nach Stage/Source/Limit |
| Leads | `get_lead` | Einzelnen Lead per ID |
| Leads | `update_lead` | Felder patchen (Stage, Kontaktdaten, Notizen) |
| Notes | `add_note` | Notiz an Lead anhängen |
| Notes | `list_notes` | Notizen eines Leads, neueste zuerst |
| Proposals | `create_proposal` | Angebots-Entwurf für Lead anlegen |
| Proposals | `list_proposals` | Angebote, optional nach Lead/Status |
| Proposals | `get_proposal` | Einzelnes Angebot inkl. `pdf_url` |
| Proposals | `mark_proposal_sent` | Status auf `sent` setzen, `sent_at` stempeln |

Hinweis: Die `pdf_url` aus `get_proposal` zeigt auf `/proposals/{id}/pdf` und benötigt eine eingeloggte Browser-Session — direkter Download per `X-API-Key` ist (noch) nicht möglich.

### Anbindung an Claude Code

```bash
claude mcp add --transport http vibe \
  https://vibe.agentic-reach.com/mcp/ \
  --header "X-API-Key: <key-aus-admin-ui>"
```

### Anbindung an Claude Desktop

In `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "vibe": {
      "transport": { "type": "http", "url": "https://vibe.agentic-reach.com/mcp/" },
      "headers": { "X-API-Key": "<key-aus-admin-ui>" }
    }
  }
}
```

### Lokales Debuggen

```bash
npx @modelcontextprotocol/inspector
# Connect: http://localhost:8000/mcp/  · Header X-API-Key
```

---

## Angebote & PDF

1. Lead öffnen → „Angebot erstellen"
2. Leistungsblöcke aktivieren und beschreiben (1–3 aus: Strategie / Change / Technik)
3. Konditionen eintragen (Preis, Laufzeit, Zahlungsmodalitäten)
4. Live-Preview im Browser (iframe)
5. „PDF ↓" — WeasyPrint rendert das gebrandete HTML-Dokument zu PDF
6. Manuell versenden, dann „Als gesendet markieren"

---

## KI-Planungs-Tab

Auf jedem Lead gibt es einen „Planung"-Tab mit Claude-Integration:

- **Chat** — freies Gespräch im Kontext des Leads
- **Zusammenfassung** — automatisch generierte Lead-Zusammenfassung
- **Prompt-Export** — generiert einen Prompt für externe Nutzung

KI-Modell und Systemeinstellungen sind im Admin-Bereich konfigurierbar.

---

## Deployment (Docker + Caddy)

```bash
# .env befüllen
cp .env.example .env

# Starten
docker compose up -d

# Logs
docker compose logs -f app
```

Caddy übernimmt automatisch TLS via Let's Encrypt.

Das Brand-Verzeichnis ist Teil des Image-Builds (im Repo unter `static/brand/`) — kein zusätzliches Volume nötig.

> Der Produktions-Deploy läuft über GitHub Actions (`.github/workflows/deploy.yml`) und Traefik als Reverse Proxy.

---

## Roadmap

### Offen
- [ ] E-Mail-Versand (Resend API) mit PDF-Anhang
- [ ] Aktivitäts-Timeline pro Lead
- [ ] Stage-Kanban-Board
- [ ] Webhook-Events (Lead eingeliefert → Slack/Notification)
- [ ] Öffentliche Angebots-Links für Kunden
- [ ] Pipeline-Reporting & -Auswertung
- [ ] API-authentifizierter PDF-Download (`/api/proposals/{id}/pdf`), damit MCP-Agenten Angebote direkt verschicken können
- [ ] Per-Key-Scoping (REST / MCP / beide) auf `ApiKey`
- [ ] **Brand-Konfiguration via ENV/Datenbank** — hardcoded Strings (Firmenname, Anschrift, Mail, Angebots-Präfix, KI-Prompts) auf Konfig-Variablen heben, damit Fork = nur Assets tauschen + ENV setzen. Erst sinnvoll, wenn ≥ 2 Brands aus derselben Codebase betrieben werden sollen.

### Umgesetzt
- [x] Login & Session-Auth (E-Mail / Passwort)
- [x] Benutzerverwaltung & Rollen (Admin / Editor / Viewer)
- [x] API-Key-Verwaltung im Admin-Bereich (SHA-256 Hash, Revoke, `last_used_at`)
- [x] KI-Planungs-Tab (Claude-Chat, Zusammenfassung, Prompt-Export)
- [x] Notizbuch pro Lead (Markdown-fähig)
- [x] Gebrandete Angebots-PDFs (WeasyPrint, Klassisch-Premium 3-Seiten-Template)
- [x] Adaptives Light/Dark-Favicon
- [x] Agent-REST-API (`/api/leads`) für automatische Lead-Einlieferung
- [x] **MCP-Server (`/mcp/`) mit 10 Tools für Leads, Notes und Proposals — gleicher API-Key wie REST**

---

## Invoicing — §14 UStG-konformes Rechnungs-Modul

Seit 2026-05 ist das System auch um die Rechnungsstellung erweitert. Das Modul
deckt §§ 14, 14a UStG, UStDV und GoBD ab und erzeugt **ZUGFeRD/Factur-X**
PDF/A-3-Rechnungen mit eingebettetem EN16931-XML — bereit für die
E-Rechnungspflicht ab 2028.

### Schnellstart

1. **Aussteller-Daten pflegen:** Als Admin `/admin/issuer` öffnen, Felder
   ausfüllen (Anschrift, Steuernummer/USt-IdNr., Bank, ggf.
   Kleinunternehmer-Flag).
2. **Lead mit Adresse:** Rechnungsempfänger braucht Straße, PLZ, Stadt,
   Land. Die Felder sind seit dem 2026-05-Update direkt am Lead pflegbar.
3. **Rechnung erstellen:** Über die Lead-Detailseite oder direkt unter
   `/invoices/new`.
4. **Positionen hinzufügen** und **finalisieren.** Beim Finalize wird die
   Nummer (`RE-YYYY-NNNN`) vergeben, das PDF/A-3 + XML erzeugt und unter
   `archive/invoices/{YYYY}/` abgelegt (chmod 0444). Die Rechnung ist ab
   diesem Moment unveränderlich.
5. **Versand** erfolgt manuell außerhalb des Systems; im UI auf „Als
   versendet markieren" / „Als bezahlt markieren" klicken.
6. **Storno:** Auf der Detailseite. Erstellt eine neue Rechnung mit eigener
   Nummer, negativen Beträgen und Verweis auf das Original. Original wird
   `cancelled`, bleibt unverändert lesbar.

### Pflicht-Doku

- `docs/verfahrensdokumentation.md` — GoBD-Pflichtdokument (Steuerprüfer-Doku).
- `docs/runbook.md` — operative Schritte (Integrity-Check, Restore, Override).
- `docs/adr/` — Architektur-Entscheidungen mit Begründung (6 ADRs).
- `docs/open-questions.md` — bewusst nicht in v1 umgesetzt.

### Integritätsprüfung

```bash
make integrity-check
# oder
.venv/bin/python -m services.invoicing.integrity_check --json
```

Empfohlen als Cron-Job auf dem Server. Exit `0` = ok, `1` = Mismatch,
`2` = fataler Fehler.

### Issuer-Bootstrap aus ENV

Beim ersten Boot legt `bootstrap_issuer()` einen `IssuerProfile`-Eintrag aus
folgenden ENV-Variablen an:

```
ISSUER_LEGAL_NAME=Agentic Reach · Ulrich Schinz
ISSUER_STREET=Staltacher Straße 59A
ISSUER_POSTAL_CODE=82393
ISSUER_CITY=Iffeldorf
ISSUER_COUNTRY_CODE=DE
ISSUER_STEUERNUMMER=
ISSUER_USTID=
ISSUER_KLEINUNTERNEHMER=false
ISSUER_BANK_HOLDER=
ISSUER_BANK_IBAN=
ISSUER_BANK_BIC=
ISSUER_CONTACT_EMAIL=hello@agentic-reach.com
```

Spätere Änderungen an diesen ENV-Variablen haben keinen Effekt mehr — der
Admin pflegt die Daten ab dann ausschließlich über `/admin/issuer`.

---

## Testing

Das Projekt hat ein vollständiges, projektweites Testframework auf Basis von
`pytest` + `hypothesis` + `freezegun`. Coverage-Ziel ist ≥ 90 % für das
Invoicing-Modul.

```bash
# Dev-Deps installieren
uv pip install -r requirements-dev.txt

# Schneller Lauf (Unit + Integration, ~6 s)
make test-fast

# Vollständig (inkl. KoSIT, veraPDF — braucht Java 17 + KoSIT-Jar im Cache)
make test

# Nur Unit-Tests (am schnellsten)
make test-unit

# End-to-End via FastAPI TestClient
make test-e2e

# KoSIT-Validator gegen erzeugte XML (CI-Gate)
make test-kosit
```

Layout:

```
tests/
  unit/         # VAT-Engine, Money, State Machine — pure Python
  integration/  # Schema-Migrations, Numbering, Finalize, Storno, VIES, Archive
  contract/     # KoSIT, veraPDF (extern)
  e2e/          # FastAPI TestClient, REST-API
  fixtures/     # Factories für Issuer, Leads (DE/EU/Drittland), Drafts
```

Coverage-Reports landen in `reports/coverage/` (HTML + lcov + xml).
KoSIT-Output unter `reports/kosit/`.

Die CI-Pipeline (`.github/workflows/test.yml`) läuft auf jedem Push und PR:
Python 3.12 + Java 17 + WeasyPrint-Apt-Deps + KoSIT-Jar herunterladen +
`make test-fast` + `make test-contract` (continue-on-error in v1) + `make test-e2e`.
