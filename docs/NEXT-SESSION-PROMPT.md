# Fortsetzungs-Prompt — Audit-Remediation + Deploy-Sicherheits-Track

> Diesen Text als Start-Prompt einer frischen Session verwenden (Kontext
> wurde bewusst gelöscht). Single Sources of Truth sind die unten
> genannten Dateien + das persistente Memory `scaling-roadmap-progress` —
> denen vertrauen, nicht diesem Prompt paraphrasieren.

---

Du setzt einen Audit-Remediation- + Deploy-Sicherheits-Track in
`/Users/uli/projects/agentic-reach/vibe` fort. Vorgeschichte (alles
bereits passiert, in Doku & Memory nachlesbar):

- Ein 9-Schritte-Scaling-Roadmap-Umbau wurde **adversarial auditiert**
  (`docs/audit-report-scaling-roadmap.md`) und in einem **separaten
  Remediation-Track** (`docs/remediation-backlog.md`, T1–T7 als
  Gates + Ops-Items D1–D6) ohne Datenverlust auf Prod gebracht.
- **Roadmap bleibt eingefroren Rev. 2** (Governance E2 — kein Rev. 3,
  nicht anfassen). **Schuld 6 / Move-not-rewrite akzeptiert mit
  Revisit-Trigger** (E1 — kein Abbau-Schritt).
- **`main` == Produktion** (jeder Merge deployt automatisch via
  `.github/workflows/deploy.yml` → ghcr → SSH-Forced-Command auf
  `adm.agentic-reach.com:/opt/services/vibe`). Tests laufen **nicht**
  beim Main-Push (`branches-ignore: [main]`) — der grüne PR ist das
  einzige Test-Gate. Per Konvention: nie direkt auf `main` pushen.

## Stand (alles gemerged auf `main`, alles deployed, alles smoke-grün)

Aktuelle main-Reihenfolge (oben = neuester Stand):

```
5dfbbdf  ops:  T7-C — services/linkedin_import.py-Shim sterben lassen (R2 strukturell, 3/3) (#35)
62e0afe  ops:  T7-B — services/ai.py-Shim sterben lassen (R2 strukturell, 2/3) (#33)
5f5f8eb  ops:  T7-A — models.py-Shim sterben lassen (R2 strukturell, 1/3) (#31)
83208b8  ops:  T6 — Struktur-Assertions ins Doc-Gate (schließt R5) (#29)
43caa2a  ops:  T5 — scaffold patcht Independence-Contract (schließt R6) (#27)
56204f7  test: T4b — e2e-Suite via run_migrations (Alembic-Pfad real) (#24)
f5fa552  test: T4a — Alembic-Baseline-Schema vs. create_all empirisch geprüft (#22)
f2a0a3c  docs: D3/D4 erledigt; Pre-Deploy-Backup-Hook; brand-Mount-Drift (#21)
5a7e114  ops:  D3 — Deploy-Gate härten (verify-Job + immutable :sha-Tag) (#20)
1952cc1  docs: Deploy-Runbook + Off-Host-Backup-Schutz (.gitignore) (#19)
cf3a950  Remediation T2: Web/REST-Modellsperre (schließt R1) (#18)
9ad24ee  Audit-Remediation: T3 + T1 + Backlog (separater Track) (#17)
5258d30  Schritt 9 — Alembic (Roadmap, schon vor diesem Track)
```

Plus serverseitig (nicht im Repo, am `adm.agentic-reach.com` live):
- `vibe-db-backup.timer` (systemd, täglich 02:30 UTC, WAL-sicher,
  integrity-gated, rotiert → `/opt/backups/vibe/`, Restore getestet).
- `/opt/scripts/deploy.sh` mit Pre-Deploy-Backup-Hook für `vibe`
  (`set -e`-gated; runway/landingpage unverändert) — bisher 2× live
  bewiesen, **self-perpetuating**.

