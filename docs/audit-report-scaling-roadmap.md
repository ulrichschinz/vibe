# Audit-Report — Scaling-Roadmap-Umsetzung (adversarial)

> Auditor-Modus: Widerlegung, nicht Bestätigung. Belege gegen Code/CI/Config,
> Stand `main` @ `5258d30`. „Nicht verifizierbar" wird als Risiko gewertet.
> Datum 2026-05-19.

---

## 1. Urteil (ein Satz je Achse)

- **(a) Korrekt umgesetzt — JA, mit Einschränkung.** Schritte 0–9 sind je
  ein gemergter PR (#1–#16), die *aktivierten* `import-linter`-Contracts,
  Makefile-Gate, Alembic-Bäume und der Scaffold existieren und sind
  mechanisch funktionsfähig (Scaffold-Probe lief hier, Exit 0, exakt 7
  Dateien). Stärkster Gegenbeleg: mehrere Akzeptanz-Aussagen sind
  CI-„grün-ohne-lokalen-Lauf" und damit nie unabhängig reproduziert.
- **(b) Vollständig umgesetzt — NEIN.** Die plan-eigene
  **Outcome-Metrik** (Roadmap „Verifikation" §3: `docs/outcome-probe/*.expected`,
  versiegelte Vorhersagen, Baseline jetzt, Gate erneut nach Schritt 7,
  N=3, 3/3) wurde **vollständig übersprungen** — `docs/outcome-probe/`
  existiert nicht (`ls` → „No such file or directory"). Das ist nicht
  „deferred", es ist die *Wirksamkeitsverifikation selbst*.
- **(c) Zielwirksam (Agent-Konsistenz + Skalierung) — TEILWEISE/NEIN.** Die
  zentrale Anti-Pattern-Sperre („Interfaces konstruieren keine Modelle",
  „eine Logik, drei Clients") ist für die **größte** Oberfläche (alle
  CRUD-Web/REST-Handler) **nicht erzwungen** — sie ist für genau diese
  Fläche weiterhin Prosa. Stärkster Gegenbeleg: 6 Modell-Konstruktions-
  Sites in `app/interfaces/**` bei grünem Build (s. Risiko R1).

---

## 2. Risiko-Register

### R1 — Zentrale Anti-Pattern-Sperre für Web/REST nicht erzwungen — **HOCH**
Die Kantentabelle (CLAUDE.md / Roadmap) fordert `interfaces/* ↛
domains/*/models`. Aktiv in `pyproject.toml` sind nur **4** Contracts:
`services.invoicing`-forbidden, `services.mcp_server`-forbidden,
`app.core`-forbidden, `domains`-independence. Die `interfaces`-Modellsperre
ist **nicht** darunter (ADR-009 §G: bewusst deferred, „churn owned by no
step").
Beleg gegen Code (grep, grüner Build):
- `app/interfaces/web/leads.py:281` `lead = Lead(`
- `app/interfaces/web/leads.py:502` `note = Note(`
- `app/interfaces/web/invoices.py:133` `inv = Invoice(`
- `app/interfaces/web/admin.py:72` `user = User(`
- `app/interfaces/api/router.py:89` `lead = Lead(`
- `app/interfaces/api/router.py:238` `inv = Invoice(`
**Bricht wann:** nie. Ein Agent, der Logik/Modellbau in einen Web/REST-
Handler legt, ist *im Einklang mit dem Bestand* und CI bleibt grün. „Eine
Logik, drei Clients" ist nur für *einen* Client (MCP) erzwungen — asymmetrisch.
„Churn owned by no step" ist hier ein Euphemismus für „nie": kein Schritt
0–9 besitzt diese Kante, kein numerierter Folgeschritt existiert.

### R2 — Permanente Shims = die Ambiguität, die der Plan abschaffen wollte — **HOCH**
Vier „Zwei-Häuser"-Situationen, keine mit terminierendem numerierten Schritt:
1. `models.py` — Test-facing Re-Export + Aggregator. Die Roadmap
   spezifizierte explizit ein **„Shim-Sterbe-Gate"** (import-linter „nichts
   importiert mehr aus Top-Level-`models`", aktiviert *im selben PR*, der
   den letzten Aufrufer migriert; *dann* Löschung — „Ohne dieses Gate
   bleibt der Shim dauerhaft = zwei Churn-Events"). Letzter Prod-Aufrufer
   wurde in Schritt 8 migriert — **Gate nicht aktiviert, Datei nicht
   gelöscht**. Der Plan ist hier an seinem eigenen Kriterium gescheitert.
2. `services/ai.py` — Re-Export-Shim + frozen Monkeypatch-Seam.
3. `services/linkedin_import.py` — dito.
4. `services/mcp_server.py` (363 LOC) — bleibt physisch (frozen `m.engine`
   Seam, ADR-009 §B); ist der `source_modules`-Anker der MCP-Regel.
characterization-map: deren Tod ist „ein eigener Folgeschritt" — **nicht in
0–9, nicht numeriert**. De facto permanent. Jeder = zwei plausible
Importorte (`from models import Lead` vs `from app.domains.leads.models`;
`services.ai` vs `app.core.ai`; MCP-Logik in `services/mcp_server.py` vs
`app/domains/*/service.py`). **Bricht wann:** beim nächsten Agenten, der
„welcher Ort ist richtig?" entscheiden muss — exakt der abgeschaffte Zustand.

### R3 — Schema-Evolution nach der Baseline ist *erhofft, nicht erzwungen* — **HOCH**
`tests/conftest.py:36-38` ruft weiterhin direkt
`SQLModel.metadata.create_all(eng)` + `install_lead_invoice_columns` +
`install_invoice_triggers`. Kein Test durchläuft `run_migrations`/Alembic
(`grep -rln run_migrations tests/` → leer). Es gibt **kein Gate**, das einen
Entwickler zwingt, eine Alembic-Revision zu schreiben statt nur ein Modell
zu ändern: Tests sehen das neue Modell via `create_all`, Doc-Gate zählt nur
die Tabellenzahl (`m_tables`), nicht „Modelländerung ohne Migration". „Danach
keine impliziten `create_all`-Änderungen mehr" (Roadmap-Auftrag, ADR-010
Kontext) ist damit **unerzwungen**.
**Bricht wann:** beim ersten echten Schema-Change nach Baseline — Prod
(Alembic) und Tests (`create_all`) driften lautlos auseinander; Prod-Start
erstellt nur die in `db_migrate.CRM_TABLES`/`BILLING_TABLES` *aufgezählten*
Tabellen, eine neue Tabelle ohne Partitionseintrag wird in Prod **gar nicht
angelegt**, in Tests schon → grün im CI, kaputt im Deploy.

### R4 — Partitions-Drift CRM/Billing wird von nichts gefangen — **HOCH**
`CRM_TABLES`/`BILLING_TABLES` in `app/core/db_migrate.py:46-62` sind
hartkodierte String-Tupel. `tests/test_models_split.py:41,50` prüft nur
`set(SQLModel.metadata.tables) == EXPECTED_TABLES`, **nicht**
`set(CRM_TABLES) | set(BILLING_TABLES) == set(metadata.tables)`. Wer ein
Modell der falschen Partition zuordnet (oder vergisst), landet im falschen
Versionsbaum — genau das, was den „DB-Split ohne Daten-Migration"
ad absurdum führt — und **kein Gate bemerkt es**.
**Bricht wann:** beim Stage-B-Split; der Fehler ist dann Monate alt.

### R5 — Doc-Gate prüft Zahlen, nicht Struktur — **MITTEL**
`scripts/check_architecture_metrics.py` asserted 10 numerische Kennzahlen.
Es asserted **nicht**: Contract-Menge, Schichtkanten, Shim-Existenz,
Partitions-Vollständigkeit, „wer konstruiert Modelle". Konkretes
Drift-Szenario, das durch *alle* Gates käme: jemand löscht den
`app.core`-forbidden-Contract aus `pyproject.toml` und ARCHITECTURE.md
behauptet weiter „core ↛ domains erzwungen" — `import-linter` prüft die
gelöschte Regel nicht, Doc-Gate zählt nur Zahlen (unverändert),
`make verify` bleibt grün. Struktur-Prosa in ARCHITECTURE.md/CLAUDE.md ist
nicht selbst-verifizierend.

### R6 — Neue Domäne hat NULL Cross-Domain-Enforcement — **MITTEL**
Scaffold-Probe hier ausgeführt: `python3 scripts/new_domain.py
contracts_smoke` → Exit 0, 7 Dateien. `grep -c contracts_smoke
pyproject.toml` → **0**. Der `independence`-Contract hartkodiert nur
`app.domains.{leads,proposals,billing}` (`pyproject.toml:253-257`). Eine
frisch gescaffoldete 4. Domäne ist in **keinem** Contract → sie darf
`app.domains.billing` direkt importieren, Build bleibt grün. Der Scaffold
„patcht keine zentrale Registry" — *einschließlich* der import-linter-
Regel. Die Anti-„random files"-Sperre erweitert sich **nicht** automatisch
auf neue Domänen; sie muss manuell in `pyproject.toml` nachgezogen werden
(= genau der zentrale Eingriff, den der Scaffold-Vertrag zu vermeiden vorgibt).

### R7 — `contracts ↛ domains/core/interfaces` (pure DTO) nicht aktiv — **NIEDRIG**
Kein Contract nennt `app.contracts` als `source_modules`.
`app/contracts/billing_order.py` importiert heute nur stdlib+pydantic
(grep-sauber), aber nichts *erzwingt* das. Niedrig, weil eine Datei, klein —
aber es ist eine weitere „erhofft statt erzwungen"-Kante.

### R8 — „Neue Soll-Fläche ist strict" hat große Ausnahmen — **MITTEL**
`pyproject.toml`: `app.interfaces.*` → `mypy ignore_errors`; `services.*`
→ `ignore_errors`; `app/interfaces/*` → ruff `E712,E741` ignoriert.
Die *größten* Module sind genau die ungeprüften: `web/leads.py` 533 LOC,
`web/invoices.py` **481** LOC (Prompt schätzte ~441 — real größer),
`api/router.py` 385, `core/ai.py` 305 mit dem **verbatim** verschobenen
`===MARKER===`-Regex (`app/core/ai.py:141`) + `<json>`-Regex (`:219`).
Schuld 6 ist isoliert, nicht bezahlt. „Move-not-rewrite" akkumuliert
strukturell verschobene, ungetypte, fragile Schuld in den dicksten Dateien.

---

## 3. Übersprungen vs. bewusst deferred

**Übersprungen (Roadmap *fordert*, geschah nicht):**
- **`docs/outcome-probe/` komplett — die zentrale Wirksamkeits-Verifikation.**
  Roadmap „Verifikation" §3 fordert versiegelte `*.expected`-Dateien,
  Baseline-Messung *jetzt* (zur Motivation), Gate erneut *nach Schritt 7*,
  N=3, Bestehen=3/3. Nichts davon existiert. Damit ist „der Plan wirkt
  konsistent" **unbelegt**; verifiziert ist nur „der Plan ist konsistent
  gebaut". Höchste Schwere — es ist der vom Plan selbst definierte Beweis.
- **Shim-Sterbe-Gate für `models.py`** (Roadmap Schritt-4/Migrationspfad,
  explizit „im selben PR" des letzten Aufrufers). Letzter Aufrufer in
  Schritt 8 migriert, Gate nie aktiviert → exakt das vom Plan benannte
  Failure („zwei Churn-Events").

**Bewusst deferred + begründet (ADR-009 §G, legitim als Entscheidung —
aber die *Wirkung* fehlt trotzdem):**
- `interfaces/* ↛ domains/*/models` (web/REST) — move-not-rewrite-Begründung.
- `shared ↛ domains` — enum-keyed Labels, via `ignore_imports` neutralisiert.
- Tod von `services/ai.py` / `services/linkedin_import.py` (S6-Char-Lifecycle).
- Physische Relokation `services/mcp_server.py` → `app/interfaces/mcp`.
- Stage-B-DB-Split (optionaler Schritt 10, nur bei Trigger).

> Die Trennung ist sauber dokumentiert. Kritik: „bewusst deferred ohne
> terminierenden Schritt" ist operativ ununterscheidbar von „nie" — die
> deferred-Liste hat keinen einzigen numerierten Fälligkeitstermin.

---

## 4. Punch-List (ausführbare Gates, priorisiert)

1. **Outcome-Probe nachholen (P0).** `docs/outcome-probe/{lead-field,
   mcp-tool,vat-rule,api-endpoint,new-domain}.expected` einchecken
   (versiegelte Dateilisten), CI-Job `outcome-probe.yml`: führt die 5
   Aufgaben skriptgesteuert N=3, diff gegen `.expected`, `make verify` je
   Lauf — rot bei ≠ exaktem Set. Ohne das bleibt die Kern-These unbelegt.
2. **Web/REST-Modellsperre aktivieren (P0).** `[[contracts]]` forbidden
   `source_modules=["app.interfaces"]`, `forbidden=["app.domains.*.models"]`,
   `allow_indirect_imports=True` — nach Refactor der 6 R1-Sites in
   `service.py`. Macht „Interfaces konstruieren keine Modelle" *erzwungen*.
3. **Partitions-Vollständigkeits-Test (P0, billig).**
   `tests/test_db_partition.py`: `assert set(CRM_TABLES)|set(BILLING_TABLES)
   == set(SQLModel.metadata.tables)`. Schließt R4 in einem Test.
4. **Alembic-Pfad testen (P1).** Eine e2e/integration-Fixture, die statt
   `create_all` `app.core.db_migrate.run_migrations(engine)` fährt und das
   resultierende Schema mit dem `create_all`-Schema vergleicht (Schema-
   Snapshot-Diff) — macht „byte-gleich" *geprüft* statt tautologisch und
   fängt künftige Revisions-Drift. Schließt R3.
5. **Scaffold patcht Independence-Contract (P1).** `new_domain.py` fügt die
   neue Domäne dem `independence`-`modules`-Array in `pyproject.toml` hinzu
   (idempotent), + Scaffold-Smoke prüft `grep -q <name> pyproject.toml`.
   Schließt R6 — Enforcement skaliert dann mit den Domänen.
6. **Struktur-Assertions ins Doc-Gate (P2).** `check_architecture_metrics.py`
   erweitern: erwartete Contract-Namen-Menge + Shim-Inventar (Pfad-Existenz)
   gegen ARCHITECTURE.md-Tabelle assert. Schließt R5.
7. **Shim-Sterbe-Gate + numerierter Folgeschritt (P2).** Für jeden der 4
   Shims einen datierten Schritt mit aktivierungsfähigem import-linter-Gate;
   ohne Termin bleibt R2 strukturell.

---

## 5. Teil C — Skaliert es „virtuell unendlich"? (Decken)

- **Laufzeit ≠ Code-Organisation.** Der Plan adressiert *ausschließlich*
  Code-Navigierbarkeit. Single-Process, synchrone SQLModel-Sessions,
  SQLite single-writer (WAL + `BEGIN IMMEDIATE`). Bei 5–10× Last bricht
  *zuerst* der SQLite-Single-Writer (Schreib-Serialisierung), dann der
  synchrone Request-Pfad (Thread-Pool-Sättigung bei WeasyPrint-PDF /
  Anthropic-Calls im Handler). „Skaliert" ist nur ehrlich als „bleibt für
  einen Agenten lesbar" — *nicht* als Laufzeit. Beide Aussagen sauber
  getrennt: die Roadmap behauptet nur erstere; das Memory-Wort „skaliert"
  ist überdehnt.
- **Skaliert die Konsistenz-Mechanik selbst? Nein, ohne Pflege.** Schon
  jetzt: 1 `ignore_imports`-Pflaster (shared.labels→domains), 3
  `ignore_errors`-mypy-Blöcke, 2 ruff-per-file-ignores, 1
  `allow_indirect_imports`. Jede deferred Kante = ein Loch, das mit der
  Codebasis wächst. Auto-Discovery (`pkgutil.iter_modules`) skaliert
  technisch auf 50 Domänen, aber der `independence`-Contract ist
  hartkodiert (R6) — neue Engstelle: `pyproject.toml` wird die zentrale
  Registry, die der Scaffold zu vermeiden vorgibt.
- **Move-not-rewrite bei 80k LOC.** Bei 8k LOC + 90 %-Invoicing-Netz
  risikoarm. Skaliert nicht als Prinzip: ungetypte, fragile Module
  (`===MARKER===`-Parser, 481-LOC-`invoices.py`) werden bei N× Größe
  zementiert, nicht abgebaut — „verschiebe, schreibe nie um" + „Cleanup
  owned by no step" = dauerhafte Altlast per Konstruktion.
- **Bounded-Context-Versprechen unter Stress.** „DB-Split = nur Deploy"
  ist optimistisch: versteckte Kopplung bleibt — geteilte `engine`/
  `get_session` (`app/core/db.py`), Soft-FK `Invoice.lead_id` (kein SQL-
  Constraint, aber Lese-Annahme), geteilte `app.core.*`, Test-Fixtures
  (`conftest`) über die Netzgrenze, und `models.py` registriert *alle* 13
  Tabellen auf *einer* `SQLModel.metadata`. Getrennte Versionsbäume lösen
  *Migrations*-Historie — nicht die Laufzeitkopplung. Der Split ist
  „kein Daten-Rewrite", aber sehr wohl ein Code-Rewrite an diesen Nähten.

---

## Fazit ohne Höflichkeit

Der Umbau ist *handwerklich solide gebaut und dokumentiert* — aber an drei
Stellen ist das Versprechen **behauptet, nicht erzwungen**: (1) die
Wirksamkeits-Verifikation (Outcome-Probe) wurde übersprungen; (2) die
zentrale Modellsperre fehlt für die größte Oberfläche; (3) Schema-Evolution,
Partitions-Integrität und neue-Domäne-Isolation hängen an Disziplin, nicht
an Gates. „Der Agent legt Code nicht random ab" gilt heute erzwungen für
MCP und Cross-Domain *zwischen den drei Altdomänen* — für den Normalfall
(CRUD-Web/REST, neue Domäne) ist es weiterhin Prosa.
