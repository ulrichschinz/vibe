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
Gate-Output meldet jetzt `5 import-linter contracts and 5 re-export shims
accounted for` — T7 hat damit einen lebenden Zähler. Self-Test (6
Mutationen, alle Drift-Wege empirisch verifiziert). R5 strukturell zu.
ADR-013). Erledigte Ops: **D1** (Server-DB-Persistenz belegt), **D2**
(Backup-Automatik + Restore-Test on-host), **D3** (Deploy-`verify`-Job
+ Pre-Deploy-Backup-Hook serverseitig), **D4** (immutable `:sha`-Tag
+ image-basierter Rollback-Pfad).

## Offen

**Track:**
- **T7** (P2) — Shim-Sterbe-Gates für `models.py` /
  `services.ai`+`linkedin_import` / `services.mcp_server`. Mehrere PRs,
  nicht eines. **Vorschlag als nächster Schritt**: jeder Shim-Tod fällt
  jetzt im T6-Inventar-Gate auf (`5 re-export shims accounted for`-Zähler
  ändert sich) — gute Sichtbarkeit für die mehrstufige Bearbeitung. Pro
  PR: ein Shim sterben lassen (Test-Importer migrieren, Datei löschen,
  Inventar-Zeile entfernen, ggf. import-linter-Aktivierung), Char-Test-
  Lifecycle-Swap wo zutreffend.

**Ops:**
- **D2b** — Off-Host-Backup-Automatik. Heute fehlt am Server jedes
  Tooling (kein rclone/restic/aws/gsutil/b2) **und** ein Ziel.
  Echte Infra-Entscheidung (zweiter Host via scp/rsync-Key, oder
  Objekt-Storage-Bucket + Creds). Interim deckt: Pre-Deploy-Hook +
  Timer + der manuelle Off-Host-Snapshot in lokalem `.secrets/`.
- **D5** (optional) — Staging-Umgebung (gleiches Image, Kopie der DB)
  für riskante Migrations-Proben ohne Prod-Risiko.

**Empfohlene Reihenfolge (mein Vorschlag, nicht bindend):**
T7 (mehrere PRs, je ein Shim-Tod); D2b parallel sobald die Ziel-Infra
entschieden ist.

## Stehendes Mandat (Track-PRs eigenständig mergen)

Du darfst Track-PRs **nach grüner CI selbst squash-mergen** und das
Branch löschen — analog zu Sessions vom 2026-05-20 (T4b PR #24 +
NEXT-SESSION-PROMPT-Folge PR #25; T5 PR #27 + Folge-Doku PR #28; T6
PR #29 + Folge-Doku). Begründung: jede Track-PR-Iteration
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
nächstes (Vorschlag T6), und arbeite es als eigenen PR ab —
schemaneutral, byte-äquivalent wo Move, sealed bleibt sealed,
Kennzahlen im selben Change syncen.
