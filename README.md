# Agentic Reach — Lead Management

Internes CRM-Werkzeug für Agentic Reach. Verwaltet Leads, generiert gebrandete Angebote als PDF und bietet eine REST-API, über die KI-Agenten Leads automatisch einliefern können.

---

## Stack

| Schicht | Technologie |
|---|---|
| Backend | Python 3.12+ · FastAPI · Uvicorn |
| Datenbank | SQLite via SQLModel (migrierbar zu Postgres) |
| Templates | Jinja2 + Brand-System (`../brand/`) |
| PDF | WeasyPrint |
| Paketmanager | uv |

---

## Lokaler Start

```bash
# 1. Abhängigkeiten installieren (einmalig)
uv venv
uv pip install -r requirements.txt

# 2. Umgebungsvariablen einrichten
cp .env.example .env
# .env bearbeiten: API_KEY setzen

# 3. Server starten
source .venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Die App ist dann unter `http://localhost:8000` erreichbar.

---

## Umgebungsvariablen

| Variable | Bedeutung | Beispiel |
|---|---|---|
| `DATABASE_URL` | SQLite-Pfad oder Postgres-URL | `sqlite:///./leads.db` |
| `API_KEY` | Bearer-Token für die Agent-API | zufälliger 32-Byte-String |
| `APP_HOST` | Hostname (für Deployment) | `leads.agentic-reach.com` |

---

## Verzeichnisstruktur

```
leads/
├── main.py                  # FastAPI-App, Static-Mounts, Lifespan
├── models.py                # SQLModel-Datenmodelle (Lead, Proposal, Note)
├── database.py              # Engine, Session, create_db()
├── routes/
│   ├── leads.py             # Web-UI: Dashboard, Lead-Liste, Detail, Formular
│   ├── proposals.py         # Proposal-Editor, PDF-Download, Status
│   └── api.py               # Agent-REST-API (/api/leads)
├── services/
│   ├── pdf.py               # WeasyPrint: HTML → PDF
│   └── numbering.py         # Angebotsnummer AR-YYYY-NNN
├── templates/
│   ├── base.html            # Nav, Brand-CSS/JS
│   ├── dashboard.html       # Pipeline-Übersicht
│   ├── leads/
│   │   ├── list.html        # Tabelle mit Filter
│   │   ├── detail.html      # Lead-Detail, Pipeline, Notizbuch
│   │   └── form.html        # Anlegen / Bearbeiten
│   └── proposals/
│       ├── editor.html      # Angebots-Editor mit Live-Preview
│       ├── view.html        # Angebots-Ansicht mit Aktionen
│       └── document.html    # Gebrandetes Dokument (HTML + PDF-Quelle)
├── static/
│   └── app.css              # App-spezifische Styles (ergänzt Brand-Kit)
├── generated_pdfs/          # Erzeugte PDFs (gitignored)
├── Dockerfile
├── docker-compose.yml       # App + Caddy (TLS)
├── Caddyfile
├── requirements.txt
└── .env.example
```

Das Brand-System liegt in `../brand/` und wird zur Laufzeit als `/static/brand` gemountet.

---

## Datenmodell

### Lead
Zentrales Objekt. Name **oder** Firma ist Pflicht — beide können angegeben werden.

| Feld | Typ | Beschreibung |
|---|---|---|
| `name` | String? | Vorname Nachname |
| `company` | String? | Unternehmensname |
| `email` / `phone` | String? | Kontaktdaten |
| `source` | Enum | `website · referral · agent · manual · linkedin` |
| `stage` | Enum | `new → contacted → proposal_sent → negotiating → won / lost` |
| `notes` | Text? | Legacy-Freitextfeld (ersetzt durch Note-Einträge) |
| `agent_metadata` | JSON? | Metadaten automatisch eingelieferter Leads |

### Proposal (Angebot)
Gebundene an einen Lead. Nummer: `AR-YYYY-NNN`.

Enthält 1–3 Leistungsblöcke (Strategie, Change, Technik), Konditionen (Preis, Laufzeit, Zahlung) und wird als HTML + PDF gerendert.

Status: `draft → sent → accepted / declined`

### Note (Notiz)
Timestamped Notizbuch-Einträge pro Lead. Unterstützt Markdown (`**fett**`, `- Liste`, `## Abschnitt`). Wird client-seitig gerendert.

---

## Agent-API

Alle Endpunkte unter `/api/` · Authentifizierung: `X-API-Key: <token>` im Header.

```
POST   /api/leads          Neuen Lead einliefern
GET    /api/leads          Alle Leads (Filter: ?stage=new&source=agent)
GET    /api/leads/{id}     Lead-Detail
PATCH  /api/leads/{id}     Lead aktualisieren
```

### Beispiel: Lead einliefern

```bash
curl -X POST https://leads.agentic-reach.com/api/leads \
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

## Angebote & PDF

1. Lead öffnen → „Angebot erstellen"
2. Leistungsblöcke aktivieren und beschreiben (1–3 aus: Strategie / Change / Technik)
3. Konditionen eintragen (Preis, Laufzeit, Zahlungsmodalitäten)
4. Live-Preview im Browser (iframe)
5. „PDF ↓" — WeasyPrint rendert das gebrandete HTML-Dokument zu PDF
6. Manuell versenden, dann „Als gesendet markieren"

---

## Deployment (Docker + Caddy)

```bash
# .env befüllen (API_KEY, APP_HOST)
cp .env.example .env

# Starten
docker compose up -d

# Logs
docker compose logs -f app
```

Caddy übernimmt automatisch TLS via Let's Encrypt.  
Domain in `Caddyfile` anpassen: `leads.agentic-reach.com`.

Das Brand-Verzeichnis (`../brand`) wird als Read-only-Volume gemountet.

---

## Roadmap

### Phase 2
- [ ] E-Mail-Versand (Resend API) mit PDF-Anhang
- [ ] Aktivitäts-Timeline pro Lead
- [ ] Stage-Kanban-Board

### Phase 3
- [ ] Login (einfache Auth für Team-Zugang)
- [ ] Webhook-Events (Lead eingeliefert → Slack/Notification)
- [ ] Öffentliche Angebots-Links für Kunden
- [ ] Pipeline-Reporting & -Auswertung
