# Deploy-Runbook — Audit-Remediation-Track auf Prod bringen

> Stand 2026-05-19. Zweck: die offenen Remediation-PRs (#17, #18 — und
> später T4–T7) **ohne Datenverlust** und ohne App-Ausfall auf `main` =
> Prod bringen. Single sources: `.github/workflows/deploy.yml`,
> `docker-compose.yml`, `database.py`, `app/core/db_migrate.py`,
> `docs/adr/010-alembic-split-versioning.md`.

---

## 1. Wie Deploy hier *wirklich* funktioniert (verifiziert)

```
PR (grün) ──merge──▶ main ──push──▶ .github/workflows/deploy.yml
                                      ├─ build-and-push: Docker-Image →
                                      │    ghcr.io/<repo>:latest
                                      └─ deploy: SSH (forced command) →
                                           cd /opt/services/vibe
                                           docker compose pull
                                           docker compose up -d --remove-orphans
```

**Konsequenzen, die den ganzen Plan bestimmen:**

1. **`main` == Produktion.** Jeder Merge nach `main` löst sofort einen
   echten Prod-Deploy aus. Es gibt kein manuelles „Deploy-Knopf"-Gate
   dazwischen.
2. **Tests laufen NICHT beim Main-Push.** `test.yml` ist
   `push: branches-ignore: [main]` + `pull_request: branches: [main]`.
   Das `make verify` (ruff/mypy/import-linter/test-fast/doc-gate) läuft
   **nur auf dem PR**. Beim Main-Push laufen nur `deploy.yml`,
   `doc-metrics.yml`, `outcome-probe.yml`. → **Der grüne PR ist das
   einzige Sicherheits-Gate. Niemals direkt auf `main` pushen — immer nur
   via grünem PR mergen.**
3. **`deploy.yml` hat kein `needs:` auf Tests/Doc-Gate.** Der Deploy-Job
   startet unabhängig. Ein nachträglicher Doc-Drift auf `main` würde den
   Deploy *nicht* stoppen. (Härtungs-Punkt, s. §7.)
4. **Image-Tag ist nur `:latest`** (keine immutablen Versions-Tags).
   Rollback = Git-Revert + Rebuild, nicht „altes Image redeployen"
   (das alte `:latest` ist nach dem nächsten Build überschrieben).
5. **Bei einem PR-Stack = mehrere Deploys.** #17→main deployt, dann
   #18→main deployt erneut. Jeder Zwischenzustand von `main` muss für
   sich deploy-fähig sein (ist er — s. §3).

---

## 2. Datensicherheit — warum die bestehenden Leads sicher sind

- **`leads.db` ist eine host-persistierte SQLite-Datei — VERIFIZIERT am
  Server (2026-05-19, SSH `adm.agentic-reach.com` = `ar00`).** Die
  Server-Compose `/opt/services/vibe/docker-compose.yml` bindet
  `./leads.db:/app/leads.db` (+ `./archive:/app/archive`,
  `./generated_pdfs`), Image `ghcr.io/ulrichschinz/vibe:latest`. Host-
  Datei `/opt/services/vibe/leads.db` ist live (~180 KB, an dem Tag
  aktualisiert). Container `vibe-vibe-1` lief „Up 12 hours" auf `:latest`.
  `docker compose pull && up -d` (= der deploy.yml-Mechanismus) ersetzt
  **nur den Container**, der Bind-Mount bleibt → die echten Leads
  überleben Image-/Container-Tausch nachweislich (haben sie über die
  letzten Deploys). **D1 ist damit Beleg, keine Annahme mehr.**
- ⚠️ **WAL-Modus aktiv** (`leads.db-wal`/`-shm` am Server vorhanden):
  ein nacktes `cp leads.db` bei laufender App ist **nicht konsistent**
  (uncheckpointete Daten im `-wal`). Backups daher zwingend per
  `sqlite3 .backup` (transaktionssicher) **oder** App stoppen → kopieren.
