# ADR-010: Alembic — zwei getrennt versionierte Bäume (Schritt 9)

**Status:** Akzeptiert (2026-05-19)

## Kontext

Schritt 9 von `docs/scaling-roadmap.md` führt Alembic ein. Vorher etablierte
`database.create_db()` das Schema implizit über
`SQLModel.metadata.create_all` + additive `ALTER TABLE lead`-Spalten +
`CREATE TRIGGER`-Immutabilität beim App-Start. Roadmap-Auftrag wörtlich:
*Baseline-Migration = aktuelles Schema; CRM- und Billing-Schema **getrennt
versioniert** → ermöglicht späteren DB-Split ohne Daten-Migration; danach
keine impliziten `create_all`-Änderungen.* GoBD↔DSGVO-Trennung beachten;
`services/invoicing/` bleibt move-not-rewrite (90 %-Suite = Netz).

Randbedingung (S4–S8-Lektion): **kein lokaler Interpreter mit App-Deps** →
keine `--autogenerate`-Diffs lokal erzeugbar; Korrektheit ist CI-verifiziert.

## Entscheidungen

### A — Zwei Bäume, getrennte version_table (statt Branch-Labels)

`migrations/crm` und `migrations/billing` sind **eigenständige
script_locations** mit **eigener** `version_table`
(`alembic_version` bzw. `alembic_version_billing`) auf der heute
gemeinsamen SQLite-Datei. Bewusst **nicht** ein Baum mit Alembic-Branch-
Labels und gemeinsamer `alembic_version`: das eigentliche Roadmap-Ziel
(„DB-Split ohne Daten-Migration") verlangt **physisch entkoppelte
Historien** — wenn Billing später eigenes Deployable + eigene DB wird
(Bounded-Context Stufe B, ADR-007), trägt seine DB nur seine eigene
Versionszeile; keine geteilte `alembic_version` muss retroaktiv entwirrt
werden. Es ist zugleich die strukturelle Heimat der eigenen Billing-
**Aufbewahrungsregel** (GoBD): finalisierte Rechnungen ~10 J. unveränderbar,
unabhängig von der DSGVO-Löschbarkeit der Leads.

Die Tabellen-Partition (7 CRM/Kernel + 6 Billing = die 13 Tabellen der
Datenmodell-Sektion) lebt als reine `__tablename__`-**Strings** in
`app/core/db_migrate.py` — kein Modell-Import, damit der Schritt-8-Contract
`core ↛ domains/interfaces/contracts` grün bleibt.

### B — Baseline = altes Schema, per Delegation (kein Handschrieb)

`0001_*_baseline.py` schreibt **keine** ~13 `op.create_table`-Blöcke von
Hand (Drift-Risiko, ohne lokalen Interpreter nicht gegen-autogenerierbar).
Stattdessen delegiert `upgrade()` an genau den Schema-Builder, den die
Produktion vorher nutzte: `SQLModel.metadata.create_all(op.get_bind(),
tables=[…Domänen-Partition…])` + die **verbatim** aus `database.py`
geteilten Trigger-Statements / Lead-Spalten-Fragmente. Damit ist das
erfasste Schema **per Konstruktion byte-gleich** zum Pre-Schritt-9-
`create_all` — move-not-rewrite (auch die Invoicing-DDL wird nicht
umgeschrieben, nur in eine versionierte Baseline gewrappt). `database.py`
wurde nur **refaktoriert** (Trigger-/Spalten-SQL in geteilte Helfer
extrahiert — identische Bytes, Reihenfolge, Per-Statement-Swallow), damit
Legacy-`install_*` (von `tests/conftest.py` genutzt) und die Baselines aus
**einer** Quelle emittieren.

Alle DDL läuft auf **einer** Connection (`op.get_bind()`) — kein zweiter
Writer gegen die WAL/`BEGIN IMMEDIATE`-Engine. Idempotent: `create_all`
ist checkfirst, `CREATE TRIGGER IF NOT EXISTS` nativ idempotent, die
`ALTER`-Spalten introspektions-geguarded (reproduziert den Legacy-
try/except-Endzustand ohne die Migrations-Txn abzubrechen).

### C — Bindung an die Live-Engine (e2e-Naht erhalten)

`app.core.db_migrate.run_migrations(engine)` legt die **übergebene**
Engine auf `config.attributes["connection"]`; `env.py` nutzt diese statt
eine URL neu abzuleiten. Damit bleibt die e2e-Test-Isolation
(`monkeypatch` auf `database.engine`/`main.engine`, PR-#5-Lektion) exakt
erhalten — der Lifespan migriert die Per-Test-Engine, nicht die
konfigurierte Datei. CLI-Fallback (`alembic -n crm upgrade head`) baut die
Engine aus `app.core.config` (eine URL-Quelle; kein direkter Env-Read in
`env.py` — vermeidet Doppel-Config und den Doc-Gate-`getenv`-Substring-
False-Positive).

### D — Tests unverändert (frozen Netz 0-Diff)

`tests/conftest.py` und die unit/integration/characterization-Fixtures
rufen weiter **direkt** `create_all` + `install_*` — das ist *per
Definition* identisch zur 0001-Baseline, also keine Verhaltensänderung und
**0 `tests/`-Diff**. Nur Prod-Start **und** der e2e-Lifespan (`TestClient`
→ `create_db`) laufen jetzt durch Alembic; das Netto-Schema ist identisch
(Baseline delegiert an denselben `create_all`). Das ist die einzige,
charakterisiert-äquivalente Verhaltens*pfad*-Änderung in Schritt 9; die
132 Characterization-Tests und die 90 %-Invoicing-Suite bleiben 0-Diff
grün (kein Char-Lifecycle-Delete — `docs/characterization-map.md` ordnet
Schritt 9 keinen Char-Test zu).

### E — Scope / Gates

`migrations/` ist **kein** import-linter-`root_package` und **nicht** im
`mypy scripts app`- / `ruff`-Scope → die dynamischen Alembic-Muster und der
`database`/`models`-Reach der `env.py`/Baselines berühren **keinen**
Schritt-1..8-Contract. `app/core/db_migrate.py` ist `app.*`-strict +
ruff-clean (nur `alembic` + stdlib + übergebene Engine; keine Domänen-
Importe). `requirements.txt` += `alembic>=1.13,<2` (lockerer Pin, Repo-
Stil für Nicht-Kern-Deps; 1.13+ zielt auf das SQLAlchemy 2.x, das sqlmodel
zieht). Keine `pyproject.toml`-Regeländerung (Roadmap: Schritt 9 ist
Migrations-Einführung, keine Kantenaktivierung).

## Konsequenz / Akzeptanz-Gate

`make verify` grün (ruff + ruff-format + mypy + import-linter + test-fast
+ Doc-Gate) **und** 90 %-Invoicing-Suite grün **und** 132 Characterization-
Tests 0-Diff grün **und** e2e grün (Lifespan über Alembic, Schema
identisch) **und** ARCHITECTURE.md-Kennzahlen/Baum/Schichten/Schuld 5 +
CLAUDE.md-Statusbanner im selben PR. Lokal nur Doc-Gate verifizierbar
(stdlib); Test-/import-linter-Korrektheit CI-verifiziert (ohne lokalen
Interpreter mehrere Fix-Forward-Runden erwartbar — S8-Muster).

Spätere, keinem Schritt zugeordnete Folge-Arbeit (unverändert offen,
ADR-009): physischer Shim-Tod (`models.py`/`services.ai`/
`services.linkedin_import`/`services.mcp_server`) + Test-Import-Migration;
S6-AI/LinkedIn-Char-Lifecycle; `mcp_server`-Relokation; web/REST
`interfaces↛models`- + `shared↛domains`-Kanten. Optionale Stufe B
(Billing eigenes Deployable + eigene DB) wird durch die getrennten
Versionsbäume zur reinen Deploy-Entscheidung.
