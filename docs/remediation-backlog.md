# Remediation-Backlog — Scaling-Roadmap-Audit

> Begleitet [`audit-report-scaling-roadmap.md`](audit-report-scaling-roadmap.md)
> (Befund) und ist **bewusst getrennt** von `scaling-roadmap.md`.
>
> **Governance-Entscheidung (E2):** Die Roadmap bleibt **eingefroren
> (Rev. 2)** und ist der historische Record der Schritte 0–9 — *„wurde der
> Plan ausgeführt wie geschrieben?"* = ja. Diese Remediation ist ein
> **separater Track**, kein Rev. 3, damit *„Plan ausgeführt"* nicht mit
> *„Plan nachträglich gepatcht"* vermischt wird. Das ist exakt die
> Trennung, die das Audit eingefordert hat. Memory-Pointer:
> `scaling-roadmap-progress`.
>
> Status: **offen**, Auftrag erteilt für T3 (umgesetzt in diesem PR).
> Datum 2026-05-19.

---

## Entscheidung E1 — Move-not-rewrite-Decke: **akzeptiert mit Trigger**

Schuld 6 (`===MARKER===`-Proposal-Parser + `<json>`-LinkedIn-Parser,
`app/core/ai.py:141` / `:219`) und die `mypy ignore_errors`-Ausnahmen für
die dicksten verschobenen Module (`app/interfaces/web/invoices.py` 481 LOC,
`web/leads.py` 533 LOC) werden **bewusst dauerhaft akzeptiert** — **kein**
numerierter Abbau-Schritt (= kein T8).

Begründung: Move-not-rewrite war *richtig* (Compliance-Risikokontrolle
während der Migration); die Migration ist durch. Schuld 6 ist real fragil,
aber **isoliert und charakterisiert** (Char-/Unit-Tests pinnen das
Verhalten). Ein Rewrite ist eine normale Produktqualitäts-Aufgabe, ausgelöst
durch echten Bedarf — nicht durch ein Audit. Bei ~8k LOC wäre ein
Abbau-Schritt Over-Engineering.

**Revisit-Trigger (explizit, damit die Entscheidung bewusst statt implizit
ist):** Schuld 6 wird neu bewertet, sobald **eines** eintritt:
1. ein Proposal-Draft- oder LinkedIn-Import-Parse-Fehler tritt in Prod auf, ODER
2. das verwendete AI-Modell ändert sein Ausgabeformat (Marker/JSON-Block), ODER
3. die Codebasis überschreitet ~25k Produktiv-LOC (dann skaliert der Wert
   von Typisierung/robustem Parsing über die Kosten).

Bis dahin: nicht anfassen. Diese Zeile *ist* die Entscheidung.

---

## Todo-Register (T1–T7) — jedes als ausführbares Gate

Reihenfolge nach Wert: **T1** (Kern-These) und **T2** (größter
Strukturhebel) zählen wirklich; **T3** ist der schnellste Gewinn.
Abhängigkeitskette: T3 sofort → T1 + T2a parallel → T2b nach T2a; T4/T5
parallel → T6/T7.

### T1 — Outcome-Probe nachholen — **P0** — ✅ etabliert + 2/5 empirisch validiert (2026-05-19)

**Status:** Infrastruktur steht und ist lokal beweisbar.
`docs/outcome-probe/` angelegt: `README.md` (Spec/Methodik/ehrliche
Grenzen), 5 versiegelte `*.expected` (vor jedem Lauf committed),
`BASELINE.md` (Baseline `4aa4f9a` + Delta — größter Nutzen bei
`new-domain`/`lead-field`, ~kein Nutzen bei `vat-rule`, ehrlich),
`RESULTS.md`. Harness `scripts/outcome_probe.py` (reine stdlib, lokal
lauffähig wie der Doc-Gate), `make outcome-probe TASK=x`, CI-Gate
`outcome-probe.yml` (Wohlgeformtheit). **Validierungslauf N=1:**
`new-domain` 8/8 **exakt**, `lead-field` 7/7 **exakt** (sealed nach
Ergebnis NICHT geändert). Verbleibend (CI/manuell, no-local-interp,
prozessual — kein Blocker des Track): volle N=3 × 5 mit `make verify`
grün; `mcp-tool`/`vat-rule`/`api-endpoint` empirisch. Die Probe
*quantifiziert* zugleich R1/R3/R6 (exakt-getroffen ≠ vollständig/erzwungen
— s. `.expected`-Annotationen). Detail unten = ursprüngliche Spezifikation.



