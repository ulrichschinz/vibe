# ADR-012: Scaffold patcht den Independence-Contract (Remediation-Track T5)

**Status:** Akzeptiert (2026-05-20)

## Kontext

Das adversariale Audit (`docs/audit-report-scaling-roadmap.md`, Befund R6)
hielt fest: eine über `make new-domain X` erzeugte 4. Domäne landet in
**0** import-linter-Contracts — der `independence`-Contract listet nur die
drei zur Schritt-8-Aktivierung existierenden Domänen
(`leads`/`proposals`/`billing`) und wird heute nur per *manuellem*
zentralen Eingriff erweitert. Damit skaliert das
Cross-Domain-Enforcement (`domains/<x> ↛ domains/<y>`, die hart gemeinte
Zeile der Contract-Kantentabelle, CLAUDE.md) **nicht** mit dem
Domänen-Satz: Schritt 1 hat den Scaffold-Vertrag „eine Domäne = ein
Befehl, import-linter- und ruff-format-konform by construction"
etabliert; T5 schließt die Lücke an der Contract-Seite. Remediation-Track-
Item **T5** (`docs/remediation-backlog.md`): klein und isoliert, kein
zweistufiger Cut wie T2.

Randbedingung (S4–S9-Lektion, unverändert): **kein lokaler Interpreter
mit App-Deps** → Korrektheit ist CI-verifiziert; lokal nur stdlib-
Doc-Gate + Probe-Lint. Der Scaffold ist selbst stdlib-only (lief
schon vor T5 ohne Interpreter-Deps); diese Eigenschaft bleibt erhalten.

## Entscheidungen

### §A — Scaffold-Verantwortung, nicht Handarbeit

Die Eintragung der neuen Domäne ins `[[tool.importlinter.contracts]]`-
Block `type = "independence"`, `modules = [...]` wandert in
`scripts/new_domain.py`. **Begründung:** Schritt 1 hat den Scaffold als
*den* Anti-„random-files"-Hebel etabliert (`make new-domain X` =
ein Befehl, alles Soll-konform by construction). Eine handarbeitliche
Pflege des Contract-Arrays ist genau das Anti-Pattern, das Schritt 1
beseitigen wollte. Alternative betrachtet (verworfen): pre-commit-Hook
oder separater „contracts-doctor". Beide würden den Scaffold-Vertrag
auflockern (zwei Schritte statt einer) und wiederholen die R6-Pathologie
in einer anderen Schicht.

### §B — Chirurgischer 1-Zeilen-Insert, kein TOML-Roundtrip

Implementierung ist stdlib-only ohne TOML-Roundtrip (kein `tomli_w`,
kein `tomlkit`). **Begründung:** `pyproject.toml` führt mehrzeilige
`#`-Rationale-Kommentare an jedem Contract-Block (das *Warum* lebt
neben dem *Was*, ADR-009 §G-Muster), plus eine spezifische Anordnung,
die ein Roundtrip-Serializer verliert. Stattdessen eine State-Machine
über Zeilen: `[[tool.importlinter.contracts]]` → `type = "independence"`
→ `modules = [` → schließendes `]`; Insert `    "app.domains.<name>",`
direkt vor dem `]`. Idempotenz: Existenz-Check des Ziel-Strings im
Modul-Array (`return False`, kein erneuter Insert). Robustheit: bei
fehlendem Ziel-Block (z. B. abgespeckter Klon) gracefuller No-op,
kein Hard-Fail.

### §C — Nur `independence`, nicht `forbidden`-Contracts

Patcht **nur** den `independence`-Contract — nicht die
`forbidden`-Contracts (S5 billing, S7/S8 MCP, T2 web/REST-Modellsperre).
**Begründung:** `forbidden`-Contracts adressieren *bestehende* Module
(`services.invoicing`, `services.mcp_server`, `app.interfaces`), die der
Scaffold nicht anlegt. Eine neue Domäne unter `app/domains/<x>/` ist
zur `forbidden`-Topologie kein neuer Knoten (die Verbote zeigen *aus*
den schon definierten Quell-Modulen *in* die Domänen — also bereits
über `app.domains.<x>.models` erfasst, sobald die neue Domäne in
`app/domains/` existiert; `grimp`s package-Discovery findet sie über
`root_packages = ["...", "app"]`).

