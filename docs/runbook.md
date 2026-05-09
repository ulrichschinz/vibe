# Runbook — Rechnungs-Modul

Ergänzt die Verfahrensdokumentation um operative Einzelschritte. Dieses
Dokument richtet sich an den Inhaber/Admin, nicht an Steuerprüfer.

## 1. Integritätsprüfung manuell laufen lassen

```bash
# Lokal (auf dem Server)
cd /srv/vibe
.venv/bin/python -m services.invoicing.integrity_check

# Über Make
make integrity-check

# Als JSON für Monitoring
.venv/bin/python -m services.invoicing.integrity_check --json
```

Exit-Codes:
- `0` — alle Hashes konsistent, Kette intakt
- `1` — Mismatch entdeckt → Verfahrensdokumentation §10 Szenario C
- `2` — fataler Fehler (DB nicht erreichbar etc.)

Das Ergebnis wird zusätzlich in `integritycheckrun` persistiert.

## 2. Archivierte Rechnung wiederherstellen

Rechnungen liegen unter `archive/invoices/{YYYY}/{number}.pdf`.

```bash
# Kopie für den Steuerberater
cp archive/invoices/2026/RE-2026-0001.pdf /tmp/

# Hash zum Beleg
cat archive/invoices/2026/RE-2026-0001.sha256
```

Aus einem Backup:

```bash
tar -tzf /backups/vibe-2026-05-09.tar.gz | grep RE-2026-0001
tar -xzf /backups/vibe-2026-05-09.tar.gz \
    --strip-components=2 -C /tmp/restore \
    srv/vibe/archive/invoices/2026/RE-2026-0001.pdf
```

## 3. KoSIT-Validierung debuggen

Falls eine Rechnung im KoSIT-Validator nicht durchgeht:

```bash
# Gespeicherte XML aus dem Archiv ziehen
cp archive/invoices/2026/RE-2026-0001.xml /tmp/

# Validator manuell laufen lassen (jar liegt im KoSIT-Cache)
java -jar .kosit-cache/validator-1.5.0-standalone.jar \
     -s .kosit-cache/scenarios/scenarios.xml \
     /tmp/RE-2026-0001.xml
```

Häufige Ursachen:
- Pflichtfeld fehlt: Issuer-Daten nicht vollständig (siehe `/admin/issuer`).
- Falscher VAT-Code: VAT-Engine hat einen Fall, der noch nicht in R-06 abgedeckt ist → in
  `docs/open-questions.md` dokumentieren.

## 4. VIES-Override-Workflow (R-16)

Wenn beim Finalize einer EU-B2B-Rechnung VIES nicht erreichbar ist:

1. Editor sieht eine Fehlermeldung im UI: „VIES service unavailable".
2. Admin loggt sich ein, geht zur Edit-Seite der gleichen Rechnung.
3. Im UI erscheint nun das Feld „Override-Begründung" (nur für Admins).
4. Admin gibt eine nachvollziehbare Begründung ein („Kunde verifiziert per
   Telefon am 09.05.2026, Vertragsnummer XYZ").
5. Klick auf „Finalisieren" → Override wird mit Begründung in
   `viesauditentry.override_reason` archiviert, Rechnung wird finalisiert.

Begründungs-Best-Practices:
- Datum + Kanal („Telefon", „E-Mail vom …", „Vertrag XYZ")
- Was wurde verifiziert? („USt-IdNr. ATU99999999 stimmt mit Vertrag überein")
- Wer hat verifiziert? („uli@agentic-reach.com")

## 5. Manuelle Produktions-Migration

Da kein Migrations-Tool im Einsatz ist, werden neue Spalten manuell auf der
Server-DB ergänzt:

```bash
# Auf dem Server, vor dem Deploy:
ssh uli@adm.agentic-reach.com
cd /srv/vibe

# DB-Backup vor Migration!
cp leads.db leads.db.backup-$(date +%F-%H%M)

# Schema-Änderungen via SQLite-Shell
sqlite3 leads.db <<EOF
ALTER TABLE lead ADD COLUMN street TEXT;
ALTER TABLE lead ADD COLUMN postal_code TEXT;
-- usw.
EOF

# Container neu starten — bootstrap_admin/bootstrap_issuer + create_db()
# legen alle neuen Tabellen + Trigger an.
docker compose restart vibe
```

Beim ersten Start nach dem Deploy:
1. `/admin/issuer` öffnen, alle Pflichtfelder ausfüllen, speichern.
2. Test-Lead anlegen, Test-Rechnung als Draft → Finalize → PDF prüfen.
3. `make integrity-check` laufen lassen.

## 6. Storno einer Rechnung

UI-Weg: Auf der Rechnungs-Detailseite den Storno-Button mit kurzer Begründung.
Erstellt automatisch eine neue Rechnung mit eigener Nummer, negativen
Beträgen und Verweis auf das Original. Das Original wird auf `cancelled`
gesetzt, bleibt aber unverändert lesbar.

API-Weg:
```bash
curl -X POST -H "X-API-Key: …" \
     -H "Content-Type: application/json" \
     -d '{"reason": "Doppelt berechnet"}' \
     https://vibe.agentic-reach.com/api/invoices/123/storno
```

## 7. Häufige Fehlersuche

| Symptom | Ursache | Lösung |
|---|---|---|
| Finalize blockt mit „IssuerProfile missing fields" | Stammdaten fehlen | `/admin/issuer` ausfüllen |
| Finalize blockt mit „Customer block incomplete" | Lead hat keine Adresse | Adresse am Lead pflegen oder direkt in der Rechnung |
| Finalize blockt mit „Steuernummer or USt-IdNr." | Issuer ist nicht Kleinunternehmer und beides fehlt | Eines pflegen |
| KoSIT-Validator schlägt fehl | Schema-Violation | Siehe §3 |
| Archiv-Datei `PermissionError` | chmod 0444 von vorigen Tests | Tests via `make test` mit Tmp-Dirs nutzen, Prod nicht durcheinanderbringen |
| `database is locked` unter Last | BEGIN IMMEDIATE + busy_timeout | busy_timeout in `database.py` erhöhen wenn nötig |
