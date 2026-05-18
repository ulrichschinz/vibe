# ADR-009: Interface-Split + zentraler RFC-7807-Mapper (Schritt 8)

**Status:** Akzeptiert (2026-05-18)

## Kontext

Schritt 8 von `docs/scaling-roadmap.md` finalisiert den Interface-Split:
die Web-/REST-/MCP-Router liegen heute interface-gemischt unter `routes/`
+ `services/mcp_server.py`; das `app/interfaces/{web,api,mcp}`-Skelett steht
seit Schritt 2 docstring-only. Zusätzlich verschob Schritt 7 vier Punkte
explizit hierher (ADR-008 / `ARCHITECTURE.md` Schuld 4 „Offen"):

1. Router-Trennung `routes/` → `app/interfaces/{web,api,mcp}` +
   Auto-Discovery (Scaffold-Vertrag „Registrierungs-Mechanismus").
2. Zentraler RFC-7807-Mapper statt Inline-`HTTPException`-Coercion pro
   Endpoint in `routes/api.py`.
3. Billing-MCP-Facade: die billing-internen Invoice-Draft/Line/Get/List/
   Storno-Tools konstruieren noch `Invoice(...)` direkt im MCP-Layer.
4. Volle Interface-Kantenmenge der Roadmap-Tabelle aktivieren + der
   `models`-Shim-Tod (Prod-Naht).

## Entscheidungen

### A — Move-not-rewrite + `routes/*`-Re-Export-Shims

Die Handler-Bodies wandern **byte-verbatim** nach `app/interfaces/web/`
(`leads,proposals,invoices,admin,auth,ai`) bzw. `app/interfaces/api/`
(`router.py`). Einzige Änderung an verschobenem Code: die Modell-Importe
zeigen statt auf den Top-Level-`models`-Shim direkt auf `app.domains.*` /
`app.core.*` (das kappt die Prod-Naht) und die Template-Pfade bleiben
identisch (`templates/` wird vom Repo-Root referenziert — kein Move).

`routes/leads.py` + `routes/proposals.py` bleiben als **dünne
Re-Export-Shims** (`from app.interfaces.web.<m> import router`), weil die
eingefrorene Test-Suite sie importiert
(`tests/characterization/test_{leads,proposals}_routes.py`,
`tests/integration/test_proposal_from_plan.py` ⇒ `from routes import …`).
Die übrigen Route-Module (`api,invoices,admin,auth,ai,mcp`) hatten nur
`main.py` als Aufrufer → ersatzlos gelöscht (kein Test importiert sie).
Das ist exakt das von der Fork-Entscheidung gewählte Muster „Prod-Naht
kappen, Shim-Dateien für die Tests behalten, physischen Datei-Tod +
Test-Import-Migration als eigenen Folgeschritt" (S1-Präzedenz: Churn ohne
Schritt-Eigner wird verschoben).

### B — `services/mcp_server.py` bleibt physisch

`tests/characterization/conftest.py::mcp_module` macht
`import services.mcp_server as m; monkeypatch.setattr(m, "engine", …)`.
ADR-008 hält fest: „der `mcp_module`-`m.engine`-Monkeypatch-Seam bleibt
exakt". Ein physischer Move von `mcp_server.py` würde diesen eingefrorenen
Seam (und damit `test_mcp_tools`, S7-zugeordnet, 0-Diff-Pflicht) brechen.
Daher bleibt `services/mcp_server.py` der physische Home von `mcp` +
Tools + `engine` — analog zum `models.py`/`services.ai`-Shim-Muster. Der
Mount (`routes/mcp.py`) zieht nach `app/interfaces/mcp/mount.py`; das
`app/interfaces/mcp`-Paket re-exportiert `mcp` für die Registrierung.
Physische Relokation + Conftest-Seam-Migration = derselbe deferred
Folgeschritt wie der Datei-Tod.

### C — Echtes `application/problem+json` (RFC-7807)

`tests/characterization/test_api_errors.py` pinnt bewusst das **aktuelle**
`{"detail": …}` (FastAPI-Default) „so that Schritt-8 change is a visible,
intentional diff". Der zentrale Mapper (`app/core/errors.py`) liefert
daher **echtes** `application/problem+json` (`{type,title,status,detail}`),
über `app.interfaces.api`-Exception-Handler registriert. **Statuscodes
und die Fang-Reihenfolge bleiben erhalten**: `InvoiceValidationError ⊂
FinalizeError` wird zuerst gefangen → Doppel-Finalize bleibt **422** (nicht
409), Draft-Guard bleibt 409 (charakterisiert in
`test_double_finalize_is_422_and_lines_on_finalized_is_409`). Der Mapper
ist die einzige sanktionierte Verhaltensänderung in Schritt 8 (Roadmap-
Disziplin: charakterisiert + sichtbar). `test_api_errors.py` ist in
`docs/characterization-map.md` Schritt 8 zugeordnet → **Lifecycle-Delete
im selben PR** mit äquivalenten Mapper-Unit-Tests
(`tests/unit/test_rfc7807_mapper.py`), die den neuen Vertrag (Statuscodes,
422-vor-409, problem+json-Shape) zusichern. Alle übrigen 132
Characterization-Tests bleiben **0-Diff**.

### D — Billing-MCP-Facade in `app/domains/billing/service.py`

Neu, strict-mypy-/ruff-konform. Kapselt Draft-/Line-/Get-/List-/Storno-
Konstruktion über Billings **eigene** Modelle (erlaubte Kante:
`domains/billing/* → domains/billing/*`). Die MCP-Invoice-Tools delegieren
dorthin statt `_Invoice(...)` selbst zu bauen → `interfaces/mcp`
konstruiert keine Domänen-Modelle mehr. Bewusst **nicht** in
`services/invoicing/` (würde den `.coveragerc`-90 %-Billing-Gate auf
Interface-geformten Code ziehen und den `customer_resolver` in die
verbotene Kante zwingen — S5-Muster: der Resolver bleibt im Interface-
Aufrufer verdrahtet). Finalize/Storno laufen unverändert über den
`BillingOrder`-Vertrag (Schritt 5).

### E — mypy-Scope der Interface-Adapter

`app.*` ist strict. Die ~2.000 LOC verschobener FastAPI-Handler tragen
vorbestehende untypisierte Signaturen (`_=Depends(...)`, fehlende
Return-Annotationen) — sie strict zu typisieren wäre ein Repo-weiter
Rewrite, „Churn owned by no step" und ein Verstoß gegen move-not-rewrite
(exakt die Schritt-1-Scoping-Entscheidung: das Gate trifft nur die *neue*
Soll-Fläche, Legacy wandert per Schritt unter den Checker). `routes/`/
`services/` waren vor S8 **gar nicht** im mypy-Lauf (`typecheck` =
`mypy scripts app`). Damit der mechanische Move den Status nicht ändert:
`[[tool.mypy.overrides]] module = "app.interfaces.*"` mit
`ignore_errors = true` (exakt „Legacy ist erst unter dem Checker, wenn es
*richtig* migriert ist" — die verschobenen FastAPI-Handler tragen die
vorbestehenden untypisierten Signaturen + ungetypte ORM-Ausdrücke; sie
strict zu machen wäre ein Repo-weiter Rewrite, kein S8-Scope). Die *neuen*
Logik-Module — `app.core.errors`-Mapper, `app.domains.billing.service`-
Facade — liegen **außerhalb** `app.interfaces.*` und bleiben voll
`app.*`-strict (ORM-Ausdrücke mit dem dokumentierten `# type: ignore`-
Muster). `ruff format` (mechanisch, lokal vorgeprüft) gilt für ganz
`app/`. `ruff check`: `F` bleibt **überall** aktiv (tote Importe werden
entfernt); `E712`/`E741` sind in den verbatim verschobenen
`app/interfaces/{web,api}/*`-Handlern per-file-ignored (dieselbe
move-not-rewrite-Begründung wie `ignore_errors`) — die neuen Logik-Module
sind voll gelintet.

### F — `models`-Shim-Tod (Prod-name-reexport-scoped)

`models.py` **bleibt** das Move-Vertrag-Aggregations-Modul (eine
Verschiebung der Aggregation nach `app/core/tables.py` würde selbst die zu
aktivierende `core ↛ domains`-Kante verletzen — der Aggregator muss alle
Domänen-Modelle importieren). `database.create_db()` behält den
Registry-Bootstrap `import models`; `database` ist ein Top-Level-Modul,
**kein** import-linter-`root_package`, also für die Contracts unsichtbar.
Alle Prod-**Namens-Re-Export**-Konsumenten (`main.py`, `services/auth.py`,
`services/proposals.py`, `services/numbering.py`,
`services/mcp_server.py`, die verschobenen `app.interfaces.*`-Handler)
zeigen direkt auf `app.*` — **kein `services`/`routes`/`app`-Modul
importiert die Shim-Namen mehr**. `models.py` überlebt als
**test-zugewandter** Re-Export (Docstring aktualisiert).

**Erzwingung — grimp-Limitation (S5-Lektion).** Ein nacktes `models.py`
ist kein gültiges grimp-`root_package` und (sobald kein Aufrufer es mehr
zieht) gar nicht im Import-Graph → eine `forbidden_modules = ["models"]`-
Regel ist nicht werkgetreu kodierbar (genau die in Schritt 5 dokumentierte
Limitation). Der Shim-Tod ist daher **(i)** durch die volle Interface-/
Domain-Kantenmenge unten erzwungen (kein Pfad zu `domains/*/models`
außer intra-domain) und **(ii)** statisch grep-verifiziert „kein
`services|routes|app` importiert top-level `models`" — dieselbe
CI-Arbiter-Logik wie die transitive S5-Billing-Regel.

### G — Volle Interface-Kantenmenge (`pyproject.toml`)

`root_packages = ["services", "routes", "app"]` (unverändert). Aktivierte
`forbidden`/`independence`-Contracts — **nur die Kanten, die nach
move-not-rewrite-S8 *wahr* sind** (eine Regel ist inaktiv bis ihr
Zustand gilt — Roadmap Schicht 2):

- **`interfaces/mcp`-Zeile (voll aktiv):** die Schritt-7-Regel
  `services.mcp_server ↛ app.domains.{leads,proposals}.models` wird um
  `app.domains.billing.models` erweitert (die Billing-Facade entkoppelte
  den letzten direkten Modell-Import), `allow_indirect_imports = "True"`
  (kein **direkter** Modell-Import, intra-domain `service → models`
  erlaubt — die exakte ADR-008-Subtilität). `mcp_server` bleibt physisch
  (B), deckt damit die `interfaces/mcp`-Zeile ab.
- **`core ↛ domains/interfaces/contracts` (aktiv):** grep-verifiziert
  sauber (`app.core` importiert nichts aus `app.domains`/`app.interfaces`/
  `app.contracts`).
- **`domains/<x> ↛ domains/<y>` (aktiv):** `independence`-Contract über
  `app.domains.{leads,proposals,billing}` — grep-verifiziert: nur
  intra-domain-Importe. Der Schritt-6-Transitional-Seam
  (`app.domains.proposals.service → services.ai`,
  `app.domains.leads.service → services.linkedin_import`) ist `services.*`,
  **nicht** `app.domains.*` → keine Independence-Verletzung; er stirbt mit
  den S6-Char-Tests in einem späteren Schritt.
- **Billing-Regel (S5):** unverändert; `forbidden_modules` um
  `app.interfaces` ergänzt (Billing-Isolation auch ggü. der neuen
  Interface-Schicht).

**Bewusst NICHT aktiviert (werkgetreu — Zustand gilt noch nicht):**

- `interfaces/* ↛ domains/*/models` für die **web/REST**-Zeile: die
  verschobenen CRUD-Handler konstruieren weiter `Lead(...)`/`Invoice(...)`
  direkt (move-not-rewrite — Schritt 8 ist „Router-Trennung + Mapper,
  mechanisch", **nicht** „Handler dünn machen"). Die Roadmap terminiert
  dieses Ausdünnen nirgends als eigenen Schritt → Folge-Refactor, „Churn
  owned by no step" (Schritt-1-Präzedenz). Die `interfaces/mcp`-Zeile *ist*
  aktiv (oben), exakt weil S6/S7 + die S8-Billing-Facade die MCP-Handler
  dünn gemacht haben.
- `shared ↛ domains`: `app.shared.labels` ist **enum-keyed** und importiert
  bewusst die Enums aus `app.domains.*.models` (Schritt-4-Entscheidung).
  Die Roadmap-Endzustands-Kante setzt eine Enum-Relokation voraus, die
  kein Schritt terminiert → ebenfalls deferred.

Lokal nicht verifizierbar (kein Interpreter mit App-Deps; grimp braucht
den Import-Graph) → statisch via grep geprüft, **CI ist Arbiter** (S4/5/7-
Muster).

## Konsequenz / Akzeptanz-Gate

`make verify` grün (ruff + ruff-format + mypy + import-linter + test-fast
+ Doc-Gate) **und** die 90 %-Invoicing-Suite grün **und** die 132
verbleibenden Characterization-Tests **0-Diff grün** (der dokumentierte
Lifecycle-Delete: `test_api_errors.py` → `tests/unit/test_rfc7807_mapper.py`
im selben PR) **und** ARCHITECTURE.md-Kennzahlen/Baum/Schichten +
CLAUDE.md-Statusbanner im selben PR aktualisiert.

Kein Char-Lifecycle-Delete der S6-AI/LinkedIn-Char-Tests in Schritt 8:
die `services/ai.py`+`services/linkedin_import.py`-Shims + ihr lazy
Service-Seam **bleiben** (sie bedienen weiter `test_from_plan_*` /
LinkedIn-Char + `test_proposal_from_plan` + `test_ai_proposal_drafts`);
ihr Tod gegen äquivalente Service-Unit-Tests ist ein eigener Folgeschritt
(werkgetreu: `characterization-map.md` ordnet Schritt 8 **nur**
`test_api_errors` zu).
