# Scaling Roadmap — Soll-Zustand & Migrationspfad

> Begleitet [`../ARCHITECTURE.md`](../ARCHITECTURE.md) (Ist-Zustand).
> Ziel: das Repo so aufbauen, dass es bei vielfachem Umfang **erweiterbar,
> verständlich und für einen Coding-Agenten *konsistent bearbeitbar*** bleibt
> — kein „random code in random files".
>
> **Status:** **Freigegeben (Rev. 2, 2026-05-16).** Umsetzung startet bei
> Schritt 0. Architektur und Schritt-Reihenfolge sind entschieden — nicht
> neu aufrollen, nur ausführen. Jeder Schritt = ein eigener PR; Fortschritt
> s. Memory `scaling-roadmap-progress`.
>
> **Rev.-2-Leitsatz:** Die Verzeichnisstruktur allein macht einen Agenten
> nicht konsistent. Was ihn konsistent macht, ist **ausführbarer Zwang**
> (Scaffold + Import-Linter) plus ein **erzwungen-korrekter Ort, den der
> Agent zuerst liest** (CLAUDE.md/AGENTS.md). Diese Bausteine sind deshalb
> *Teil des Umbaus*, nicht nachgelagert.

## Warum (Problem)

Die Struktur ist *technisch* geschichtet (`routes/`, `services/`, ein
`models.py`), nicht *domänenorientiert*. Das funktioniert bei der heutigen
Größe (8.737 LOC), bremst aber bei 2–3× Feature-Umfang: eine neue Domäne
berührt `models.py` + mehrere dicke Route-Module + dupliziert Logik in MCP.
Verständlichkeit und Agent-Navigierbarkeit sinken mit jeder Zeile in den
Sammeldateien — und ein Agent ohne erzwungene Konvention legt Code dort ab,
wo er gerade „plausibel" wirkt.

## Soll-Architektur: domänenorientiert

Eine Domäne = ein Paket = eine in sich geschlossene, ausschneidbare Einheit.

```
app/
  core/          # config.py (pydantic-settings), db.py, security.py,
                 # logging.py, errors.py, ai.py (Anthropic-Adapter +
                 # Prompt-Registry) ── wiederverwendbarer Kern
  contracts/     # billing_order.py — published DTO (Anti-Corruption-Naht)
  domains/
    leads/       # models.py  schemas.py  service.py  repository.py  router.py
    proposals/   # dito — inkl. AI-Draft-Merge IM proposals-service
    billing/     # ehem. services/invoicing/ — BOUNDED CONTEXT:
                 #   eigene models (eigenes Tabellen-Schema), eigene
                 #   numbering+audit, eigener Store-Adapter, Fassade+router;
                 #   importiert NICHTS aus domains/* — nur
                 #   contracts/billing_order
  interfaces/
    web/         # Jinja-Routen (UI)  + templates/
    api/         # REST-Router; RFC-7807-Fehler ZENTRAL (ein Mapper)
    mcp/         # FastMCP; Tools rufen domains/*/service.py — keine Duplikate
  shared/        # labels/i18n, pdf, numbering, money
```

> **Geändert ggü. Rev. 1:** Kein `domains/crm_ai/`. „AI-Orchestrierung" ist
> eine *Capability*, keine Domäne — als eigenes Paket schafft sie ein
> zweites plausibles Zuhause für Proposal-/Planning-Logik und damit genau
> die Ambiguität, die wir abschaffen wollen. AI-Modellzugriff +
> Prompt-Registry liegen als Adapter in `core/ai`; die *Orchestrierung*
> (Draft-Merge, Planning) liegt im Service der besitzenden Domäne
> (`proposals`, `leads`).

### Leitprinzipien

