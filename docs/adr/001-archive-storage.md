# ADR-001: Persistenz finalisierter Rechnungen

**Status:** Akzeptiert (2026-05-09)

## Kontext

R-10 fordert eine GoBD-konforme, append-only Persistenz für Rechnungs-PDFs +
ZUGFeRD-XML über 8 Jahre. R-11 verlangt, dass das beim Finalize erzeugte
Original ausgeliefert wird, nicht ein neu gerendertes Dokument. R-12 verlangt
eine maschinell prüfbare Manipulationsdetektion.

Volumen: dutzende Rechnungen/Jahr — also ein paar hundert Files über 8 Jahre.

## Optionen geprüft

1. **Filesystem mit chmod 0444 + Hash-Kette** *(gewählt)*
2. **Append-Only-DB-Tabelle (BLOB-Spalten) + revoke UPDATE/DELETE für die App-Rolle**
3. **S3-kompatibler Object-Lock-Bucket**
4. **Dediziertes WORM-Volume + Sidecar-Container**

## Entscheidung

**Option 1: Filesystem unter `archive/invoices/{YYYY}/`, files chmod 0444,
plus Hash-Kette in DB und in `_chain.log`.**

## Begründung

- **Einfachheit:** Kein zusätzlicher Service, kein Cloud-Provider-Lock-in. Files
  sind direkt mit `cp`, `tar`, `restic` etc. zu sichern und vom Steuerberater
  abrufbar.
- **Verifizierbarkeit:** Hash-Kette + DB-Trigger erlauben gerichtsfeste
  Detection — physische Unveränderbarkeit ist bei einem Single-Operator-Server
  Overkill.
- **chmod 0444** ist ausreichend gegen versehentliche Edits aus der laufenden
  App. Ein böswilliger Root-User (auf dem Server mit Shell-Zugang) kann
  ohnehin alles, was er will — gegen das Risiko helfen Off-Site-Backups.
- **Volumen:** ~Hundert Files/Jahr; Filesystem-Skalierung kein Thema.

## Konsequenzen

**Positiv:**
- Keine zusätzlichen Infrastruktur-Komponenten.
- Backup-Strategie ist trivial (`tar.gz`).
- Restore funktioniert ohne spezielle Tools.

**Negativ:**
- Kein zentraler Audit-Log auf Filesystem-Ebene (wer hat wann zugegriffen).
  Als Mitigation läuft die Web-App und API auf einem Server mit Auth + Logs;
  direkter SSH-Zugriff ist auf den Inhaber beschränkt.
- `chattr +i` würde stärker schützen, braucht aber Root und ist im Container
  schwer zu administrieren — out of scope für v1.

## Alternativen verworfen

- **DB-BLOB:** Macht Backup-Größe explodieren, ist langsamer beim Lesen, und
  das Tooling für Steuerberater-Exporte (PDF lokal öffnen) wäre umständlicher.
- **S3 Object-Lock:** Cloud-Vendor-Abhängigkeit, monatliche Kosten, und der
  Vorteil (Compliance-Mode) lässt sich auch ohne Cloud erreichen.
- **WORM-Volume:** Erfordert Sidecar, eigenes Volume-Management — Aufwand für
  einen Single-Operator nicht vertretbar.

## Verifikation

- `tests/integration/test_document_renderer.py::test_archive_files_are_readable_only`
  prüft `chmod 0444`.
- `tests/integration/test_integrity_check.py::test_integrity_check_detects_byte_mutation`
  belegt die Hash-basierte Detektion.
