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
den Test). Erledigte Ops: **D1** (Server-DB-Persistenz belegt), **D2**
(Backup-Automatik + Restore-Test on-host), **D3** (Deploy-`verify`-Job
+ Pre-Deploy-Backup-Hook serverseitig), **D4** (immutable `:sha`-Tag
+ image-basierter Rollback-Pfad).

## Offen

**Track:**
- **T4b** (P1, mittel) — `tests/conftest.py` für die e2e-Suite auf
  `run_migrations` statt `create_all` umstellen. Macht den Alembic-Pfad
  in jedem CI-Lauf real exerciert (heute nur via T4a). Schemaneutral,
  aber **alle e2e-Tests müssen weiter grün bleiben** — risikoreichster
  Test-Layer-Change im Track.
- **T5** (P1) — `scripts/new_domain.py` patcht das `independence`-
  Contract-Array in `pyproject.toml` idempotent + CI-Scaffold-Smoke
  prüft `grep -q "app.domains.<name>" pyproject.toml`. Schließt R6
  (gescaffoldete 4. Domäne ist heute in **0** Contracts).
- **T6** (P2) — Struktur-Assertions ins Doc-Gate
  (`scripts/check_architecture_metrics.py` erweitern um erwartete
  import-linter-Contract-Namen-Menge + Shim-Pfad-Inventar gegen eine
  neue ARCHITECTURE.md-Tabelle). Macht Struktur-Prosa selbst-verifizierend.
- **T7** (P2) — Shim-Sterbe-Gates für `models.py` /
  `services.ai`+`linkedin_import` / `services.mcp_server`.

**Ops:**
- **D2b** — Off-Host-Backup-Automatik. Heute fehlt am Server jedes
  Tooling (kein rclone/restic/aws/gsutil/b2) **und** ein Ziel.
  Echte Infra-Entscheidung (zweiter Host via scp/rsync-Key, oder
  Objekt-Storage-Bucket + Creds). Interim deckt: Pre-Deploy-Hook +
  Timer + der manuelle Off-Host-Snapshot in lokalem `.secrets/`.
- **D5** (optional) — Staging-Umgebung (gleiches Image, Kopie der DB)
  für riskante Migrations-Proben ohne Prod-Risiko.

**Empfohlene Reihenfolge (mein Vorschlag, nicht bindend):**
T4b → T5 → T6 → T7; D2b parallel sobald die Ziel-Infra entschieden ist.

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
nächstes (Vorschlag T4b), und arbeite es als eigenen PR ab —
schemaneutral, byte-äquivalent wo Move, sealed bleibt sealed,
Kennzahlen im selben Change syncen.