| Prinzip | Vorher | Nachher |
|---|---|---|
| Eine Domäne, ein Paket | `models.py` 610 Z. (14 Tabellen) | `domains/<x>/models.py` je Domäne |
| Labels sind Daten | Label-Dicts in `models.py` | `shared/labels.py` (oder JSON/i18n) |
| Routes sind dünn | Aggregation/Import/AI-Merge im Handler | Handler → `service.py` → Response |
| Eine Logik, drei Clients | MCP dupliziert Lead/Proposal | Web/REST/MCP rufen denselben Service |
| Config zentral | `os.getenv` in 6 Dateien | `core/config.py`, Fail-fast bei Start |
| Billing-Grenze | `_snapshot_customer` liest `Lead` direkt | `BillingOrder`-Vertrag; `billing/` kennt kein CRM |
| Compliance einfrieren | `services/invoicing/` (90 % Cov.) | Code **verschieben, nicht umschreiben** |
| **Konvention ist ausführbar** | Prosa „bitte so machen" | **Scaffold-Generator + Import-Linter brechen den Build** |
| **Agent liest zuerst Wahrheit** | CLAUDE.md driftet (10 vs. 16 MCP-Tools) | CLAUDE.md/AGENTS.md = CI-verifizierter Vertrag |
| Repository nur bei Bedarf | Queries in Routes verstreut | `repository.py` erst wo dupliziert |

> **Invoicing-Code ist tabu für Refactor.** Rechtlich kritisch (§14 UStG /
> ZUGFeRD), 90 % Coverage. Der Code wird *verschoben*, nicht umgeschrieben;
> die bestehenden Tests sind das Sicherheitsnetz und müssen bei jedem
> Schritt grün bleiben. **Einzige inhaltliche Änderung:** der direkte
> `Lead`-Zugriff in `_snapshot_customer()` wird durch den
> `BillingOrder`-Vertrag ersetzt — Details unten.

## Architektur-Entscheidung: Billing-Trennung

**Beschluss: Billing wird ein extraktions-fähiger Bounded Context im
selben Prozess — kein Zwei-App-Split jetzt.** Der eigentliche Aufwand ist
der *Vertrag/Schnitt, nicht das Deployment*; er ist für „zusammen" und
„getrennt" identisch und wird jetzt gemacht. Damit ist ein späterer
physischer Split eine reine Deploy-Entscheidung, kein Rewrite.

Warum nicht jetzt zwei Apps:

| Faktor | Pro „zusammen, harte Grenze" |
|---|---|
| Kopplung | Einziger echter CRM-Reach = `finalize.py::_snapshot_customer()` → durch Vertrag ersetzbar |
| Compliance | Audit/GoBD-Nutzen kommt aus eigenem Store + Immutabilität + abgegrenzter Verfahrensdoku, **nicht** aus eigenem Prozess (DB-Trigger + Hashchain existieren bereits) |
| Risiko | In-Prozess-Grenze hält die 90 %-Suite als Netz; Service-Split erzwingt Test-Umbau über Netzgrenze |
| Ops | Zwei Deployables = Idempotenz/Outbox/Netzausfall/Vertrags-Versionierung — Dauer-Steuer für eine Single-Process-App |

**Split-Trigger** (erst dann Stufe B = eigener Service + eigene DB):

1. Ein **zweites Quellsystem / externe Kunden** nutzen Billing.
2. **Zwingend unabhängige Deploy-Kadenz** (Prüfungs-Freeze des Billings
   bei täglich deployendem CRM) — sonst per Release-Disziplin lösbar.
3. **Steuerberater/Prüfer verlangt ein physisch getrenntes System** für
   die Verfahrensdokumentation. ⚠️ Extern, **mit Steuerberater
   abzuklären** — nicht im Code entscheidbar.

### `BillingOrder`-Vertrag (`app/contracts/billing_order.py`)

Der explizite „abrechnungswürdige Auftrag", den der CRM-Teil exportiert.
Trägt einen **unveränderlichen Snapshot** — Billing greift nie auf CRM
zurück:

- `order_ref`, `idempotency_key`
- `issuer{}` — Snapshot aus `IssuerProfile` (heute `finalize.py` Read)
- `customer{}` — heute aus `Lead.{salutation,street,street2,postal_code,
  city,country_code,vat_id,is_business,email,name,company}`
- `lines[]` — Beschreibung, Menge, Einheit, Netto, VAT-Hinweis
- `meta{}` — Titel, Leistungsdatum, Zahlungsziel, Referenzen

Billing **validiert/berechnet selbst** (VIES, VAT, Nummernkreis,
Hashchain) und liefert Rechnungs-Referenz + Status zurück. `billing/`
importiert nichts aus `domains/*`/`models` — als Import-Linter-Regel
erzwungen (s. Verifikation).

### DSGVO ↔ GoBD