### §D — CI-Smoke-Gate ist `grep`, nicht zweites Tool

CI (`test.yml`, Scaffold-Smoke-Job) prüft den Patch via
`grep -q '"app.domains.scaffoldsmoke"' pyproject.toml` **bevor**
`make … contracts` läuft. **Begründung:** der `make`-Aufruf würde die
Abwesenheit des Contract-Eintrags *nicht* als Fehler zeigen
(`independence` würde dann den Knoten schlicht nicht prüfen — stille
Lücke statt CI-Rot). Der `grep` ist das *deliverable-level* Gate:
„Existiert der Eintrag?". Der nachgelagerte `make … contracts`
verifiziert dann, dass die Domäne den Independence-Pakt nicht verletzt
(d. h. sie kreuzt keine andere Domäne) — das ist die zweite, separate
Frage.

### §E — Cleanup revertiert `pyproject.toml`

Der CI-Smoke-Cleanup-Pfad wurde von `git checkout -- app` auf
`git checkout -- app pyproject.toml` erweitert. **Begründung:** der
Scaffold-Smoke ist throwaway (vor T5: nur `app/`-Edits + generierte
Domänen-Dateien; ab T5: zusätzlich der pyproject-Patch). Ohne Cleanup
würde der Smoke-Lauf den Patch in den Workspace pinnen — kein
Funktionsbruch, aber Disziplin-Verstoß gegen Schritt-1-Zusicherung
„zero edits".

## Konsequenzen

**Positiv:** Cross-Domain-Enforcement skaliert ab sofort mit dem
Domänen-Satz; ein neuer `make new-domain X` ist *vollständig*
contract-abgedeckt, nicht „contract-frei bis jemand pyproject.toml
nachzieht". R6 ist strukturell geschlossen.

**Negativ / akzeptiert:** Der State-Machine-Patcher ist fragiler als
ein TOML-Roundtrip — Layout-Änderungen am `independence`-Block (z. B.
Inline-Array statt Multi-Line) würden ihn brechen. Trade-off bewusst:
der Layout-Verlust eines Roundtrips wäre nach jedem `make new-domain`
sofort sichtbar und schwer rückgängig zu machen; der State-Machine-
Bruch wäre einmalig zu fixen, falls jemand das Layout ändert (und das
ist eine bewusste Maintainer-Aktion, nicht eine Routine-Operation).

**Versiegelt:** Niemand patcht den `independence`-Contract mehr von
Hand. Wer es trotzdem tut (z. B. um eine Domäne *zu entfernen*), ist
in derselben Maintainer-Rolle, die auch den `forbidden`-Contract-
Wortlaut formuliert — Hand-Edit erlaubt, Scaffold-Pflicht nur für
**Hinzufügen** (das ist der R6-Hebel).

## Verifikation

- Lokal (stdlib-only, ohne App-Deps): `python3 scripts/new_domain.py
  scaffoldsmoke` → 1-Zeilen-Diff in `pyproject.toml`; zweiter Lauf
  (`--force`) erzeugt **denselben** Diff (keine Duplikate).
- CI (PR-Gate): `grep -q '"app.domains.scaffoldsmoke"' pyproject.toml`
  vor `make … contracts`; danach Cleanup über `git checkout -- app
  pyproject.toml`.
- Doc-Gate: 0-Diff (Änderungen liegen in `scripts/` —
  `_EXCLUDED_DIRS` von `check_architecture_metrics.py` — und in
  `.github/`/`docs/`/`pyproject.toml`, keine davon ist Python-LOC).
- Probe-Lint: 0-Diff (T5 berührt keine Probe-`.expected`-Dateien).

## Referenzen

- Audit-Befund R6: `docs/audit-report-scaling-roadmap.md`
- Backlog-Item T5: `docs/remediation-backlog.md`
- Scaffold-Vertrag (Schritt 1): `CLAUDE.md` § Scaffold-Nutzung
- Contract-Kantentabelle (Independence-Zeile): `CLAUDE.md`
- Schwester-ADRs: ADR-007 (Billing-Edge), ADR-008 (MCP-Edge),
  ADR-009 (Interface-Split), ADR-011 (T2 Web/REST-Modellsperre)
