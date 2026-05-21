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
14f0b0f  ops:  T7-D — services/mcp_server.py → app/interfaces/mcp/server.py (Move-not-rewrite, ADR-009 §B-Endpunkt) (#37)
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
  (`set -e`-gated; runway/landingpage unverändert) — bisher mehrfach live
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
stdlib-only — R6 strukturell zu; ADR-012),
**T6** (Struktur-Assertions ins Doc-Gate — `scripts/check_architecture_metrics.py`
hat zwei neue Asserter: `check_importlinter_contracts` + `check_shim_inventory`;
beide stdlib-only, Drift in beide Richtungen bricht den Build; R5
strukturell zu; ADR-013).
**T7-A** (`models.py`-Shim physisch tot — R2 strukturell, 1/3):
Aggregations-Rolle in top-level `db_tables.register_tables()` umgezogen;
17 Test-Dateien `from models import …` → direkte
`app.{core,domains,shared}.*`-Importer; ADR-014.
**T7-B** (`services/ai.py`-Shim physisch tot — R2 strukturell, 2/3):
Reine monkeypatch-Naht der frozen S0.5-Char-Tests + S6-Unit-Test.
1 Prod-Importer (`app/domains/proposals/service.py:62`, lazy) + 3 Test-
Importer mit 5 `setattr(ai, "chat_with_context", …)`-Aufrufen. Sonderfall
`ai.generate_proposal_drafts` (lebt in `app.domains.proposals.service`,
nicht `app.core.ai`) per Zusatz-Import + 2 Aufrufstellen gelöst.
CI grün first try; ADR-015.
**T7-C** (`services/linkedin_import.py`-Shim physisch tot — R2 strukturell,
3/3): mechanisch sauberer als T7-B — alle 4 re-exportierten Symbole
leben tatsächlich in `app/core/ai.py`, kein Sonderfall. 2 Prod-Importer
+ 2 Test-Imports retargeted; CI grün first try; ADR-016.
**T7-D** (`services/mcp_server.py` → `app/interfaces/mcp/server.py` —
R2 strukturell vollständig zu): **Andere Mechanik** als T7-A/B/C — kein
Shim-Tod, sondern Move-not-rewrite eines lebenden 363-LOC-Moduls (16
`@mcp.tool` + modul-globaler `engine`-Seam). ADR-009 §B-Endpunkt eingelöst:
der frozen `m.engine`-Monkeypatch-Seam zog byte-äquivalent mit, weil
`monkeypatch.setattr(m, "engine", …)` an das Modul-Objekt bindet, nicht
an den Import-Pfad-String (selber `sys.modules`-Eintrag). Recon vorab fand:
2 Prod-Importer (`app/interfaces/mcp/{__init__,mount}.py`, beide
`from services.mcp_server import mcp`) + 1 Test-Importer
(`tests/characterization/conftest.py:81`, `import services.mcp_server as m`).
`main.py` greift nur indirekt via `app.interfaces.mcp`-Paket — unverändert.
Mechanik: `git mv` + 2 Prod-Imports retargeted + 1 Test-Import retargeted
+ 1 Linter-Regel umbenannt (`source_modules = ["app.interfaces.mcp.server"]`
+ `name`-String synchron zur ARCHITECTURE.md-Struktur-Verträge-Tabelle,
sonst Doc-Gate rot) + Doc-Gate-Skript `m_mcp_tools` zählt am neuen Pfad
+ datei-eigenes Docstring auf neuen Mount-Pfad korrigiert (referenzierte
vorher `routes/mcp.py`, seit Schritt 8 weg — Stale-Korrektur).
**Zwei kleine fix-forward-Iterationen nötig** (anders als T7-B/C, die
first-try grün waren): (1) ruff-Lint-Sweep im neuen Pfad-Scope —
`select` war seit Schritt 7 genuin tot (F401-Drop, 0 LOC) + per-file-
E402-ignore für die deliberaten Late-Imports der Invoice-Tool-Gruppe
(analog `web/*`/`api/*`-Layout-Debt); (2) `ruff format` Konformitäts-
Bump (+6 prod LOC: Leerzeilen nach Section-Komment-Bannern + 2
Mehrzeilen-Aufrufe in `finalize_invoice`/`create_storno` — rein kosmetisch),
weil `app/`-Pfad unter den Format-Scope fällt. **Lektion**: der Move
ins `app/`-Scope macht latente Legacy-Layout-Schulden sichtbar; das ist
in ADR-017 §G/§H dokumentiert und sollte für künftige Move-Items
einkalkuliert werden (kein Recon-Fehler, sondern Strukturschuld).
Kennzahlen: LOC 12.254 / 8.646 / 3.608 (+14 = +8 Naht-Docstring +6 Format).
Shim-Inventar unverändert (mcp_server ist keine Re-Export-Shim — Body
enthält Funktions-Definitionen; T6-AST-Walk klassifiziert korrekt als
Nicht-Shim → Gate-Output bleibt `5 import-linter contracts and 2
re-export shims accounted for`). Schicht-Hygiene auf der Interface-Achse
jetzt vollständig: `services/` enthält keine Interface-Schicht mehr
(`auth/numbering/pdf/proposals` = Reusable-Kernel, `invoicing/` =
Compliance-Move-not-rewrite). ADR-017. **R2 strukturell vollständig
zu** (T7-A + T7-B + T7-C + T7-D); **T7 abgeschlossen**.
Erledigte Ops: **D1** (Server-DB-Persistenz belegt), **D2**
(Backup-Automatik + Restore-Test on-host), **D3** (Deploy-`verify`-Job
+ Pre-Deploy-Backup-Hook serverseitig), **D4** (immutable `:sha`-Tag
+ image-basierter Rollback-Pfad).