Roadmap „Verifikation" §3 wurde nie ausgeführt (`docs/outcome-probe/`
existiert nicht). ~90 % rettbar: Baseline ist über Git rekonstruierbar.

**Gate:**
- `docs/outcome-probe/{lead-field,mcp-tool,vat-rule,api-endpoint,new-domain}.expected`
  — versiegelte erwartete Dateiliste + Reihenfolge, **vor** dem Lauf committed.
- Baseline: `git checkout 4aa4f9a` (letzter Commit vor Schritt 0), die 5
  Aufgaben dort manuell vermessen → Datei-Streuung = Baseline (Differenz =
  gemessener Nutzen; ehrlich dokumentieren, dass „zum Zeitpunkt versiegelt"
  für die Baseline nicht mehr gilt — nur das *Nachher* ist sealebar).
- CI-Job `outcome-probe.yml`: je Aufgabe N=3 unabhängige Läufe, Diff gegen
  `.expected`, `make verify` jeder Lauf grün. Bestehen = 3/3 exaktes Set,
  keine Extra-Datei.

### T2 — Web/REST-Modellsperre — **P0** — schließt R1, liefert „eine Logik, drei Clients"

Zweistufig; **T2a blockt T2b**.

**T2a (Refactor, Bestand):** Modell-Konstruktion aus `app/interfaces/web/*`
+ `app/interfaces/api/router.py` in die jeweiligen `app/domains/*/service.py`
umleiten. Bekannte Sites (nicht abschließend — vor Umsetzung volle
grep-Inventur): `web/leads.py:281,502`, `web/invoices.py:133`,
`web/admin.py:72`, `api/router.py:89,238`. Vieles existiert schon
(Schritt 6–8 baute die Service-Schicht via MCP-Entdopplung; Web-Handler nur
nie umgebogen). Sonderfall `User(...)` hat keine Domäne → Zuhause klären
(`app/core/identity`-Service oder Admin-Service). **Invariante:** 132
Char-Tests + 90 %-Invoicing 0-Diff.