- **T1/T2/T3 ändern null am Datenmodell.** Kennzahl
  `SQLModel-Tabellen = 13` über alle drei PRs unverändert (Doc-Gate
  CI-verifiziert). Reine Code-Umzüge (move-not-rewrite, 0-Diff, von 132
  Characterization-Tests + 90 %-Invoicing im PR-CI gepinnt). **DB-Risiko
  von #17/#18 = 0.**
- **Schritt 9 (Alembic) ist seit PR #16 auf `main` und damit bereits in
  Prod gelaufen** (Prod fährt `main`, App läuft mit Leads → der
  Alembic-Adopt der echten `leads.db` ist **schon passiert und
  erfolgreich**). `app.core.db_migrate.run_migrations(engine)` läuft bei
  *jedem* App-Start (`main.py` lifespan → `database.create_db()`); er ist
  **idempotent** (`create_all(checkfirst)` + `CREATE TRIGGER IF NOT
  EXISTS` + introspektions-geschützte `ALTER`; `command.upgrade(...,
  "head")` ist No-op, wenn schon auf head). Kein `alembic stamp` nötig,
  keine Datenmigration. Der historisch heikelste Punkt (erster
  Adopt-Lauf) **liegt hinter uns.**

**Fazit:** #17 und #18 sind aus Datensicht risikoarm. Das Restrisiko ist
*Code*-Verhalten (durch den grünen PR-CI inkl. Characterization-Suite
abgedeckt), nicht *Daten*.

---

## 3. Merge-Sequenz (konkret)

Stack: `#18 (T2) → base #17 (T3+T1+Backlog) → base main`.

1. **Backup ziehen** (s. §4) — *vor* dem ersten Merge. Pflicht, auch wenn
   schemaneutral: etabliert die Routine + Sicherheitsnetz.
2. **#17 → `main` mergen** (Merge-Commit oder Squash — Projektstil).
   Löst Deploy aus. **Zwischenzustand sicher:** #17 ändert **keinen
   Produktivcode** (`app/`, `services/`, `main.py`, `database.py`
   unberührt) — nur Docs, `tests/test_db_partition.py`,
   `scripts/outcome_probe.py`, Workflows, ARCHITECTURE.md. Das Image
   wird neu gebaut, Laufzeitverhalten ist **identisch**.
3. **#18 auf `main` retargeten** (GitHub bietet das automatisch an, sobald
   #17 weg ist; sonst Base manuell auf `main` setzen) und **mergen**.
   Löst zweiten Deploy aus. #18 = der einzige Produktivcode-Change;
   0-Diff CI-grün (PR #18 `test`-Job pass: ruff+mypy+import-linter+
   test-fast+doc-gate).
4. **Post-Deploy-Smoke (§5)** nach *jedem* der beiden Deploys.

Alternative (1 Deploy statt 2): #18 direkt auf `main` retargeten und nur
#18 mergen — zieht #17 mit. Nachteil: vermischt die zwei Track-Konzerne im
Main-Verlauf. Empfehlung: getrennte Sequenz, beide Zwischenzustände sind
nachweislich deploy-fähig.

---

## 4. Backup-Strategie (aktuell die größte Lücke)

**Befund (am Server verifiziert 2026-05-19) — schlimmer als „keine
Automatik":**
- **Null Backup-Automatik:** kein User-Crontab, kein Backup-Job in
  `/etc/cron.d`/`cron.daily` (nur OS: logwatch/apt/rkhunter/…), kein
  systemd-Backup-Timer.
- **Vorhandene `leads.db.bak.*` (05-07, 05-09, 05-10) sind manuell,
  unregelmäßig und liegen IM SELBEN VERZEICHNIS auf DEMSELBEN HOST** wie
  die Live-DB. `find /` fand **keine** Off-Host-Kopie (nur ephemere
  Container-Overlay-Kopien). Ein Platten-/Host-Verlust vernichtet
  Live-DB **und** alle „Backups" gemeinsam.
- **Neuestes Backup war ~9 Tage alt** gegenüber der Live-DB → im
  Restore-Fall *heute* bis zu 9 Tage Leads weg.

