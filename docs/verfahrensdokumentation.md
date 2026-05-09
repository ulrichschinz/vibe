# Verfahrensdokumentation — Rechnungsstellung (vibe)

> **GoBD-Pflichtdokument.** Zielgruppe: Steuerprüfer, externe Auditoren, Inhaber.
> Beschreibt verbindlich, *wie* Rechnungen erstellt, gespeichert und vor
> Manipulation geschützt werden, sowie die organisatorischen Rahmenbedingungen.
>
> Stand: 2026-05-09. Verantwortlich: Ulrich Schinz, Agentic Reach.

## 1. Anwendungsbereich

Diese Dokumentation gilt für das Rechnungsmodul des CRM-Systems „vibe" (FastAPI,
Python 3.12, SQLite). Sie deckt §§ 14, 14a UStG, UStDV sowie die GoBD ab und ist
auf die kommende E-Rechnungspflicht (ZUGFeRD/Factur-X) ausgelegt.

Nicht in Scope: Buchhaltung, Steuererklärungen, Lohnabrechnung. Diese werden
extern (Steuerberater) verarbeitet — Rechnungs-Originale (PDF + XML) werden auf
Verlangen exportiert.

## 2. Workflow einer Rechnung

### 2.1 Status-Übergänge (State Machine)

```
draft ─finalize──► finalized ──mark-sent──► sent ──mark-paid──► paid
                       │                      │                    │
                       └─storno─► cancelled  ─┴─storno─► cancelled ┘
```

- `draft` — Editierbar, noch keine Rechnungsnummer.
- `finalized` — Nummer vergeben, PDF + XML im Archiv, unveränderlich (R-03).
- `sent` — Versendet (Versand außerhalb des Systems, Status manuell gesetzt).
- `paid` — Bezahlung erfasst.
- `cancelled` — Per Storno-Rechnung aufgehoben (R-05).

Übergänge sind in `services/invoicing/state_machine.py` explizit kodiert.
Versuche, eine ungültige Transition durchzuführen (z. B. `paid → sent`),
werden mit `InvoiceStateError` abgelehnt.

### 2.2 Erstellungsablauf

1. Anwender erstellt einen Entwurf via Web-UI (`/invoices/new`), API
   (`POST /api/invoices/draft`) oder MCP-Tool (`create_invoice_draft`).
2. Positionen werden hinzugefügt (Beschreibung, Menge, Einheit, Einzelpreis,
   USt-Satz).
3. **Finalisieren:** Validierung (R-01), Stamm­daten-Snapshot (R-04),
   USt-Berechnung (R-06), VIES-Check bei Reverse-Charge (R-16),
   Nummernvergabe (R-02), Hash-Berechnung (R-12), Archivierung (R-10),
   Status-Übergang `draft → finalized`.
4. PDF + XML stehen unter `/invoices/{id}/pdf` und `/invoices/{id}/xml` zum
   Download bereit (nur eingeloggte Benutzer).
5. Versand erfolgt manuell außerhalb des Systems; `mark-sent` setzt nur den
   Status.

## 3. Nummernkreis (R-02)

**Format:** `RE-{YYYY}-{NNNN}` mit vierstelliger, je Geschäftsjahr lückenloser
Folge (z. B. `RE-2026-0001`). Eigener Prefix, getrennt vom Angebots-Prefix
`AR-`.

**Vergabe:**

```
1. Beim Finalize wird auf der Connection BEGIN IMMEDIATE ausgeführt
   (SQLite-Reservedlock). busy_timeout=5000 ms.
2. Die Tabelle invoicenumbersequence enthält pro Geschäftsjahr genau eine
   Zeile mit dem zuletzt verbrauchten Counter.
3. last_sequence wird inkrementiert und in derselben Transaktion mit der
   neuen Invoice-Zeile committet.
4. Bei Fehlern vor COMMIT führt SQLite ein vollständiges Rollback durch,
   keine Nummer wird verbraucht.
```

**Lückenlosigkeit-Beweis:**
- Eine `UNIQUE(fiscal_year, sequence_number)`-Constraint verhindert Duplikate.
- Concurrency-Test (`tests/integration/test_numbering_concurrency.py`) startet
  30 parallele Threads, die alle `assign_next_number` aufrufen; das Ergebnis
  ist bei jedem Lauf eine dichte Folge `1..30` ohne Doppler.
