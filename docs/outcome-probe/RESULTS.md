# Outcome-Probe — Ergebnisse

## Validierungslauf 2026-05-19 (N=1 je Aufgabe, Methodik-Validierung)

Zweck: prüfen, ob die *vor* jedem Lauf versiegelten `.expected`-Sets in
einem echten Agent-Edit-Protokoll-Lauf **exakt** getroffen werden. In
isoliertem Throwaway-Klon; die `.expected`-Dateien wurden **nach** Sicht
der Ergebnisse **nicht** verändert (Integritätsregel der README).

| Aufgabe | Sealed | Changed | Ergebnis |
|---|---|---|---|
| `new-domain` (`make new-domain campaigns`) | 8 | 8 | **PASS — Set exakt** |
| `lead-field` (faithful Agent-Edit-Protokoll-Umsetzung) | 7 | 7 | **PASS — Set exakt** |

Belege: `scripts/outcome_probe.py <task>` → exit 0, „PASS: changed-file
set is exactly the sealed prediction" für beide. `lead-field` bestand
**weil** die Vorhersage die R1-Interface-Steuer bereits einkalkuliert
(`web/leads.py` + `api/router.py` statt `service.py` — der REST-Create
konstruiert `Lead(` feldweise, also erzwingt ein neues Feld eine
Interface-Änderung) und die R3-Migration **bewusst auslässt** (Protokoll
kennt keinen Migrations-Schritt) — beides dokumentierte Befunde, keine
Messfehler.

**Befund (Methodik-Ebene):** Die Soll-Struktur macht die Dateimenge aus
Protokoll + Struktur **vorab exakt ableitbar** — die Kern-These des Plans
hält für die zwei geprüften Aufgaben. Gleichzeitig **quantifiziert** die
Probe die Audit-Befunde: das exakte Treffen schließt R1/R3/R6 *nicht* —
„Agent landet exakt dort" ist wahr, „die Änderung ist damit
vollständig/erzwungen-konsistent" nicht (s. `.expected`-Annotationen,
`BASELINE.md`).

## Was damit erbracht ist — und was nicht (ehrlich)

**Erbracht:** versiegelte Vorhersagen + rekonstruierte Baseline + Delta +
lokal lauffähiger Harness + CI-Wohlgeformtheits-Gate + empirische
Methodik-Validierung (2/5 Aufgaben, N=1, beide exakt). Das ist der Teil
mit Integritätsanforderung (Versiegelung vor Lauf) und der lokal
beweisbare Teil.

**Nicht erbracht (verbleibende Disziplin, CI/manuell — no-local-interp):**
- Volle Schwelle **N=3 je Aufgabe** über alle 5 Aufgaben (frische
  unabhängige Agent-Sessions) — prozessual, nicht von CI auslösbar.
- **`make verify` grün je Lauf** — CI-only (kein lokaler Interpreter mit
  App-Deps; dieselbe dokumentierte Randbedingung wie der gesamte Plan).
- `mcp-tool`, `vat-rule`, `api-endpoint` empirisch noch ungeprüft (nur
  analytisch versiegelt).

Damit ist die im Audit als *komplett übersprungen* befundene
Wirksamkeits-Verifikation **etabliert und zu ~2/5 empirisch validiert**,
nicht mehr nur behauptet — die volle 3/3×5-Schwelle bleibt als laufende,
jetzt *überprüfbare* Disziplin (Harness + Gate existieren).