Das ist die größte reale Lücke des gesamten Setups — größer als das
#17/#18-Deploy-Risiko. Genau der Punkt, den du angesprochen hast.

### 4a. Sofort, manuell (vor jedem Merge nach main, bis Automatik steht)

Auf dem Server (`/opt/services/vibe`), **konsistente** SQLite-Kopie
(nicht `cp` während Schreibzugriff — `.backup` ist transaktionssicher):

```bash
ts=$(date +%Y%m%d-%H%M%S)
docker compose exec -T app \
  sqlite3 /app/leads.db ".backup '/app/leads.db.bak-$ts'"
# Kopie aus dem Container/Mount heraus an einen Off-Host-Ort sichern:
cp /opt/services/vibe/leads.db.bak-$ts /opt/backups/vibe/   # Beispielpfad
```

(Falls `sqlite3` im Image fehlt: `docker compose stop app` → Datei
kopieren → `start app`. Kurzer Ausfall, aber garantiert konsistent.)

### 4b. Automatik — INSTALLIERT & GETESTET (2026-05-19, D2 Phase 1)

Am Server `ar00` eingerichtet (additiv, reversibel):
- `/usr/local/bin/vibe-db-backup.sh` — WAL-sicherer `sqlite3 .backup` →
  `PRAGMA integrity_check` (Abbruch bei Korruption, kein Überschreiben
  guter Historie) → `gzip` → Rotation (neueste 60). Schreibt nach
  **`/opt/backups/vibe/`** (außerhalb des Deploy-Dirs
  `/opt/services/vibe` → ein fehlerhafter Deploy/`compose`-Lauf kann die
  Backups nicht treffen). Live-DB nur lesend angefasst.
- `vibe-db-backup.timer` (systemd) — `OnCalendar=*-*-* 02:30 UTC`,
  `Persistent=true` (holt verpasste Läufe nach Downtime nach).
  `enable --now`, erster Lauf grün.
- **Restore-Test bestanden** (nicht-destruktiv, `/tmp`): `gzip -t` ok,
  `integrity_check ok`, Zeilenzahlen restored==live (lead 12 / note 17 /
  proposal 4 / user 2). Skript-Kopie versioniert unter
  `.secrets/vibe-db-backup.sh` (gitignored).

**Reversibel:** `systemctl disable --now vibe-db-backup.timer` +
`rm /usr/local/bin/vibe-db-backup.sh /etc/systemd/system/vibe-db-backup.*`.

### 4c. NOCH OFFEN — die Off-Host-Automatik (D2 Phase 2)

Phase 1 + der Pre-Deploy-Hook (D3, 2026-05-20) liegen weiterhin auf
**demselben Host/Datenträger** wie die Live-DB (`/dev/sda1`). Ein Host-/
Disk-Verlust ist damit immer noch nicht abgedeckt. **Update 2026-05-20:**
die alte „bis zu 24 h zwischen Backup und Deploy"-Lücke ist
geschlossen — `/opt/scripts/deploy.sh` ruft jetzt für `vibe` als
**ersten** Schritt `/usr/local/bin/vibe-db-backup.sh` auf (vor `compose
pull`); `set -e` blockt einen Deploy ohne Sicherung. Jeder Deploy ist
also selbst-sichernd. Off-Host-Stand: periodisch manuell (der
`sqlite3 .backup` + `scp`-Weg, checksum-verifiziert) — `.secrets/
leads.db.snap-…` als interim Off-Host-Anker. Für die *automatische*
Off-Host-Leg fehlt am Server jedes Tooling (kein rclone/restic/aws/
gsutil/b2) **und** ein Ziel: Infra-Entscheidung (zweiter Host via
scp/rsync-Key, oder Objekt-Storage-Bucket + Creds) — siehe D2b in §7.

---

## 5. Post-Deploy-Smoke (nach jedem Main-Deploy, < 2 Min)

1. App erreichbar: `GET /login` → 200 (oder Health-Endpoint, falls
   vorhanden).