## Offen

**Track:**
- *(keiner)* — T7 ist abgeschlossen. Der Remediation-Track hat keine
  offenen T-Items mehr.
- **`routes/{leads,proposals}.py`** — die zwei `app.interfaces.web.*.router`-
  Re-Export-Shims. Nicht in T7 als eigenes Item geführt; sterben mit der
  nächsten Char-Test-Reorganisation (Test-Importer `from routes import
  leads as leads_route` ablegen). Inventar-Zähler-Ziel: 0.

**Ops:**
- **D2b** — Off-Host-Backup-Automatik. Heute fehlt am Server jedes
  Tooling (kein rclone/restic/aws/gsutil/b2) **und** ein Ziel.
  Echte Infra-Entscheidung (zweiter Host via scp/rsync-Key, oder
  Objekt-Storage-Bucket + Creds). Interim deckt: Pre-Deploy-Hook +
  Timer + der manuelle Off-Host-Snapshot in lokalem `.secrets/`.
- **D5** (optional) — Staging-Umgebung (gleiches Image, Kopie der DB)
  für riskante Migrations-Proben ohne Prod-Risiko.

**Empfohlene Reihenfolge (mein Vorschlag, nicht bindend):**
D2b sobald die Ziel-Infra entschieden ist (P1, Wertbeitrag = echte
Off-Host-DR-Garantie); D5 falls eine größere Schema-Änderung ansteht
(P2, optional). Die `routes/*.py`-Test-Shims können bei nächster Char-
Test-Reorganisation mitgenommen werden — kein eigenes T-Item.

## Stehendes Mandat (Track-PRs eigenständig mergen)

Du darfst Track-PRs **nach grüner CI selbst squash-mergen** und das
Branch löschen — analog zu Sessions vom 2026-05-20/21 (T4b PR #24 +
NEXT-SESSION-PROMPT-Folge PR #25; T5 PR #27 + Folge-Doku PR #28; T6
PR #29 + Folge-Doku PR #30; T7-A PR #31 + Folge-Doku PR #32;
T7-B PR #33 + Folge-Doku PR #34; T7-C PR #35 + Folge-Doku PR #36;
T7-D PR #37 + Folge-Doku).
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
4. Folge-Doku-PR (falls passend, analog #36): NEXT-SESSION-PROMPT
   auf den neuen Stand ziehen, Memory `scaling-roadmap-progress` +
   `MEMORY.md`-Index ergänzen — und denselben Mandats-Pfad nutzen.

## Harte Constraints (gelten immer, nicht verletzen)

- **Kein lokaler Interpreter mit App-Deps.** `make verify` ist CI-only.
  Einziger lokaler Hebel: stdlib-Skripte —
  `python3 scripts/check_architecture_metrics.py` (Doc-Gate) und
  `python3 scripts/outcome_probe.py --lint`. Beide müssen grün bleiben.
  **Zusatz seit T7-D**: `ruff` (`pip install --user ruff`) ist
  app-dep-frei und reicht für `ruff format --check app` + `ruff check
  scripts app` lokal vor Push — empfohlen bei jedem Move-not-rewrite-
  Item in `app/`, weil `services/` außerhalb des Format-Scopes lag und
  Move-Items latente Layout-Debt sichtbar machen (T7-D-Lektion,
  ADR-017 §G/§H).
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
nächstes (Vorschlag D2b sobald die Ziel-Infra geklärt ist — echte
Infra-Entscheidung, deshalb mit dem User abklären), und arbeite es als
eigenen PR ab — schemaneutral, byte-äquivalent wo Move, sealed bleibt
sealed, Kennzahlen im selben Change syncen.
