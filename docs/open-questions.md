# Offene Punkte / Out of Scope

Stand: 2026-05-09. Bewusst nicht in v1 umgesetzt — mit Begründung.

## ❓ XRechnung-Output (reine XML für öffentliche Auftraggeber)

**Status:** Datenmodell unterstützt es, Renderer ist nicht in v1.

**Begründung:** Auftraggeber ist Einzelunternehmer mit B2B-Beratung; öffentliche
Auftraggeber sind im ersten Jahr nicht zu erwarten. Das `kind`-Enum auf
`Invoice` und der drafthorse-Pfad sind so konzipiert, dass eine
XRechnung-Variante (UN/CEFACT-konform, ohne PDF) als zweiter Renderer
hinzugefügt werden kann, ohne das Datenmodell zu ändern.

**Wann nachholen:** Sobald der erste öffentliche Auftraggeber kommt.

## ❓ EU-B2C-OSS-Schwelle

**Status:** v1 behandelt EU-B2C wie DE-B2C (deutsche USt). Eine Warnung wäre
fairer.

**Begründung:** Der OSS-Mechanismus (One-Stop-Shop) greift erst ab €10.000
EU-Fernverkäufe pro Jahr. Bei dutzenden Beratungs-Rechnungen pro Jahr und
fast ausschließlich DE-Kunden ist das v1 nicht relevant. Die Engine
dokumentiert den Punkt mit einem Kommentar in `vat.py`.

**Wann nachholen:** Wenn EU-B2C ein Thema wird, oder vor Erreichen der
Schwelle.

## ❓ E-Mail-Versand der Rechnung

**Status:** Nicht implementiert. `mark-sent` setzt nur den Status auf `sent`.

**Begründung:** Der Versand erfolgt heute manuell (mit personalisiertem
Anschreiben). Ein automatischer Versand würde Template-Pflege, SMTP-Setup,
Bounce-Handling etc. nach sich ziehen — Aufwand ist im aktuellen Volumen
nicht gerechtfertigt.

## ❓ Mehrwährung

**Status:** `currency='EUR'` hardcoded auf Drafts. Schema kennt das Feld als
Text-Spalte.

**Begründung:** Beratungsumsätze sind in EUR. Falls jemand in CHF/USD abrechnen
will, muss die VAT-Engine entsprechend erweitert werden — kein einfaches
Schema-Update.

## ❓ Mahnwesen / Zahlungseingangs-Erfassung

**Status:** `mark_paid` ist boolean. Kein Mahnlauf, keine offenen Posten,
kein Zahlungseingangs-Matching.

**Begründung:** Bei dutzenden Rechnungen pro Jahr macht ein einfaches
"hab ich Geld gesehen → Klick auf 'Bezahlt'" mehr Sinn als ein vollständiges
OP-Modul. Falls das wachstumsbedingt anders wird, ist ein dedizierter
Payment-Stream (z. B. EBICS, FinTS) angeraten.

## ❓ Filesystem-Immutable-Bit / WORM-Volume

**Status:** Aktuell nur `chmod 0444` + Hash-Chain.

**Begründung:** `chattr +i` auf Linux braucht root-Rechte im Container; ein
Read-Only-Volume erfordert Sidecar-Architektur. Beides ist bei dutzenden
Files pro Jahr Overkill — die Hash-Kette und die DB-Trigger reichen für
gerichtsfeste Manipulationsdetektion.

**Wann nachholen:** Falls eine Audit-Anforderung physische Append-Only
verlangt.

## ❓ Race-Condition-Bug in Angebots-Nummerierung

**Status:** `services/numbering.py:next_proposal_number` benutzt `count()+1`
ohne Lock. Das ist nicht race-safe.

**Begründung:** Bewusst aus dem Scope dieses Auftrags genommen (siehe
ADR-003). Bei dutzenden Angeboten pro Jahr und Single-Worker-Deployment ist
das Risiko gering. Sobald irgendetwas auf Multi-Worker umgestellt wird,
muss das Pattern aus dem Rechnungsmodul (BEGIN IMMEDIATE + Sequence-Tabelle)
übertragen werden.

## ❓ Mutation Testing

**Status:** Setup vorbereitet (`mutmut` in `requirements-dev.txt`), in CI nicht
aktiv.

**Begründung:** Mutation Testing ist auf einem Modul mit ZUGFeRD-XML-Tooling
sehr langsam. Lohnt sich, sobald die Test-Suite stabilisiert ist und
zusätzliche Confidence gesucht wird.

## ❓ veraPDF-Validierung in CI

**Status:** Tests prüfen, dass das Factur-X XML im PDF embedded ist und mit dem
Standalone-XML byte-identisch ist. Eine vollständige PDF/A-3-Konformitäts-
Prüfung mit veraPDF wäre zusätzlich.

**Begründung:** Java-Tooling, das das CI-Bild aufbläht. KoSIT (das primäre
Akzeptanz-Gate) ist in CI verdrahtet; veraPDF wäre Ergänzung.

**Wann nachholen:** Wenn ein Empfänger PDF/A-3-Konformität explizit prüft.