- Da die Nummer nur innerhalb der Finalize-Transaktion vergeben wird und
  Failures vor COMMIT zurückrollen, kann zwischen aufeinanderfolgenden
  finalisierten Rechnungen keine Lücke entstehen, solange das Archiv-
  Verzeichnis schreibbar ist (siehe Notfall-Konzept §10).

## 4. Unveränderbarkeit (R-03)

Drei aufeinander aufbauende Schutzschichten:

### 4.1 Datenbank-Trigger (primär)

Ein `BEFORE UPDATE`-Trigger auf der Tabelle `invoice` blockiert jegliche
Änderung an den geschützten Spalten (Nummer, Daten, Beträge, Snapshots,
Hashes, …) sobald `OLD.status != 'draft'`. Analoge Trigger auf
`invoicelineitem` blockieren INSERT/UPDATE/DELETE auf Lines, deren Parent-
Invoice nicht mehr im Draft-Status ist.

Definition siehe `database.py:_install_invoice_triggers`.

### 4.2 SQLAlchemy-Event-Listener (sekundär)

`services/invoicing/immutability.py` registriert `before_update`-Listener,
die noch vor dem SQL-Versand prüfen und mit `ImmutableInvoiceError` brechen.
Liefert eine bessere Fehlermeldung; die DB-Trigger sind die letzte
Verteidigungslinie.

### 4.3 Hash-Kette (Detection)

Jede finalisierte Rechnung hält einen sha256-Hash über
`pdf_bytes + xml_bytes + canonical(header)` und einen Hash der vorigen
Rechnung im selben Geschäftsjahr (Genesis: `sha256("genesis-invoice-chain-{year}")`).
Eine spätere Manipulation an Archiv-Datei oder DB-Zeile lässt sich durch den
Integrity-Check (siehe §6) zuverlässig nachweisen.

## 5. Speicherorte und Aufbewahrung (R-10, R-11)

```
archive/invoices/{YYYY}/{number}.pdf
archive/invoices/{YYYY}/{number}.xml
archive/invoices/{YYYY}/{number}.sha256      # Klartext-Quittung
archive/invoices/{YYYY}/_chain.log           # Append-Only-Tab-Log
leads.db                                     # SQLModel + Hash-Kette + Audit
```

**Originale, nicht regenerieren:** Beim Finalize werden PDF und XML einmal
erzeugt und im Archiv abgelegt. Spätere Anzeige (z. B. Download über
`/invoices/{id}/pdf`) liefert das **gespeicherte Original**, niemals einen
neu gerenderten Inhalt. Validiert durch
`tests/integration/test_document_renderer.py::test_render_pdf_a3_with_embedded_xml`
(Hash bleibt konstant zwischen Finalize und späterem Lesen).

**WORM-Strategie:**
1. **DB-Trigger** + Hash-Kette (primäre Detektion bei Manipulation).
2. **`chmod 0444`** auf Archiv-Dateien direkt nach dem Schreiben — Edits aus
   der laufenden App scheitern mit `PermissionError`.
3. (Optional, manuell zu Jahresende:) `chmod 0555` auf das Year-Directory,
   sodass keine neuen Files mehr darin landen können.

**8-Jahres-Aufbewahrung:** Der Ordner `archive/invoices/` wächst linear
(erwartet: ~Hundert Files pro Jahr). Es ist kein Tooling notwendig — die
Files bleiben einfach liegen. Backup siehe §7.

## 6. Integritätsprüfung

CLI: `make integrity-check` → `python -m services.invoicing.integrity_check`.

Was passiert:
1. Alle finalisierten Rechnungen werden geordnet nach `(fiscal_year, sequence)` gelesen.
2. Pro Rechnung: `recompute_invoice_hash(pdf_bytes, xml_bytes, header)` wird mit
   dem in der DB gespeicherten Hash verglichen.
3. `verify_chain` prüft pro Geschäftsjahr, dass jede Rechnung den `hash_sha256`
   ihres Vorgängers in `hash_prev` führt.
4. Ergebnis wird in der Tabelle `integritycheckrun` mit Zeitstempel,
   Anzahl gescannter Rechnungen, JSON-Mismatches und Status (`ok | mismatch | error`)
   protokolliert.
5. Exit-Code `0` (alles ok), `1` (Mismatch), `2` (fataler Fehler).

**Empfehlung:** Cron-Job auf dem Server (täglich, frühmorgens), Alarm bei
Exit-Code != 0 via Mail/Slack.

Manipulationsprobe:
- Test `test_integrity_check_detects_byte_mutation` mutiert ein Byte in einer
  archivierten PDF → Check geht rot.