Leads sind löschbar (DSGVO Art. 17), Rechnungen ~10 Jahre unveränderbar
aufzubewahren (GoBD). Snapshot in `cust_*`/`iss_*` + Soft-FK
`Invoice.lead_id` (kein Cascade) entkoppeln den *Inhalt* bereits; offener
Punkt = die **gemeinsame DB-Datei**. Lösung in-process: eigenes
Billing-Tabellen-Schema (Schritt 4) + eigene Aufbewahrungsregel + getrennt
versionierte Migrationen (Schritt 9); Lead-Löschung darf finalisierte
Rechnungen nie berühren. Ermöglicht späteren DB-Split ohne Daten-Migration.

### Tool-Umfang

Fokussierter Billing-Service-Zuschnitt: Auftrag rein → Rechnung/ZUGFeRD/
Archiv/Hashchain raus; minimale Admin-UI (Liste, Storno, Verfahrensdoku).
Generisch genug, dass Multi-Brand später nicht blockiert ist — aber
**kein** eigenständiges Multi-Mandanten-Produkt jetzt (YAGNI; Multi-Brand
bleibt Roadmap).

## Migrationspfad (risiko-aufsteigend, jeder Schritt grün)

Jeder Schritt = eigener PR; Akzeptanz = `make test` + Linter + Import-Linter
grün, **keine Verhaltensänderung**. Reihenfolge-Prinzip Rev. 2:
*Konventionen ausführbar und das finale Skelett früh* (billig, hoher ROI,
risikoarm) — *dann* Code **einmal** an seinen Endplatz bewegen.

0. **CLAUDE.md/AGENTS.md = erzwungener Vertrag (Nullrisiko).** Doc-Drift
   sofort fixen (CLAUDE.md nennt „10 MCP-Tools", real 16; weitere Zahlen
   gegen `ARCHITECTURE.md` abgleichen). Kleines CI-Script, das die in
   `ARCHITECTURE.md` dokumentierten Kennzahlen *asserted* (kein Graph,
   nur `assert`) → Doc-Drift bricht künftig den Build. Betrifft nur Doku +
   ein Script.

0.5 **Characterization-/Golden-Tests auf die Bruchstellen.** Begründung:
   die 90 %-Coverage liegt in `invoicing/` — *dort, wo nichts geändert
   wird*. Die riskanten Schritte 6–7 treffen die **am wenigsten
   getesteten** Module; ohne dieses Netz ist „keine Verhaltensänderung"
   dort nicht verifizierbar.

   **Characterization-Vertrag** (Akzeptanz für Schritt 0.5):

   - **Genauer Scope (nur was Schritt 5–7 anfasst, nicht ganze Module):**
     - `routes/leads.py`: Dashboard-Aggregation, LinkedIn-Import-Flow,
       Lead→Proposal-Erzeugung.
     - `routes/proposals.py`: AI-Draft-Erzeugung + Merge.
     - `services/mcp_server.py`: `create_lead`/`update_lead` (Duplikat-
       Logik) + die Proposal-/Finalize-Tools, die Schritt 7 umbiegt.
     - `routes/api.py`: die Endpoints mit Inline-RFC-7807-Coercion, die
       Schritt 8 zentralisiert.
   - **Zusicherungs-Granularität (stabil, nicht kosmetik-fragil):**
     HTTP-Status + Redirect-`Location` + **DB-Seiteneffekt** (welche
     Rows/Felder sich ändern), **nicht** HTML-Body. MCP: Rückgabe-Payload-
     *Shape* + DB-Seiteneffekt. Externe Aufrufe (Anthropic, LinkedIn-PDF,
     VIES) gestubbt/aufgezeichnet → deterministisch.
   - **Akzeptanz (nicht die globalen 90 %):** Jeder oben gelistete
     Handler/Tool hat ≥1 Characterization-Test (Status + Seiteneffekt);
     eine Checkliste mappt Test → Migrationsschritt. **Härtekriterium:**
     diese Tests bleiben über Schritte 5–8 **unverändert grün** — *das*
     ist der Nachweis „keine Verhaltensänderung". Ein Diff an einem
     Characterization-Test in jenen PRs ist ein Rotflag und
     begründungspflichtig.
   - **Lebenszyklus:** Ein Characterization-Test wird **erst in demselben
     PR gelöscht, der den äquivalenten Service-Unit-Test einführt** —
     nie vorher (sonst Netz mit Loch).