Erledigte Track-Items: **T1** (Outcome-Probe etabliert + 2/5 validiert),
**T2** (Web/REST-Modellsperre — Gate aktiv, R1 strukturell zu),
**T3** (Partitions-Vollständigkeits-Test), **T4a** (Alembic-Pfad real
geprüft — `run_migrations` wird in CI ausgeführt, Schema-Drift bricht
den Test), **T4b** (e2e-Suite baut Schema jetzt via `run_migrations`
statt `create_all` — `tests/e2e/conftest.py` überschreibt das geteilte
`engine`-Fixture, schemaneutral per T4a, andere Test-Layer unverändert),
**T5** (Scaffold patcht `independence`-`modules`-Array in `pyproject.toml`
idempotent; CI-Scaffold-Smoke greppt es; chirurgischer 1-Zeilen-Insert
stdlib-only — R6 strukturell zu; `new-domain.expected` bleibt versiegelt,
künftiger Lauf zeigt 9/8 als T5-Messung, kein Korrekturlass; ADR-012),
**T6** (Struktur-Assertions ins Doc-Gate — `scripts/check_architecture_metrics.py`
hat zwei neue Asserter: `check_importlinter_contracts` (Set der
`name`-Werte aus `[[tool.importlinter.contracts]]` in `pyproject.toml`
gegen neue `## Struktur-Verträge (CI-erzwungen)`-Tabelle) und
`check_shim_inventory` (AST-fundiertes Shim-Set — Body nach optionalem
Docstring nur `Import`/`ImportFrom` + max. `__all__`-Assign — gegen
neue `## Re-Export-Shim-Inventar (CI-erzwungen)`-Tabelle, inkl.
LOC-Match je Zeile). Drift in beide Richtungen bricht den Build; stdlib-
only (Regex für TOML, `ast` für Python — gleiche Disziplin wie ADR-012
§B). Keine YAML-Änderung, das Skript läuft schon in allen drei CI-Pfaden.
Self-Test (6 Mutationen, alle Drift-Wege empirisch verifiziert). R5
strukturell zu. ADR-013). **T7-A** (`models.py`-Shim physisch tot —
R2 strukturell, 1/3): neues top-level `db_tables.py` mit expliziter
`register_tables()`-Funktion (Funktions-Form disqualifiziert das Modul
als T6-Shim → Inventar-Zähler **echt** 5→4; top-level statt
`app.core/`, weil `core ↛ domains` jede Aggregation im `app.core`-
Paket verbieten würde — Lektion aus CI-Iteration 2). 4 Aufrufer
umgezogen (`database.create_db` + zwei Test-Conftests + die zwei
Alembic-Baselines), 17 Test-Dateien `from models import …` → direkte
`app.{core,domains,shared}.*`-Importer, `test_models_split.py` auf
neuen Bootstrap-Vertrag umgeschrieben. ADR-014.
**T7-B** (`services/ai.py`-Shim physisch tot — R2 strukturell, 2/3):
Anders als T7-A keine Aggregations-Rolle, sondern reine monkeypatch-
Naht der frozen S0.5-Char-Tests + S6-Unit-Test. Recon vorab fand 1
Prod-Importer (`app/domains/proposals/service.py:62`, lazy) + 3 Test-
Importer mit 5 `setattr(ai, "chat_with_context", …)`-Aufrufen.
Lifecycle-Swap mechanisch: Prod-Seam retargeted auf
`from app.core import ai as _seam`; 3 Test-Files `from services
import ai` → `from app.core import ai`; Sonderfall
`ai.generate_proposal_drafts` (lebt in `app.domains.proposals.service`)
per Zusatz-Import + 2 Aufrufstellen gelöst (macht Schritt-6-Layering
Adapter ≠ Orchestrierung sichtbar). monkeypatch-Aufrufe selbst byte-
identisch. Bonus-Sweep: veraltete `services.ai`-Seam-Kommentare in
`app/core/ai.py`, `app/interfaces/web/{ai,proposals}.py`, `README.md`
retargeted. Keine neue import-linter-Regel (Datei-Löschung ist das
Gate). **CI grün first try, KEIN fix-forward** — Recon zahlte sich
aus. ADR-015.
**T7-C** (`services/linkedin_import.py`-Shim physisch tot — R2
strukturell, 3/3): mechanisch sauberer als T7-B — alle 4
re-exportierten Symbole (`SYSTEM_PROMPT`, `LinkedInImportError`,
`_parse_json_block`, `extract_lead_from_pdf`) leben tatsächlich in
`app/core/ai.py`, **kein Sonderfall** analog T7-B/
`generate_proposal_drafts`. Recon vorab fand 2 Prod-Importer
(`app/domains/leads/service.py:127` lazy, `app/interfaces/web/leads.py:222`
modul-lokal) + 2 Test-Importer mit 2 `setattr(li, "extract_lead_from_pdf",
…)`-Aufrufen (alle in `tests/characterization/test_leads_routes.py`).
Lifecycle-Swap mechanisch: 2 Prod-Imports retargeted
(`from services import linkedin_import as _li` →
`from app.core import ai as _li`; `from services.linkedin_import
import LinkedInImportError` → `from app.core.ai import LinkedInImportError`),
2 Test-Imports retargeted (`import services.linkedin_import as li` →
`from app.core import ai as li`), monkeypatch-Aufrufe byte-identisch.
Keine neue import-linter-Regel. **CI grün first try, KEIN fix-forward**
(zweites Mal in Folge nach T7-B — Recon-Disziplin gefestigt).
Kennzahlen: LOC 12.297→12.240, Prod 8.700→8.636 (−64 über T7-A/B/C),
Tests 3.597→3.604 (+7 über T7-A/B/C). Gate-Output ist jetzt
`5 import-linter contracts and 2 re-export shims accounted for`. ADR-016.
Erledigte Ops: **D1** (Server-DB-Persistenz belegt), **D2**
(Backup-Automatik + Restore-Test on-host), **D3** (Deploy-`verify`-Job
+ Pre-Deploy-Backup-Hook serverseitig), **D4** (immutable `:sha`-Tag
+ image-basierter Rollback-Pfad).