- Test `test_integrity_check_detects_missing_file` löscht eine Archiv-Datei →
  Check geht rot.

## 7. Backup & Wiederanlauf

**Empfohlene Strategie (außerhalb der App, dokumentiert hier):**

```
# Tägliches Backup von Archiv + DB (z. B. via cron auf adm.agentic-reach.com)
0 4 * * * tar -czf /backups/vibe-$(date +%F).tar.gz \
    /srv/vibe/archive /srv/vibe/leads.db
# Retention: 90 Tage täglich, 24 Monate monatlich, 8+ Jahre jährlich.
```

**Restore-Test** (mindestens jährlich):
1. Backup-Archiv auspacken in eine Staging-Umgebung.
2. Container starten, `make integrity-check` laufen lassen.
3. Letzte fünf Rechnungen über das Web-UI öffnen → PDF/XML sichtbar.

## 8. Berechtigungs- und Zugriffskonzept

**Rollen** (`UserRole`-Enum):

| Rolle    | Rechte rund um Rechnungen |
|----------|-----------|
| `viewer` | Liste + Detail lesen, PDF/XML herunterladen |
| `editor` | + Drafts anlegen, finalisieren, sent/paid/storno setzen |
| `admin`  | + IssuerProfile pflegen, VIES-Override mit Begründung, Audit einsehen |

**Auth-Wege:**
- **Web-UI:** Session-basiert (`SessionMiddleware`, signiert mit `SECRET_KEY`).
- **REST-API** (`/api/invoices/...`): `X-API-Key`-Header gegen DB-gespeicherte
  SHA-256-Hashes von Schlüsseln (verwaltet unter `/admin/api-keys`).
- **MCP** (`/mcp/...`): Identische Header-Auth, geprüft im ASGI-Wrapper in
  `routes/mcp.py`.

**Audit:**
- VIES-Validierungen werden in `viesauditentry` geloggt (jede Antwort,
  unabhängig vom Ergebnis). Zugriff via `/admin/vies-overrides` (admin-only).
- Jede `finalize`-Aktion erzeugt einen `IntegrityCheckRun`-Eintrag (manuell
  via CLI/Cron triggerbar).

## 9. Datenmodell (Auszug)

| Tabelle | Zweck |
|---|---|
| `invoice` | Header (Status, Nummer, Snapshots, Totals, Hashes, Archivpfade) |
| `invoicelineitem` | Positionen (mit Decimal-Beträgen, USt-Code) |
| `invoicenumbersequence` | Counter pro Geschäftsjahr |
| `viesauditentry` | Jede VIES-Antwort, inkl. Override-Begründung |
| `integritycheckrun` | Audit-Trail der Integritätsprüfungen |
| `issuerprofile` | Singleton mit Aussteller-Stamm­daten |

Vollständige Definitionen in `models.py`.

## 10. Notfall- und Wiederanlaufkonzept

**Szenario A — Archiv-Volume nicht beschreibbar.**
Symptom: Finalize wirft `PermissionError`. Aktion: keine Nummer wird vergeben
(Rollback). Admin behebt Permissions auf dem Volume; Finalize wird wiederholt.
Lückenlosigkeit bleibt gewahrt, da der Counter erst beim COMMIT verbraucht wird.

**Szenario B — Datenbank zerstört, Backup eingespielt.**
Aktion: `make integrity-check` direkt nach dem Restore. Mismatches deuten auf
unvollständigen Restore (z. B. nur DB ohne Archiv). Beheben, dann erneut prüfen.

**Szenario C — Manipulation entdeckt (Hash-Mismatch).**
Aktion: Vorfall in `docs/incidents/{date}.md` dokumentieren, Backup desselben
Tages einspielen, betroffene Rechnungen erneut prüfen, Steuerberater informieren.

**Szenario D — VIES dauerhaft offline.**
Aktion: Admin-Override mit Begründung erlaubt das Finalisieren von EU-B2B-
Rechnungen. Die Override-Begründung wird in `viesauditentry.override_reason`
unveränderlich archiviert (R-16). Sobald VIES wieder verfügbar, prüfen ob ein
Nachtrag (z. B. Rechnungsstorno + Neuausstellung) angezeigt ist.

## Anlagen

- ADR-001 bis ADR-006 unter `docs/adr/` — Architektur-Entscheidungen mit Begründung.
- Runbook unter `docs/runbook.md` — operative Einzelschritte.
- Offene Punkte unter `docs/open-questions.md`.