2. **Leads-Daten intakt:** einloggen, `/leads` öffnen → die bestehenden
   Leads sind sichtbar und vollzählig (Stichprobe: bekannte Lead-ID
   `/leads/{id}`).
3. Eine Schreib-Operation: Notiz an einem Test-Lead anlegen → erscheint
   (testet den T2-Pfad `create_note_web` end-to-end real).
4. REST: `GET /api/leads` mit gültigem `X-API-Key` → 200, Liste.
5. Logs: `docker compose logs --tail=100 app` — kein
   `run_migrations`-Fehler, kein Traceback beim Start.

Schlägt 2. fehl → sofort Rollback (§6) und Backup zurückspielen.

---

## 6. Rollback

**Image-basierter Rollback (schnellster Weg, seit D4 2026-05-20):** das
alte Image steht unter unveränderlichem `:sha-<short>`-Tag in ghcr. Auf
dem Server (Sekunden, ohne Git/Rebuild):

```bash
sudo docker pull ghcr.io/ulrichschinz/vibe:sha-<alt>
sudo docker tag  ghcr.io/ulrichschinz/vibe:sha-<alt> \
                 ghcr.io/ulrichschinz/vibe:latest
cd /opt/services/vibe && sudo docker compose up -d
```

`compose up -d` recreated den Container auf das nun lokal als `:latest`
markierte alte Image. Kein Push, kein CI-Lauf. Danach den fehlerhaften
Commit *auch* via Git revertieren, damit `main` der Realität entspricht
und der nächste Push nicht das gleiche Problem zurückbringt.

**Code-Rollback (Fallback, ~Pipeline-Dauer):**

```bash
git revert <merge-commit>     # auf main
git push origin main          # baut Image neu, redeployt automatisch
```

Dauer = ein Pipeline-Durchlauf (Build+Push+SSH-pull, ~75 s). Bei
schemaneutralen Changes wie T2 reicht ein Code-Revert — die DB muss
NICHT angefasst werden.

**Daten-Rollback (nur falls ein Schema-Change schiefgeht):** App stoppen
→ `leads.db` aus Backup (§4) zurückspielen → vorherigen Code/Image
deployen → starten. Reihenfolge: erst Code/Image zurück, dann Daten,
dann hoch.

---

## 7. Vor „deploy-sicher per Prozess": offene Punkte

| # | Punkt | Warum nötig | Status |
|---|---|---|---|
| D1 | Server-Compose persistiert `leads.db` (Bind/Volume)? | Kernannahme der Datensicherheit | **✅ VERIFIZIERT 2026-05-19 (Bind-Mount, belegt)** |
| D2 | Automatik + getesteter Restore (on-host) | War: 0 Automatik, 9-Tage-Lücke | **✅ ERLEDIGT 2026-05-19 (systemd-Timer, Restore getestet, §4b)** |
| D2b | Off-Host-Automatik (Ziel + Tooling) | Phase 1 = selber Host/Disk; interim manueller Off-Host-Snapshot | **offen — Infra-Entscheidung (§4c)** |
| D3 | `deploy.yml` an Doc-Gate/Probe koppeln + Pre-Deploy-Backup-Hook | Deploy lief sonst auch bei rotem Gate / ohne Sicherung | **✅ ERLEDIGT 2026-05-20** — PR #20 (`verify`-Job, Self-Bootstrap success first try) + serverseitiger `/opt/scripts/deploy.sh`-Hook ruft `vibe-db-backup.sh` vor `compose pull`; `set -e` blockt Deploy bei Backup-Fehler |
| D4 | Immutable Image-Tags (`:sha`/`:datum`) statt nur `:latest` | Schneller Rollback ohne Rebuild | **✅ ERLEDIGT 2026-05-20** — PR #20: `:sha-<short>` zusätzlich zu `:latest`, Rollback-Pfad in §6 |
| D5 | Staging/Smoke-Umgebung (gleiches Image, Kopie der DB) | Migrations real proben ohne Prod-Risiko | **offen, optional** |
| D6 | Migrationsstrategie dokumentiert (s. §8) | Nächster Schema-Change soll nicht ad-hoc sein | **mit dieser Datei adressiert** |