> **Scope-Nachschärfung (2026-05-19, vor Umsetzung — Plan-Befund):** „nur
> Konstruktion umleiten" reicht **nicht**, damit T2b grün aktiviert. Der
> Gate verbietet jeden *direkten* Import von
> `app.domains.{leads,proposals,billing}.models` aus `app.interfaces` —
> dieselben 4 Dateien importieren die Modelle auch für Queries
> (`select(Lead)`, `session.get(Invoice, …)`), Enums (`LeadStage`,
> `InvoiceStatus`, `LeadType(...)`) und Jinja-Globals
> (`env.globals["LeadStage"]`). T2a ist daher die **volle Read-/Enum-/
> Template-Flächen-Verschiebung** der 4 Interface-Dateien hinter ihre
> Services — exakt das Schritt-7-MCP-Entdopplungs-Muster auf Web/REST
> angewandt (move-not-rewrite, byte-äquivalent, Enum-Re-Exports über das
> Service-Modul). Die 12 Konstruktions-Sites sind die *Saat*, nicht der
> Gesamtumfang. Zusätzlich (Spec „Zuhause klären", voller Scope):
> `User`/`ApiKey`/`AiSettings`-Konstruktion → neue `app/core/
> {identity,ai_settings}_service.py` (nicht gate-erzwungen — `core` ist
> keine Domäne —, aber R1-Symmetrie; `core ↛ services/domains`: Hashing
> bleibt im Handler). Entscheidung des Maintainers: voller Move + Gate.

**T2b (Gate):** `[[tool.importlinter.contracts]]` forbidden,
`source_modules=["app.interfaces"]`,
`forbidden_modules=["app.domains.leads.models","app.domains.proposals.models","app.domains.billing.models"]`,
`allow_indirect_imports="True"` (gleiche Subtilität wie die MCP-Regel:
direkter Modell-Import verboten, intra-domain `service→models` erlaubt).

### T3 — Partitions-Vollständigkeits-Test — **P0** — schließt R4 — ✅ umgesetzt 2026-05-19

`tests/test_db_partition.py`: `set(CRM_TABLES) | set(BILLING_TABLES) ==
set(SQLModel.metadata.tables)` **und** Disjunktheit der beiden Partitionen.
Fängt: ein Modell der falschen/keiner Partition landet im falschen
Versionsbaum → lautloser Prod-Bruch beim DB-Split. ~15 Zeilen, keine
Abhängigkeit, läuft in `make test-fast`.

### T4 — Alembic-Pfad real prüfen — **P1** — schließt R3

**T4a (billig):** Fixture fährt `app.core.db_migrate.run_migrations(engine)`
vs. `SQLModel.metadata.create_all`, vergleicht `sqlite_master` + `PRAGMA
table_info`/`index_list` → macht „byte-gleich" *geprüft* statt tautologisch
und fängt künftige Revisions-Drift. Heute: **0** Tests fahren `run_migrations`.

**T4b (mittel):** mindestens die e2e-Suite durch `run_migrations` statt
`create_all` (conftest-Fixture), damit der Alembic-Pfad von Tests überhaupt
ausgeübt wird.

### T5 — Scaffold patcht den Independence-Contract — **P1** — schließt R6

`scripts/new_domain.py` trägt die neue Domäne idempotent ins
`independence`-`modules`-Array in `pyproject.toml` ein; CI-Scaffold-Smoke
(`test.yml`) prüft `grep -q "app.domains.<name>" pyproject.toml`. Damit
skaliert Cross-Domain-Enforcement mit den Domänen statt an einem manuellen
zentralen Eingriff zu hängen. (Befund: gescaffoldete 4. Domäne ist in **0**
Contracts.)

### T6 — Struktur-Assertions ins Doc-Gate — **P2** — schließt R5

`scripts/check_architecture_metrics.py` erweitern: erwartete
import-linter-Contract-Namen-Menge + Shim-Pfad-Inventar gegen eine neue
ARCHITECTURE.md-Tabelle assert. Macht Struktur-Prosa selbst-verifizierend
(heute driftbar ohne CI-Rot).

### T7 — Shim-Sterbe-Gates — **P2** — schließt R2 strukturell

Je ein PR mit aktivierendem import-linter-Gate für: `models.py` (nichts
importiert mehr Top-Level-`models` → löschen — das vom Plan selbst
spezifizierte, nie aktivierte „Shim-Sterbe-Gate"), `services.ai` /
`services.linkedin_import` (Char-Test-Lifecycle-Swap → löschen),
`services.mcp_server` → `app/interfaces/mcp` relozieren. Niedrigste
Dringlichkeit bei aktueller Größe; Wert skaliert mit LOC.

---

## Nicht-Todos (bewusst, mit Begründung)

- **T8 „Schuld abbauen"** — existiert nicht (E1: akzeptiert mit Trigger).
- **Laufzeit-Skalierung** (SQLite single-writer, sync Sessions) — der Plan
  adressierte nur Code-Navigierbarkeit; das ist ein eigenes, separates
  Thema, kein Roadmap-Remediation-Item. Bei Lastbedarf neu aufmachen.