1. **Tooling-Fundament inkl. ausführbarer Konvention (Schicht 2).**
   *Präzisierung (Issue #2): Schritt 1 ist real **„reparieren &
   erweitern"**, nicht „einführen". `Makefile`, `.github/workflows/
   test.yml` und `deploy.yml` **existierten bereits** (test.yml war
   kaputt → vor Schritt 0.5 per separater Fix-PR repariert; s. Memory
   `scaling-roadmap-progress`). Schritt 1 ergänzt die **fehlende**
   Lint-/Typecheck-/Import-Contract-Schicht und verdrahtet sie in einen
   `make verify`-Gate; Architektur und Reihenfolge bleiben unverändert.*
   Konkret: neu `pyproject.toml` (zentrale Tool-Config) + `ruff`
   (Lint+Format) + `mypy` (lax global, neue `app.*`-Module strict) **+
   `import-linter`** (erste **aktive** Contract-Regel auf dem realen
   heutigen Paket: `services.invoicing` importiert nicht `routes` — die
   *Saat* der `billing/`-Isolation; sie **schärft sich in Schritt 5** zur
   vollen Regel „kein `models`/`domains`-Import", sobald die
   `_snapshot_customer`-Naht durch `BillingOrder` ersetzt ist) **+
   Scaffold-Generator `make new-domain X`** (s. *Scaffold-Vertrag* unten).
   Die bestehende GitHub-Actions-CI (`test.yml`) wird **erweitert** statt
   neu angelegt: `make verify` (= `ruff` + `mypy` + `import-linter` +
   `test-fast` + Schritt-0-Doc-Gate) läuft je PR; das 90 %-`invoicing`-
   Coverage-Gate bleibt über `.coveragerc`/`make test`. Dies ist der
   eigentliche Anti-„random files"-Mechanismus: der Agent folgt einer
   Vorlage zuverlässig, improvisiert ohne sie.

   **Scaffold-Vertrag** (Akzeptanz für `make new-domain X`):

   - **Erzeugte Dateien-Skelette (Inhalt, nicht nur Namen):**
     - `models.py` — Modul-Docstring (Zweck, Entry-Points); `SQLModel`-
       Basisklasse importiert aus `app.core.db`; eine Beispiel-Tabelle
       `X` als auskommentierter/minimaler Stub.
     - `schemas.py` — Pydantic `XCreate`/`XRead`/`XUpdate`-Skelette.
     - `service.py` — Funktions-Stubs mit `Session`-Parameter *vom
       Aufrufer übergeben* (keine eigene `Session(engine)`); reine
       Business-Logik, kein FastAPI-Import.
     - `repository.py` — leer mit Docstring „erst anlegen, wenn Query
       dupliziert" (Prinzip „Repository nur bei Bedarf").
     - `router.py` — `APIRouter` mit `prefix=/x`, ein Beispiel-Handler,
       der ausschließlich `service.py` ruft; Web/REST-Variante je nach
       `interfaces/`-Ziel.
     - `tests/test_x.py` — ein lauffähiger Smoke-Test (Service-Ebene),
       der direkt grün ist.
   - **import-linter-Konformität per Konstruktion:** Der erzeugte Code
     besteht `make verify` (inkl. `import-linter`) *ohne Nacharbeit*.
     Insbesondere erzeugt der Scaffold **keine** Kante, die eine
     Contract-Regel verletzt (z. B. kein `domains/*`-Import in einem
     `billing/`-Scaffold, kein Modell-Konstruktor in `interfaces/mcp`).
     Akzeptanz: frisch scaffoldetes `X` → CI grün, null manuelle Edits.
   - **Registrierungs-Mechanismus:** Auto-Discovery bevorzugt — eine
     zentrale Stelle (`interfaces/{web,api,mcp}`) iteriert über
     `app/domains/*` und bindet `router.py` automatisch ein; der Scaffold
     muss **keine** zentrale Registry-Datei patchen. Falls Auto-Discovery
     für MCP-Tools nicht praktikabel, patcht der Scaffold *genau eine*
     deklarierte Registry-Datei (idempotent, im PR-Diff sichtbar). „Neue
     Domäne" bleibt damit ein Ein-Befehl-Schritt.

