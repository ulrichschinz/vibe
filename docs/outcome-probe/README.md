# Outcome-Probe — die plan-eigene Wirksamkeits-Metrik (Audit-Remediation T1)

> Schließt die im Audit (`../audit-report-scaling-roadmap.md`) als
> **komplett übersprungen** befundene Roadmap-„Verifikation" §3. Diese
> Probe misst nicht „ist der Plan konsistent gebaut" (das ist verifiziert)
> sondern **„wirkt er": kann ein Coding-Agent eine repräsentative Aufgabe
> umsetzen und landet die Änderung *exakt* in der vorhergesagten
> Dateimenge — kein random code in random files."**

## Methodik (bewusst streng)

1. **Versiegelung vor jedem Lauf.** Die erwartete Dateiliste je Aufgabe ist
   *vor* irgendeinem Umsetzungslauf in `*.expected` eingecheckt. Ohne das
   ist „vorhergesagt" im Nachhinein wegrationalisierbar (Roadmap-Wortlaut).
   Diese `.expected`-Dateien werden in dem PR committed, der dieses
   Verzeichnis anlegt, **bevor** eine der fünf Aufgaben umgesetzt wird.
   Eine `.expected` nach einem Lauf zu ändern ist ein Integritätsbruch —
   stattdessen: Mismatch als Befund dokumentieren.
2. **Messgröße.** Pro Aufgabe = `git diff --name-only` der Umsetzung
   (geänderte + neue Dateien, repo-relativ). Bestehen = die Menge ist
   **exakt gleich** der `.expected`-Menge: keine fehlende, keine zusätzliche
   Datei. Reihenfolge ist Doku, nicht Gate (Sets vergleichen).
3. **Schwelle.** Je Aufgabe `N = 3` unabhängige Läufe (frische
   Agent-Session, nur Aufgaben-Satz + `CLAUDE.md`/Agent-Edit-Protokoll als
   Input). Bestehen = **3/3** exakt das versiegelte Set **und** `make
   verify` jeder Lauf grün.
4. **Baseline.** Roadmap wollte „Baseline jetzt, Gate nach Schritt 7" —
   beide Zeitfenster sind zu. Rekonstruiert über Git: Referenzbaum
   `4aa4f9a` (letzter Commit vor Schritt 0, pre-Monolith-Split). Die
   Baseline-Dateimengen + die Delta-Analyse stehen in `BASELINE.md`.
   **Ehrliche Einschränkung:** die Baseline ist *post-hoc* erhoben, also
   nicht „zum Zeitpunkt versiegelt" — nur das *Nachher* ist echt sealebar.
   Das mindert die Baseline nicht als Vergleichsgröße (der Strukturzustand
   bei `4aa4f9a` ist faktisch über Git), nur ihre Versiegelungs-Strenge.

## Ehrliche Grenzen dieser Probe (no-local-interp-Realität)

- Es gibt **keinen lokalen Interpreter mit App-Deps** → `make verify` ist
  CI-only. Der Harness (`scripts/outcome_probe.py`) ist **reine stdlib**
  (wie der Doc-Gate) und lokal lauffähig: er prüft nur die *Dateimenge*,
  nicht ob `make verify` grün ist. Letzteres bleibt CI/manuelles Gate.
- „N=3 unabhängige Agent-Läufe" ist prozessual, nicht von CI auszulösen
  (CI kann keinen Agenten beschwören). CI/`make` validieren *pro Lauf*
  den Diff gegen `.expected`; die Wiederholung × 3 ist die Disziplin des
  Ausführenden. Diese Datei + der Harness machen jeden Einzellauf
  *überprüfbar* — das ist der erzwingbare Teil.
- **Die Probe darf Protokoll-Lücken aufdecken.** Wo das dokumentierte
  Agent-Edit-Protokoll (`models → schemas → service → router → test`) eine
  Datei *nicht* vorsieht, die für Korrektheit nötig wäre, wird sie bewusst
  **nicht** in `.expected` aufgenommen — der daraus folgende Prod-Defekt
  ist ein **Befund**, kein Messfehler. Konkret betroffen (siehe
  `.expected`-Annotationen): fehlende Alembic-Revision (Audit R3 / Backlog
  T4) und nicht-gepatchter `independence`-Contract bei neuer Domäne (R6 /
  T5). Die Probe *quantifiziert* damit genau die Lücken, die das Audit
  qualitativ benannt hat.

## Die fünf versiegelten Aufgaben (konkret, eindeutig)

Minimal-repräsentativ gewählt; die exakte Formulierung ist Teil der
Versiegelung (Aufgaben-Drift = Messung-Drift).

| Key | Aufgabe (wörtlich an den Agenten zu geben) |
|---|---|
| `lead-field` | „Füge dem Lead ein optionales Feld `linkedin_url: str \| None = None` hinzu, exponiert über die REST-API (Create + Read + Patch) und das Web-Anlage-Formular." |
| `mcp-tool` | „Füge ein **read-only** MCP-Tool `list_recent_notes(limit: int = 10)` hinzu, das die zuletzt angelegten Notes über alle Leads zurückgibt." |
| `vat-rule` | „Füge der VAT-Bestimmung eine zusätzliche Konstellation hinzu: innergemeinschaftliche B2B-Dienstleistung an einen Kunden ohne valide USt-IdNr → Steuerschuld bleibt beim Issuer (Code `S`), mit Unit-Test." |
| `api-endpoint` | „Füge den REST-Endpoint `GET /api/leads/{lead_id}/notes` hinzu, der die Notes eines Leads als JSON liefert." |
| `new-domain` | „Lege eine neue Domäne `campaigns` an (Web-Router)." |

Erwartete Sets: `<key>.expected`. Baseline + Delta: `BASELINE.md`.

## Ausführung eines Laufs

```bash
# nach Umsetzung einer Aufgabe, im Working-Tree:
make outcome-probe TASK=lead-field        # Diff vs. docs/outcome-probe/lead-field.expected
# exit 0 = Set exakt getroffen; exit 1 = fehlende/zusätzliche Datei (gelistet)
```

`scripts/outcome_probe.py` vergleicht `git diff --name-only` (inkl.
untracked, ohne dieses `docs/outcome-probe/`-Verzeichnis selbst) gegen das
versiegelte Set. `.github/workflows/outcome-probe.yml` validiert zusätzlich,
dass jede `.expected` wohlgeformt ist und der Harness selbst grün läuft.