D1–D3 sind die echten Blocker für „wir können beruhigt deployen".
#17/#18 selbst sind **ohne** D1–D5 vertretbar (schemaneutral, 0-Diff,
manuelles Backup §4a als Netz) — die offenen Punkte sind für *künftige*,
insb. schemaverändernde Deploys.

---

## 8. Migrationsstrategie (Alembic, zwei getrennte Bäume)

Etabliert durch Schritt 9 (`docs/adr/010-alembic-split-versioning.md`):
zwei unabhängig versionierte Bäume — `migrations/crm`
(`alembic_version`) + `migrations/billing` (`alembic_version_billing`)
auf derselben SQLite-Datei. Aktuell existiert je nur die **0001-Baseline**
(= altes `create_all`-Schema per Delegation, idempotenter Adopt).

**Regeln für jeden künftigen Schema-Change (nicht T2 — T2 hat keinen):**

1. **Kein impliziter `create_all` mehr.** Jede Schemaänderung = neue
   Alembic-Revision im richtigen Baum (CRM-Tabelle → `migrations/crm`,
   Billing-Tabelle → `migrations/billing`; die Partition ist durch
   `tests/test_db_partition.py` = T3 abgesichert).
2. **Constraint: kein lokaler Interpreter mit App-Deps** → `alembic
   revision --autogenerate` ist lokal nicht lauffähig. Revisionen werden
   **von Hand** geschrieben (wie die 0001-Baseline) und sind
   **CI-verifiziert**, nicht lokal. Review zählt doppelt.
3. **SQLite-Caveat:** SQLite kann `ALTER TABLE` nur eingeschränkt
   (kein DROP/ALTER COLUMN). Für solche Änderungen Alembic **batch
   mode** (`with op.batch_alter_table(...)`) benutzen — sonst bricht der
   Deploy beim Start. Additive Spalten (`ADD COLUMN`) sind unkritisch.
4. **Idempotenz/Adopt beibehalten:** neue Revisionen so schreiben, dass
   ein erneuter Lauf auf bereits migrierter DB No-op ist (Pattern der
   0001-Baseline) — `run_migrations` läuft bei *jedem* App-Start.
5. **Backup ist bei Schema-Changes PFLICHT** (§4a) — der Code-Revert
   allein rettet dann nicht, die DB-Struktur ist schon verändert.
6. **Reihenfolge bei Schema-Change-Deploy:** Backup → PR grün (CI fährt
   die Migration in test-fast/e2e) → Merge → Deploy → `run_migrations`
   beim Start migriert die Prod-DB → Smoke (§5, inkl. Daten-Stichprobe)
   → bei Fehler Daten-Rollback (§6).
7. **Forward-only bevorzugen:** `downgrade()` für SQLite ist fehleranfällig
   (oft Tabellen-Rebuild). Strategie = vorwärts-fixen + Backup-Restore als
   Sicherheitsnetz, nicht auf `alembic downgrade` verlassen.

---

## 9. Empfohlene Reihenfolge (zusammengefasst)

1. ✅ **Erledigt 2026-05-19:** D1 verifiziert (Bind-Mount belegt);
   geprüfter Off-Host-Snapshot gezogen (§4a); D2 Phase 1 installiert +
   Restore getestet (§4b).
2. **#17 → main** → Deploy → Smoke §5. (Schemaneutral, datensicher;
   Backup-Netz steht.)
3. **#18 → main** → Deploy → Smoke §5 (inkl. Notiz-Schreibtest = T2-Pfad).
4. **Fast-follow:** D2b (Off-Host-Automatik, §4c — Infra-Entscheidung) +
   D3 (Deploy-Gate-Härtung). T4–T7 sind schemaneutral (T4 prüft nur den
   Alembic-Pfad, ändert kein Schema) — die Backup-Pflicht greift erst
   beim nächsten echten Schema-Change (§8).