2. **Finales `app/`-Skelett früh anlegen.** Leere Pakete
   `domains/{leads,proposals,billing}` + `core/{config,db,security,
   logging,errors,ai}` + `contracts/` + `interfaces/{web,api,mcp}` +
   `shared/`, jeweils mit Modul-Docstring (Zweck, Entry-Points). Scaffold
   + Konventionen zeigen auf dieses Skelett. Zweck: jeder folgende Schritt
   bewegt Code **einmal** an seinen *Endplatz* — kein doppelter
   Import-Churn (Rev. 1 hatte Shim *und* späteren `app/`-Umzug).

3. **`core/config.py` (pydantic-settings).** Ersetzt alle `os.getenv`-
   Fundstellen (`database.py`, `main.py`, `routes/admin.py`,
   `routes/api.py`, `services/mcp_server.py`,
   `services/invoicing/archive.py`). Start bricht früh bei fehlender Var.

4. **`models.py` splitten — in die finalen Pakete.** Entlang der 14
   Tabellen → `app/domains/*/models.py` (nicht in einen Zwischenort);
   Enums zur jeweiligen Domäne; Label-Dicts → `app/shared/labels.py`.
   Billing-Modelle (Invoice, InvoiceLineItem, InvoiceNumberSequence,
   ViesAuditEntry) in **eigenes `billing/`-Tabellen-Schema**; Soft-FK
   `Invoice.lead_id` bleibt.

   **Move-Vertrag** (Akzeptanz — „reines Move" ist in SQLModel nicht
   trivial):

   - **`SQLModel.metadata`-Registrierung:** Jede Tabelle wird **genau
     einmal** registriert. Ein einziges Aggregations-Modul importiert
     alle `domains/*/models` in deterministischer Reihenfolge; `create_all`
     hängt daran. Test: Tabellen-Set in `metadata` vor/nach dem Split
     **byte-identisch** (Snapshot-Test), keine `Table already defined`.
   - **Shim-Mechanismus (kein `import *`):** `models.py` macht
     *explizite* Re-Exports (`from app.domains.leads.models import Lead,
     Note, …`) + `__all__`, damit Tabellen-Registrierung und IDE/AST-
     Auflösung eindeutig bleiben.
   - **Shim-Sterbe-Gate:** Eine `import-linter`-Regel „nichts importiert
     mehr aus dem Top-Level-`models`" wird *im selben PR* aktiviert, der
     den letzten Aufrufer migriert; erst dann wird `models.py` gelöscht.
     Ohne dieses Gate bleibt der Shim dauerhaft = zwei Churn-Events (genau
     das, was Schritt 2 verhindern soll).
   - **Jinja-Globals:** `STAGE_LABELS`/`SOURCE_LABELS`/… ziehen mit nach
     `shared/labels.py`; die Template-Injektion wird auf die neue Quelle
     umgebogen — Char-Test (0.5) auf das Dashboard deckt Regressionen ab.

5. **`BillingOrder`-Vertrag + Naht kappen** (compliance-kritisch, höchstes
   Augenmerk). `app/contracts/billing_order.py` definieren; CRM-Seite baut
   den Snapshot beim Export; `billing/` nimmt nur den Vertrag entgegen,
   `_snapshot_customer()`'s `Lead`-Zugriff entfällt. Akzeptanz:
   import-linter-Regel „`billing/` importiert nichts aus
   `domains/*`/`models`" grün **und** 90 %-Suite **und** Char-Tests grün.

