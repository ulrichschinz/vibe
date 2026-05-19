# Fortsetzungs-Prompt — Scaling-Roadmap-Audit-Remediation

> Diesen Text als Start-Prompt einer frischen Session verwenden (Kontext
> wurde bewusst gelöscht). Single Sources of Truth sind die unten
> genannten Dateien + das persistente Memory `scaling-roadmap-progress` —
> denen vertrauen, nicht diesem Prompt paraphrasieren.

---

Du setzt eine Audit-Remediation in `/Users/uli/projects/agentic-reach/vibe`
fort. Vorgeschichte (alles bereits passiert, nachlesbar):

- Ein 9-Schritte-Scaling-Roadmap-Umbau (Schritte 0–9 gemerged) wurde
  **adversarial auditiert**. Befund: `docs/audit-report-scaling-roadmap.md`.
  Kurz: korrekt & wie geschrieben ausgeführt, aber Wirksamkeit war unbelegt
  (Outcome-Probe übersprungen) + zentrale Anti-Pattern-Sperre für Web/REST
  nicht erzwungen + Schema-Evolution/Partition/neue-Domäne hängen an
  Disziplin statt Gates.
- Daraus abgeleitet: `docs/remediation-backlog.md` — **das ist deine
  Arbeitsliste** (T1–T7 als ausführbare Gates, E1/E2 entschieden).
- **Entscheidungen (fix, nicht neu aufrollen):** E1 = Move-not-rewrite-
  Decke/Schuld 6 *akzeptiert mit Revisit-Trigger*, kein Abbau-Schritt
  (kein T8). E2 = Roadmap bleibt **eingefroren Rev. 2**; Remediation ist
  ein **separater Track** (kein Rev. 3). `docs/scaling-roadmap.md` ist
  historischer Record, nicht anfassen.

## Status

- **T3 erledigt:** `tests/test_db_partition.py` (CRM/Billing-Partition ==
  `SQLModel.metadata.tables` + disjunkt). ARCHITECTURE.md-Kennzahlen
  mitgezogen (Tests 3.380→3.425 / gesamt 11.871→11.916).
- **T1 erledigt + 2/5 empirisch validiert:** `docs/outcome-probe/`
  (README-Spec, 5 **versiegelte** `*.expected`, `BASELINE.md`,
  `RESULTS.md`) + stdlib-Harness `scripts/outcome_probe.py` +
  `make outcome-probe TASK=x` + CI `outcome-probe.yml`. Validierungslauf
  N=1: `new-domain` 8/8 + `lead-field` 7/7 exakt.
- **Alles ist UNCOMMITTED.** `git status` zeigt: `M ARCHITECTURE.md`,
  `M Makefile`, neu `docs/audit-report-*`, `docs/remediation-backlog.md`,
  `docs/NEXT-SESSION-PROMPT.md`, `docs/outcome-probe/`,
  `scripts/outcome_probe.py`, `tests/test_db_partition.py`,
  `.github/workflows/outcome-probe.yml`, `docs/audit-prompt-*`.
  **Erste Entscheidung mit dem User klären:** committen (Vorschlag: ein
  PR „Audit-Remediation: T3 + T1 + Backlog"), oder weiterarbeiten und
  später bündeln. Nichts ohne explizites Go committen/pushen.

## Nächste Aufgabe: **T2** (P0, der eigentliche Strukturhebel)

Web/REST-Modellsperre — schließt Audit-Befund R1, liefert „eine Logik,
drei Clients". Zweistufig, **T2a blockt T2b**. Vollständige Spec:
`docs/remediation-backlog.md` §T2. Kern:

- **T2a (Bestand-Refactor):** Modell-Konstruktion aus `app/interfaces/web/*`
  + `app/interfaces/api/router.py` in die jeweiligen
  `app/domains/*/service.py` umleiten. Vor Umsetzung **volle grep-Inventur**
  (`grep -rn 'Lead(\|Note(\|Invoice(\|User(\|Proposal(' app/interfaces/`).
  Bekannte Sites: `web/leads.py:281,502`, `web/invoices.py:133`,
  `web/admin.py:72`, `api/router.py:89,238`. `User(...)` hat keine Domäne
  → Zuhause klären (`app/core/identity`-Service o. Admin-Service).
  **Invariante:** 132 Characterization-Tests + 90 %-Invoicing 0-Diff.
- **T2b (Gate):** `[[tool.importlinter.contracts]]` forbidden,
  `source_modules=["app.interfaces"]`,
  `forbidden_modules=["app.domains.leads.models","app.domains.proposals.models","app.domains.billing.models"]`,
  `allow_indirect_imports="True"`.

Danach (P1) T4/T5 parallel, dann (P2) T6/T7. T4/T5/T6/T7-Specs ebenfalls
in `docs/remediation-backlog.md`.

## Harte Constraints (gelten immer, nicht verletzen)

- **Kein lokaler Interpreter mit App-Deps.** `make verify` ist CI-only.
  Einziger lokaler Hebel: stdlib-Skripte —
  `python3 scripts/check_architecture_metrics.py` (Doc-Gate) und
  `python3 scripts/outcome_probe.py --lint`. Beide müssen grün bleiben.
- **Doc-Gate-Disziplin:** jede `.py`-Änderung **außerhalb `scripts/`**
  (scripts/ ist LOC-excluded) verschiebt Kennzahlen → ARCHITECTURE.md im
  **selben Change** synchronisieren, sonst CI rot. Zahlen via Doc-Gate
  prüfen.
- **`services/invoicing/` ist move-not-rewrite** (Compliance, 90 %-Netz).
  Nur additive Änderungen, nie umschreiben.
- **Outcome-Probe-Integrität:** `docs/outcome-probe/*.expected` sind
  versiegelt — **niemals nach einem Lauf editieren**; ein Mismatch ist ein
  Befund, kein Anlass zur Korrektur der Vorhersage.
- Agent-Edit-Protokoll + Contract-Kantentabelle: `CLAUDE.md`. Memory
  `scaling-roadmap-progress` (+ `MEMORY.md`-Index) hat den vollen
  Verlaufsstand — zuerst lesen.

Beginne damit, den Status zu verifizieren (`git status`,
`docs/remediation-backlog.md` lesen, Doc-Gate + Probe-Lint grün prüfen),
die Commit-Frage mit dem User zu klären, dann T2a in Angriff zu nehmen.