## Offen

**Track:**
- **T7-D** (P2) — `services.mcp_server` → `app/interfaces/mcp/server.py`
  relozieren (Move-not-rewrite des FastMCP-Servers + Mount-Pfad-
  Anpassung in `main.py`/`app/interfaces/mcp/mount.py`; ADR-009 §B
  benannte den `m.engine`-Seam als frozen → der Move ist der Lifecycle-
  Endpunkt). Eigener ADR, eigener PR. **Hinweis:** anders als T7-A/B/C
  ist das ein **Move**, kein Shim-Tod — der T6-Inventar-Zähler ändert
  sich dadurch nicht (mcp_server ist 436 LOC echte Logik, kein
  Re-Export-Shim). Konkret: importer-Sweep auf `services.mcp_server`
  (`main.py` mountet via `routes/mcp.py`-Wrapper-ASGI), Mount-Pfad +
  `from services.mcp_server import mcp_server as m` retargeten,
  Datei verschieben (Compliance-frei — `m.engine`-Seam ist frozen,
  also nur Pfad).
- **`routes/{leads,proposals}.py`** — die zwei `app.interfaces.web.*.router`-
  Re-Export-Shims. Nicht in T7 als eigenes Item geführt; sterben mit der
  nächsten Char-Test-Reorganisation (Test-Importer `from routes import
  leads as leads_route` ablegen). Inventar-Zähler-Ziel: 0.

**Vorschlag als nächster Schritt**: T7-D (mcp_server-Relokation) —
**andere** Mechanik als T7-A/B/C (Move-not-rewrite eines lebenden
Moduls statt Shim-Tod). Recon zuerst: alle Importer von
`services.mcp_server` ermitteln (vermutlich `routes/mcp.py` +
`main.py`-Mount); Mount-Pfad-Konsequenzen klären (Trailing-Slash,
`/mcp/`-URL); Move-not-rewrite-Plan in ADR-017 fixieren bevor irgendwas
verschoben wird. Recon-Disziplin von T7-B/T7-C beibehalten — sie
hat zweimal in Folge first-try-CI-grün produziert.

**Ops:**
- **D2b** — Off-Host-Backup-Automatik. Heute fehlt am Server jedes
  Tooling (kein rclone/restic/aws/gsutil/b2) **und** ein Ziel.
  Echte Infra-Entscheidung (zweiter Host via scp/rsync-Key, oder
  Objekt-Storage-Bucket + Creds). Interim deckt: Pre-Deploy-Hook +
  Timer + der manuelle Off-Host-Snapshot in lokalem `.secrets/`.
- **D5** (optional) — Staging-Umgebung (gleiches Image, Kopie der DB)
  für riskante Migrations-Proben ohne Prod-Risiko.

**Empfohlene Reihenfolge (mein Vorschlag, nicht bindend):**
T7-D (mcp_server-Relokation, Move-not-rewrite, ADR-017); D2b parallel
sobald die Ziel-Infra entschieden ist.

## Stehendes Mandat (Track-PRs eigenständig mergen)