6. **Business-Logik aus Routes ziehen.** Abgesichert durch Char-Tests aus
   Schritt 0.5.

   **Eigentümer-Zuordnung (fix, gegen „zwei plausible Häuser"):**

   | Logik (heute) | Ziel |
   |---|---|
   | Dashboard-Aggregation, LinkedIn-Import-Orchestrierung | `domains/leads/service.py` |
   | AI-Draft-Erzeugung + Merge (`routes/proposals.py`) | `domains/proposals/service.py` |
   | Planning-Chat-Verlauf (`PlanningMessage`) | `domains/leads/service.py` (Planning gehört zum Lead, nicht zum Proposal) |
   | Anthropic-Client, Modellwahl aus `AiSettings`, Prompt-Registry, `===MARKER===`-Parsing | `core/ai` (Adapter) |

   **Verbatim-Disziplin:** Prompts und das fragile `===MARKER===`-Parsing
   werden **wortgleich** nach `core/ai` verschoben — *kein* Robustheits-
   Fix in diesem Schritt (separates späteres Item; siehe Struktur-Schuld 6
   in `ARCHITECTURE.md`). „Keine Verhaltensänderung" gilt auch hier; ein
   Char-Test auf einen AI-Pfad mit aufgezeichneter Antwort beweist es.

7. **MCP entdoppeln.** `mcp_server.py`-Tools rufen `domains/*/service.py`
   statt `Lead(...)` selbst zu bauen; Session vom Aufrufer übergeben.
   Finalize-Tools rufen Billing über den Vertrag. Eine import-linter-Regel
   verbietet Domänen-Modell-Konstruktion in `interfaces/mcp` →
   Duplikat-Logik kann nicht zurückkehren. REST + MCP + Web teilen eine
   Logik.

8. **Interface-Split finalisieren** (`interfaces/{web,api,mcp}`). Code
   liegt durch Schritt 2 bereits im `app/`-Skelett; hier nur Router-
   Trennung + **zentraler RFC-7807-Mapper** (statt Inline-Coercion pro
   Endpoint). Mechanisch.

9. **Alembic einführen.** Baseline-Migration = aktuelles Schema; CRM- und
   Billing-Schema **getrennt versioniert** → ermöglicht späteren DB-Split
   ohne Daten-Migration. Danach keine impliziten `create_all`-Änderungen.

10. *(Optional, nur bei Split-Trigger)* **Stufe B:** `billing/` als eigenes
    Deployable + eigene DB; der `BillingOrder`-Vertrag wird HTTP/Queue mit
    Idempotenz/Outbox. Reine Infrastruktur-Änderung, da die Code-Grenze ab
    Schritt 5 bereits sauber ist.

## Agent-Navigations-Layer: drei Schichten mit *unterschiedlicher Epistemik*

Entscheidung: Indexierung dient dem **Coding-Agenten**, der eine künftig
5–10× größere Codebasis konsistent weiterentwickeln soll. Der zentrale
Denkfehler, den dieser Abschnitt vermeidet: **„wie es sein soll" gehört
*nie* in einen Vector-Store** — abgerufene Prosa driftet vom Code ab und
*Retrieval ≠ Compliance*. Stattdessen drei sauber getrennte Schichten:

| Schicht | Inhalt | Eigenschaft | Wo es lebt |
|---|---|---|---|
| **1 — Ist (deskriptiv)** | „Diese Funktion macht X, Modul A importiert B" | *aus Code regeneriert, per Konstruktion wahr* | AST-Index + Vector/FTS5 (`context-mode`) |
| **2 — Soll (normativ)** | „`billing/` darf `domains/*` nicht importieren; eine neue Domäne hat *diese* 5 Dateien" | *ausführbar, bricht den Build* | `import-linter` + Scaffold (Schritte 1–2) |
| **3 — Warum (Rationale)** | „warum Billing in-process, warum dieser Schnitt" | *Entscheidung statt Zustand → driftet nicht gleich* | `docs/adr/*` |

**Warum diese Trennung den Struktur↔Runtime-Gap löst:** Framework-Magie
(FastAPI `Depends`, SQLModel-Relations, Decorators, MCP-Registrierung)
erzeugt Laufzeit-Kanten, die in keinem AST stehen — auch nach dem Umbau
nicht. Aber Schicht 2 macht diese Verdrahtung *regulär* (jede Domäne
verdrahtet gleich), sodass der Gap auf **eine erzwungene Konvention**
kollabiert statt offener Analyse zu bedürfen. *Danach* kann Schicht 1 ihn
treu indizieren, weil er ein stabiles, immer gleiches Pattern ist.

### Schicht 1 — `context-mode` (vorhanden, nicht neu bauen)

`context-mode` ist installiert (FTS5, Bun-Runtime, AST-bewusstes Chunking).
Es ersetzt eine Eigenbau-tree-sitter+FAISS-Lösung vollständig.

- `ctx_search` ist der **primäre** Weg, Code zu finden (statt blindes
  `grep`/Datei-Lesen) — in `ARCHITECTURE.md`/`CLAUDE.md` als Konvention,
  Onboarding-Schritt „Repo indizieren" im Runbook.
- `.contextignore`: `generated_pdfs/`, `.venv/`, `archive/`,
  `static/brand/`, `__pycache__/`.
- Jedes `domains/<x>/`-Paket bekommt einen Modul-Docstring (Zweck,
  Entry-Points) → selbsterklärende AST-Chunks (entsteht in Schritt 2).
- **Akzeptanz:** „Wo wird VAT berechnet?" / „Wer ruft `finalize_invoice`?"
  → relevante Domäne in *einer* Suche.

> Index ist *regeneriert*, also per Konstruktion driftfrei — der einzig
> sichere Inhalt für einen Vector-/FTS-Store.

### Schicht 2 — Soll als ausführbarer Zwang (Kern der Konsistenz)

Kein deskriptiver, eingecheckter Call-Graph (`build_graph.py` aus Rev. 1
**gestrichen**): ein statischer Aufruf-Graph in framework-schwerem
dynamischem Python ist genau an den interessanten Kanten unvollständig und
*selbstbewusst falsch* — schlechter als keiner. Der „Graph", der sich
auszahlt, ist ein **Constraint**, kein Report:

- **`import-linter`-Contracts** = die erlaubten Kanten als Config (der
  Graph *ist* die Regel). Bricht den Build bei Verletzung. Billing-Regel
  ab Schritt 1, vollständige Kantenmenge ab Schritt 5/7.
- **Scaffold-Generator** = das Muster ist generierbar, nicht „beschrieben".
- **Impact-Fragen** („was bricht, wenn ich X ändere") nicht aus statischem
  `ast`, sondern zur Query-Zeit über LSP — kein rottendes Artefakt
  (operationalisiert s. u.).

**Vollständige Contract-Kantenmenge** (das eigentliche „Soll"; Ziel-Zustand
ab Schritt 7, schrittweise schärfer ab Schritt 1). `→` = „darf importieren":

| Quelle | erlaubt → | verboten |
|---|---|---|
| `interfaces/*` | `domains/*/router`, `domains/*/service`, `domains/*/schemas`, `core/*`, `shared/*` | `domains/*/models` (kein Modell-Zugriff aus Interfaces), `domains/*/repository` |
| `interfaces/mcp` | wie oben | **Konstruktion von Domänen-Modellen** (kein `Lead(...)` etc. — verhindert MCP-Logik-Duplikat) |
| `domains/<x>/*` | `core/*`, `shared/*`, eigenes `domains/<x>/*` | **anderes** `domains/<y>/*` (Cross-Domain nur über `contracts/`) |
| `domains/billing/*` | `core/*`, `shared/*`, `contracts/billing_order`, eigenes `billing/*` | **jedes** `domains/*` **und** `models` (härteste Regel; = Punkt 2a der Verifikation) |
| `core/*` | `core/*`, stdlib/3rd-party | `domains/*`, `interfaces/*`, `contracts/*` (Kern kennt keine Domäne) |
| `shared/*` | `core/*`, stdlib/3rd-party | `domains/*`, `interfaces/*` |
| `contracts/*` | stdlib/pydantic | `domains/*`, `core/*`, `interfaces/*` (reines DTO, abhängigkeitsfrei) |

Bis ein Paket existiert, ist seine Regel inaktiv; jeder Migrationsschritt
*aktiviert* die zu ihm gehörige Kante (Schritt 5 schärft die
`billing/`-Zeile, Schritt 7 die `interfaces/mcp`-Zeile). Endzustand =
gesamte Tabelle grün.

**LSP-Pfad operationalisiert** (Ersatz für den gelöschten Call-Graph): In
Schritt 1 wird `pyright` ohnehin als Type-Checker eingeführt — derselbe
Server liefert „find references"/„call hierarchy". Verankert als
`make whocalls SYMBOL=...` (dünner `pyright --outputjson`-Wrapper) und im
Agent-Edit-Protokoll als Standardweg für „was bricht, wenn ich X ändere".
Damit ist die Probe-Frage „**wer ruft `finalize_invoice`?**" konkret
beantwortbar — `ctx_search` (Schicht 1) lokalisiert, `make whocalls`
zählt die Aufrufer auf —, ohne eingecheckten, rottenden Graphen.

### Schicht 3 — ADRs

`docs/adr/*` halten *Entscheidungen* fest (warum), nicht *Zustand* —
deshalb als Text unkritisch (driftet nicht wie eine Zustandsbeschreibung).
Import-Linter-Regeln verweisen auf die begründende ADR.

### Vektor-Suche bleibt Code-Ebene

Kein `pgvector`/Embedding-Feld in Produkt-Tabellen — semantische *Code*-
Suche deckt `context-mode` (Schicht 1) ab. **Upgrade-Pfad (nur bei Bedarf):**
Sollte der Index `context-mode` entwachsen, eigener Embedding-Index über
`app/` + dokumentierende ADR. Bis dahin nicht bauen.

## Agent-Edit-Protokoll (in CLAUDE.md/AGENTS.md verankert, Schritt 0)

Damit „immer im selben Stil" gilt, ist *der* Edit-Loop explizit und vom
Scaffold gedeckt:

1. Domäne via `ctx_search` finden (Schicht 1).
2. **Tie-Break (der eigentliche Random-File-Schutz):**
   - Genau eine bestehende Domäne passt → dort editieren.
   - **Keine** passt → es ist eine neue Domäne → `make new-domain X`.
   - Mehrere/Cross-Domain → Logik bleibt je in ihrer Domäne;
     Datenfluss **nur über `contracts/`**, nie Domäne→Domäne direkt.
3. Editier-Reihenfolge in der Domäne:
   `models → schemas → service → router → test`.
4. `make verify` (= `ruff` + `mypy` + `pytest` + `import-linter`) grün.

Der Loop ist die *Dokumentation des ausführbaren Dings*, keine parallele
Beschreibung — single source.

## Wiederverwendbarkeit

- **Domänenpakete sind ausschneidbar** (eigenes models/service/router) →
  Vorlage für weitere Brands/Mandanten; knüpft an die README-Roadmap
  „Brand-Konfiguration via ENV/DB" an.
- **`core/`** (config, db, security, errors, logging, ai) = wiederverwend-
  barer Kern für künftige Services im selben Stil.
- **Scaffold + `import-linter`-Contracts + `.contextignore`** als
  wiederverwendbares Muster über Repos hinweg.

## Verifikation dieses Plans

1. **Faktencheck** gegen `ARCHITECTURE.md`: alle Zahlen mit `wc -l`/`grep`
   belegt (14 Tabellen, 72 Endpoints, 16 MCP-Tools, 6 getenv-Sites); ab
   Schritt 0 als CI-Assertion erzwungen
   (`scripts/check_architecture_metrics.py`).
2. **Reihenfolge** ist risiko-aufsteigend; Invoicing-Code wird verschoben,
   nie umgeschrieben; Char-Tests (0.5) sichern die untesteten Bruchstellen
   *vor* der Extraktion.
2a. **Billing-Grenze prüfbar:** import-linter-Regel „`billing/` importiert
   nichts aus `domains/*`/`models`"; `BillingOrder` trägt alle Felder, die
   `_snapshot_customer()` + `IssuerProfile`-Read heute liefern (Abgleich
   gegen die in `ARCHITECTURE.md` dokumentierte Naht).
3. **Outcome-Metrik (das eigentliche Ziel, nicht nur Plan-Konsistenz).**
   5 repräsentative Aufgaben: Feld an `Lead`, neues MCP-Tool, neue
   VAT-Regel, neuer API-Endpoint, neue Domäne.
   - **Versiegelte Vorhersage:** Die erwartete Dateiliste + Reihenfolge
     wird *vor* dem Lauf eingecheckt (`docs/outcome-probe/*.expected`) —
     sonst ist „vorhergesagt" im Nachhinein wegrationalisierbar.
   - **Schwelle:** je Aufgabe `N = 3` unabhängige Läufe; Bestehen =
     **3/3** treffen genau das versiegelte Datei-Set (keine Extra-Datei),
     `make verify` jedes Mal grün.
   - **Wann:** *Baseline jetzt* (zeigt den Ist-Schmerz, motiviert) und
     **erneut als Gate nach Schritt 7** (Paketgrenzen stehen). Differenz
     Baseline→nachher = der gemessene Nutzen des Umbaus, nicht die
     Schönheit eines Diagramms.
4. **Gate:** Umsetzung startet erst nach Freigabe; danach PR-für-PR entlang
   des Migrationspfads, CI (inkl. import-linter) grün als Bedingung.
