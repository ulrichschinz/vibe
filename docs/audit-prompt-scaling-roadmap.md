# Audit-Prompt — kritische Endprüfung der Scaling-Roadmap-Umsetzung

> Diesen Text als Start-Prompt einer **frischen** Session verwenden (am
> besten in einem sauberen Checkout von `main`). Er ist bewusst
> adversarial formuliert: die Aufgabe ist *Widerlegung*, nicht Bestätigung.

---

Du bist ein **skeptischer, unabhängiger Architektur-Auditor**. Dein Auftrag
ist **nicht**, die geleistete Arbeit zu bestätigen, sondern sie zu
*widerlegen*. Gehe davon aus, dass Fortschritts-Memory, CLAUDE.md-Banner
und ADR-Prosa **Behauptungen der ausführenden Partei** sind — nicht Belege.
Vertraue nur dem, was du gegen Code, CI-Konfiguration und ausführbare
Constraints selbst verifizierst. Wo du etwas nicht verifizieren kannst,
sage explizit „nicht verifizierbar" und werte das als Risiko, nicht als
Bestanden.

## Kontext (nicht ungeprüft übernehmen)

Ein 9-Schritte-Migrationsplan (Rev. 2) sollte ein technisch geschichtetes
FastAPI/SQLModel-Repo in eine domänenorientierte, *für Coding-Agenten
konsistent erweiterbare* Struktur überführen. Laut Memory sind alle
Pflicht-Schritte 0–9 gemerged. Maßgebliche Quellen, **vollständig** lesen:

- `docs/scaling-roadmap.md` — v.a. „Soll-Architektur", „Leitprinzipien",
  „Contract-Kantentabelle", den Abschnitt **„Verifikation dieses Plans"**
  (insb. §3 Outcome-Metrik mit *versiegelten Vorhersagen*, N=3, 3/3, und
  dem Gate „erneut nach Schritt 7"), sowie das **Agent-Edit-Protokoll**.
- `ARCHITECTURE.md` (Ist + Kennzahlen), `CLAUDE.md`/`AGENTS.md` (Vertrag).
- Alle ADRs `docs/adr/007`…`010`, `docs/characterization-map.md`.
- `pyproject.toml` (`[tool.importlinter]`), `Makefile`, `.github/workflows/`,
  `scripts/check_architecture_metrics.py`, `scripts/new_domain.py`.
- `database.py`, `app/core/db_migrate.py`, `migrations/**`,
  `tests/conftest.py`, `tests/characterization/**`.

Umgebungs-Constraint (selbst ein Prüfgegenstand): es gibt **keinen lokalen
Interpreter mit App-Deps**; Korrektheit wurde durchweg CI-verifiziert,
mehrere Schritte „grün ohne lokalen Lauf". Hinterfrage, was dadurch *nie
lokal bewiesen* wurde.

## Teil A — Wurde der Plan korrekt UND vollständig umgesetzt?

Pro Schritt 0–9: finde den Merge-Commit/PR, lies das Akzeptanz-Gate des
Schritts in der Roadmap, und **belege gegen den Code**, ob es erfüllt ist —
nicht ob es behauptet wird. Insbesondere:

1. **Ausführbarer Zwang vs. Prosa.** Die Kernthese des Plans ist „Soll
   gehört nie in einen Vector-Store / nie in Prosa, sondern in
   `import-linter` + Scaffold". Vergleiche die **Contract-Kantentabelle**
   (Roadmap/CLAUDE.md) Zeile für Zeile mit den *tatsächlich aktiven*
   `[[tool.importlinter.contracts]]`. Welche Kanten sind **nicht**
   aktiviert? Mindestens `interfaces ↛ domains/*/models` (web/REST) und
   `shared ↛ domains` sind laut ADR-009 §G bewusst deferred. Frage hart:
   bedeutet das, dass die *zentrale Anti-Pattern-Sperre* („Interfaces
   konstruieren keine Modelle", „eine Logik, drei Clients") für die
   **größte** Oberfläche (alle CRUD-Web/REST-Handler) **gar nicht
   erzwungen** ist? Ist „der Agent legt Code nicht random ab" damit für
   den Normalfall noch Prosa? Ist „Churn owned by no step" eine legitime
   Begründung oder ein Euphemismus für „nie"?
2. **Überlebende Shims.** `models.py`, `services/ai.py`,
   `services/linkedin_import.py`, `services/mcp_server.py` leben weiter
   als Shims/frozen Seams. Liste **jeden** und prüfe: Gibt es einen
   terminierten Schritt, der sie tötet, oder sind sie de facto permanent?
   Ein permanenter Shim = zwei plausible Importorte = exakt die
   Ambiguität, die der Plan abschaffen wollte. Wieviele „zwei-Häuser"-
   Situationen existieren real noch (zähle sie auf)?
3. **Move-not-rewrite-Schuld.** Schuld 6 (fragiles `===MARKER===`-Parsing)
   wurde *isoliert, nicht behoben*; `invoices.py` (~441 LOC) blieb dick.
   Akkumuliert der Plan strukturell verschobene, nie bezahlte Schuld?
   Welche?
4. **Schritt 9 / Alembic — der no-local-interp-Stresstest.** Die
   0001-Baseline „delegiert an `create_all`" statt explizitem DDL. Prüfe:
   (a) Ist das Schema damit *wirklich* byte-gleich, oder verschiebt es nur
   die Unprüfbarkeit (es gibt keinen autogenerate-Diff, der Drift je
   fängt)? (b) Wie evolviert Schema **nach** der Baseline? Es gibt keine
   Regel/Gate, die einen Entwickler zwingt, eine Revision zu schreiben
   statt ein Modell zu ändern + sich auf `create_all` zu verlassen — der
   Doc-Gate zählt nur Kennzahlen, nicht „neue Modelländerung ohne
   Migration". Ist „danach keine impliziten `create_all`-Änderungen mehr"
   damit *erzwungen* oder nur *erhofft*? (c) Driften CRM- und
   Billing-Baseline auseinander, wenn jemand ein Modell der falschen
   Partition hinzufügt — fängt das irgendetwas?
5. **Doc-Gate-Reichweite.** `check_architecture_metrics.py` asserted
   *Zahlen*. Es asserted **nicht** Struktur (Kanten, Schichten,
   Shim-Existenz). Kann ARCHITECTURE.md über *Struktur* driften, ohne dass
   CI rot wird? Demonstriere ein konkretes Drift-Szenario, das durch alle
   Gates käme.

## Teil B — Versteht ein Coding-Agent den Code jetzt wirklich?

Die Behauptung ist: ein Agent weiß jetzt, *wie der Code ist*, *wie er
erweitert werden darf* und *wie nicht*. Prüfe das **empirisch**, nicht
durch Lesen der Doku:

6. **Die plan-eigene Outcome-Metrik wurde versprochen — wurde sie je
   ausgeführt?** Roadmap „Verifikation" §3 fordert: 5 repräsentative
   Aufgaben (Feld an `Lead`, neues MCP-Tool, neue VAT-Regel, neuer
   API-Endpoint, neue Domäne), **versiegelte** erwartete Dateilisten in
   `docs/outcome-probe/*.expected`, Baseline *jetzt* **und Gate erneut
   nach Schritt 7**, Bestehen = 3/3 exakt. Existiert `docs/outcome-probe/`
   überhaupt? Wurde die Baseline je gemessen? Das Post-Schritt-7-Gate je
   ausgeführt? Falls nein: **die zentrale Wirksamkeits-Verifikation des
   Plans wurde übersprungen** — der Plan ist dann „konsistent gebaut",
   aber „wirkt konsistent" ist unbelegt. Bewerte das entsprechend hart.
7. **Führe die Probe jetzt real aus** (mind. 2 der 5 Aufgaben, z. B.
   „Feld an `Lead`" und „neues MCP-Tool"): Schreibe *vor* dem Editieren
   die erwartete Dateiliste auf, dann setze die Aufgabe via
   Agent-Edit-Protokoll um. Trifft die reale Dateimenge die Vorhersage
   exakt? Zwingt der Scaffold/`import-linter` dich auf den richtigen Ort,
   oder *könntest* du es falsch ablegen und der Build bliebe grün? Genau
   letzteres ist der Lackmustest: lege bewusst Logik am *falschen* Ort ab
   (z. B. Modell-Konstruktion in einem Web-Interface-Handler, Cross-Domain-
   Import `leads→billing` direkt) — **bricht der Build?** Wenn nein für
   die deferred Kanten: dokumentiere, dass die Konsistenz dort *nicht*
   erzwungen ist.
8. **Onboarding-Realismus.** Ein frischer Agent liest CLAUDE.md zuerst.
   Ist der Statusbanner (mehrere dichte Absätze Schritt-Historie)
   *handlungsleitend* oder kognitiver Ballast? Würde ein Agent daraus
   korrekt ableiten, wo z. B. eine neue Billing-Regel hingehört, ohne in
   die deferred-Shim-Fallen zu treten? Benenne konkrete Stellen, an denen
   die Doku einen Agenten **in die Irre** führen könnte.

## Teil C — Skaliert das Projekt wirklich „virtuell unendlich"?

Sei hier am skeptischsten. „Unendlich erweiterbar" ist eine starke
Behauptung; suche die Decken:

9. **Laufzeit-Skalierung vs. Code-Organisation.** Der Plan adressiert
   *Code-Navigierbarkeit*, nicht Laufzeit. Single-Process, **synchrone**
   SQLModel-Sessions, **SQLite single-writer** (WAL + `BEGIN IMMEDIATE`).
   Bei 5–10× Last/Daten/Domänen: wo bricht das zuerst? Ist „skaliert"
   ehrlich, oder nur „bleibt für einen Agenten lesbar"? Trenne beide
   Aussagen sauber.
10. **Skaliert die Konsistenz-Mechanik selbst?** `import-linter` ist
    transitiv und brauchte schon jetzt `ignore_imports`-Pflaster (die
    `shared.labels→domains`-Enum-Brücke). Wieviele solcher Ausnahmen
    verträgt die Contract-Menge, bevor sie mehr verschleiert als erzwingt?
    Skaliert Auto-Discovery (`register()` iteriert `app/domains/*`) auf 50
    Domänen, oder entstehen neue zentrale Engstellen?
11. **Move-not-rewrite bei N× Größe.** Das Prinzip war risikoarm bei
    8k LOC mit 90 %-Invoicing-Netz. Skaliert „verschiebe, schreibe nie um"
    auf eine 80k-LOC-Codebasis, oder zementiert es Altlasten dauerhaft?
12. **Bounded-Context-Versprechen.** Schritt 9 begründet getrennte
    Versionsbäume mit „DB-Split ohne Daten-Migration". Stress-teste das:
    Bei echtem Stage-B-Split — ist es *wirklich* nur Deploy, oder gibt es
    versteckte Kopplung (geteilte `engine`/`get_session`, Soft-FK
    `Invoice.lead_id`, geteilte `app.core.*`, Test-Fixtures über die
    Netzgrenze), die den Split doch zu einem Rewrite macht?

## Liefere

1. **Urteil** in einem Satz: ist der Plan (a) korrekt umgesetzt,
   (b) vollständig umgesetzt, (c) zielwirksam (Agent-Konsistenz +
   Skalierung) — je *ja / teilweise / nein* mit dem stärksten Gegenbeleg.
2. **Risiko-Register**: jede gefundene Lücke mit Schweregrad, konkretem
   Code-/Config-Beleg (Datei:Zeile), und „bricht wann/bei welcher
   Aktion".
3. **Übersprungen-Liste**: alles, was die Roadmap *fordert*, aber nicht
   geschah (Outcome-Probe-Verdacht zuerst), klar getrennt von
   *bewusst deferred + begründet*.
4. **Punch-List**: priorisierte, minimale nächste Schritte, die die
   Behauptungen „Agent versteht / darf / skaliert" tatsächlich *erzwingen*
   (nicht nur dokumentieren) würden — jeweils als ausführbares Gate
   formuliert, nicht als Prosa.
5. Keine Höflichkeits-Bestätigung. Wenn etwas nur *behauptet* und nicht
   *erzwungen* ist, nenne es so.