Du darfst Track-PRs **nach grüner CI selbst squash-mergen** und das
Branch löschen — analog zu Sessions vom 2026-05-20 (T4b PR #24 +
NEXT-SESSION-PROMPT-Folge PR #25; T5 PR #27 + Folge-Doku PR #28; T6
PR #29 + Folge-Doku PR #30; T7-A PR #31 + Folge-Doku PR #32;
T7-B PR #33 + Folge-Doku PR #34; T7-C PR #35 + Folge-Doku).
Begründung: jede Track-PR-Iteration
ist klein, byte-äquivalent geprüft (`make verify` inkl. Char-Tests +
90 %-Invoicing-Suite + import-linter + Doc-Gate + Probe-Lint), und der
Deploy-Pfad ist self-perpetuating gesichert (D3 Pre-Deploy-`verify`-Job
gated Main; serverseitiger Pre-Deploy-Backup-Hook sichert die DB vor
jedem Apply; D4 `:sha`-Tag erlaubt sekundenschnellen Rollback ohne
Rebuild). Manuelle Maintainer-Reviews vor Merge waren in keiner
Track-PR der Hebel — die Gates *waren* der Review.

**Geltungsbereich:** Track-PRs (Remediation-Backlog T1–T7), Ops-PRs
(D-Items) und Folge-Doku-PRs zu beiden (z. B. NEXT-SESSION-PROMPT-,
ARCHITECTURE.md-, Backlog-Updates im Anschluss an einen gemergten
Track-PR). **NICHT erfasst:** alles, was die Roadmap selbst anfasst (E2 —
Rev. 2 ist eingefroren); Änderungen an `.secrets/`-Schutz oder
Deploy-/Backup-Infrastruktur ohne explizite Rückfrage; alles, was den
Steuerberater-/Compliance-Bereich berührt (siehe
[[billing-bounded-context-decision]]). Im Zweifel: rückfragen statt
mergen.

**Ablauf nach grüner CI:**
1. `gh pr merge <#> --squash --delete-branch`
2. `git checkout main && git pull --ff-only` + `git log --oneline -3`
   verifizieren (Squash-SHA sichtbar = Auto-Deploy läuft)
3. Doc-Gate + Probe-Lint lokal nachschießen (sollten grün bleiben — kein
   `.py`-Drift möglich, weil der PR ja gerade grün war)
4. Folge-Doku-PR (falls passend, analog #23/#25): NEXT-SESSION-PROMPT
   auf den neuen Stand ziehen, Memory `scaling-roadmap-progress` +
   `MEMORY.md`-Index ergänzen — und denselben Mandats-Pfad nutzen.

## Harte Constraints (gelten immer, nicht verletzen)

- **Kein lokaler Interpreter mit App-Deps.** `make verify` ist CI-only.
  Einziger lokaler Hebel: stdlib-Skripte —
  `python3 scripts/check_architecture_metrics.py` (Doc-Gate) und
  `python3 scripts/outcome_probe.py --lint`. Beide müssen grün bleiben.
- **Doc-Gate-Disziplin:** jede `.py`-Änderung **außerhalb `scripts/`**
  verschiebt Kennzahlen → ARCHITECTURE.md im **selben Change** syncen,
  sonst CI rot.
- **`services/invoicing/` ist move-not-rewrite** (Compliance, 90 %-Netz)
  — nur additive Änderungen, nie umschreiben.
- **`docs/outcome-probe/*.expected` sind versiegelt** — niemals nach
  einem Lauf editieren; ein Mismatch ist ein Befund, kein Korrekturlass.
- **`.secrets/` enthält echte Lead-PII** (`leads.db.snap-…`) — niemals
  committen. `.gitignore` schützt `.secrets/` + `*.db.snap-*`; bei
  jedem `git add` explizite Pfade nutzen, **nie `-A`** (Lektion aus
  PR #8).
- **Track vs. Roadmap nicht vermischen.** `docs/scaling-roadmap.md`
  ist historischer Record, nicht anfassen. Diese Arbeit lebt im
  Remediation-Backlog + zugehörigen ADRs (ADR-011 für T2,
  weitere für künftige Items).
- Agent-Edit-Protokoll + Contract-Kantentabelle: `CLAUDE.md`. Memory
  `scaling-roadmap-progress` (+ `MEMORY.md`-Index) hat den vollen
  Verlaufsstand — zuerst lesen.

## Server-Zugang

`ssh adm.agentic-reach.com` (User `uli`, sudo verfügbar, **sei vorsichtig**).
Hier liegt Prod (`/opt/services/vibe`, Container `vibe-vibe-1`, Bind-Mount
der `leads.db`); Backups in `/opt/backups/vibe`; Backup-Skript
`/usr/local/bin/vibe-db-backup.sh`; Deploy-Multi-Service-Skript
`/opt/scripts/deploy.sh` (touched runway+landingpage). Read-only-Recon
zuerst, jede Mutation mit `.bak` vorher.

## Beginn

Verifiziere den Status (`git status`, `git log --oneline -5`,
`docs/remediation-backlog.md` lesen, Doc-Gate + Probe-Lint grün prüfen,
`gh pr list --state open`), kläre mit dem User welches Item als
nächstes (Vorschlag T7-D, mcp_server-Move-not-rewrite, mit Recon-
Schritt vorab — **andere Mechanik** als T7-A/B/C, also nicht
mechanisch übertragen), und arbeite es als eigenen PR ab —
schemaneutral, byte-äquivalent wo Move, sealed bleibt sealed,
Kennzahlen im selben Change syncen.
