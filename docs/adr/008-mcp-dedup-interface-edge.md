# ADR-008: MCP-Entdopplung — die `interfaces/mcp`-Kante (Schritt 7)

**Status:** Akzeptiert (2026-05-18)

## Kontext

`services/mcp_server.py` (FastMCP, 16 Tools) duplizierte die Lead/Proposal-
Logik: `create_lead`/`update_lead` instanziierten `Lead(...)` selbst statt
einen Service zu rufen; `list_leads`/`get_lead`/`add_note`/`list_notes`/
`list_proposals`/`get_proposal` querten + serialisierten die Modelle inline.
Das ist die in `ARCHITECTURE.md` dokumentierte **Struktur-Schuld 4** und die
in `docs/scaling-roadmap.md` Schritt 7 adressierte „MCP entdoppeln".
`create_proposal`/`mark_proposal_sent` riefen bereits den sauberen geteilten
`services/proposals.py` (auch von `routes/proposals.py` verbatim genutzt).

Die `characterization-map.md` ordnet Schritt 7 genau zu: `test_mcp_tools`
(create/update_lead, create_proposal, mark_proposal_sent, finalize-chain) +
`test_proposals_routes` Update/mark-sent. Keiner dieser Tests patcht
`services.ai`/`services.linkedin_import` (das ist die Schritt-6-Naht für
Schritt-6-Tests, die bis Schritt 8 unverändert grün bleiben).

## Optionen geprüft

1. **Konstruktion/Query/Serialisierung verbatim nach
   `app/domains/{leads,proposals}/service.py` ziehen; Tools delegieren mit
   caller-owned `Session(engine)`; eine `import-linter`-`forbidden`-Regel mit
   `allow_indirect_imports` schützt die Kante** *(gewählt)*
2. Eine `interfaces/mcp`-Regel mit DEFAULT-(transitiver) Erkennung wie die
   Schritt-5-Billing-Regel
3. `routes/`+`mcp_server` zu *einer* gemeinsamen Lead-Create/Update-Logik
   konsolidieren (echte „eine Logik, drei Clients" jetzt)
4. Auch die Invoice-Draft/Line-Tools in einen Billing-Service ziehen +
   `app.domains.billing.models` aus dem MCP-Layer verbieten

## Entscheidung

**Option 1.** Die Bodies wandern **byte-für-byte** in die besitzende Domäne
(`app/domains/leads/service.py`: `mcp_create_lead`/`mcp_update_lead`/
`mcp_list_leads`/`mcp_get_lead`/`mcp_add_note`/`mcp_list_notes` +
`serialize_lead`/`serialize_note`; `app/domains/proposals/service.py`:
`serialize_proposal`/`list_proposals`/`get_proposal`). Das **unangetastete**
`services/proposals.py` wird von den `create_proposal`/`mark_proposal_sent`-
Tools weiter **direkt** gerufen (es war nie das Duplikat) — sie hängen nur
`serialize_proposal` an; bewusst *kein* `services.proposals`-Import in
`app/domains/proposals/service.py` (das zöge das Legacy-`services.numbering`
in den `app.*`-strict-mypy-Graph = ein vorbestehender Legacy-
`[attr-defined]`; die Konstruktion bleibt im nicht-mypy-gegateten
MCP-Interface verdrahtet). Einzige nicht-verbatim Änderung: `with
Session(engine)` → vom Aufrufer übergebene `session` (Scaffold-/Service-
Vertrag: Service ist reine Logik, das MCP-Interface besitzt den Engine-/
Session-Lifecycle) plus `# type: ignore` auf ORM-Ausdrücke für den
`app.*`-strict-mypy-Gate (typ-only, keine Verhaltensänderung — das
dokumentierte Schritt-4/6-Muster). Die Enums werden über das Service-Modul
re-exportiert, damit die Tool-Signaturen ihren FastMCP-Schema-Typ behalten,
ohne `domains/*/models` zu importieren.

- **Option 2** verworfen: die transitive Erkennung würde die *legitime*
  intra-domain-Kette `mcp_server → leads.service → leads.models` fälschlich
  als Verstoß werten. Genau invers zur Schritt-5-Billing-Regel (die die
  Transitivität *braucht*, um den `models`-Shim-Reach zu fangen). Daher
  `allow_indirect_imports = "True"`: es verbietet exakt den **direkten**
  Domänen-Modell-Import im Interface und lässt den Weg über `service`/
  `schemas` zu — die präzise Kodierung von „kein Modell-Konstruktor in
  `interfaces/mcp`".
- **Option 3** verworfen: `routes`/`api`/`mcp` haben *unterschiedliche*
  Eingabeverträge (Form vs. pydantic vs. typed kwargs). Eine echte
  Konsolidierung berührt die Routes (Verhaltensänderungs-Risiko über das
  Char-Netz, das jene Routes erst in Schritt 8 anfasst) — Scope-Bruch
  gegen „ein PR, ein Konzern, keine Verhaltensänderung". Schritt 7 entkoppelt
  das *MCP*-Duplikat; der Web/REST-Interface-Split ist Schritt 8.
- **Option 4** verworfen für Schritt 7: die Invoice-Draft/Line-Tools sind
  **kein** CRM-Duplikat (Schuld 4 = ausdrücklich *Lead/Proposal*); Finalize/
  Storno laufen seit Schritt 5 über den `BillingOrder`-Vertrag. Interface-
  geformten Code jetzt nach `services/invoicing/` zu ziehen riskiert den
  `.coveragerc`-90 %-Billing-Gate und greift dem Schritt-8-Interface-Split
  vor. Roadmap-Prinzip: eine Regel ist inaktiv bis ihr Paket existiert;
  jeder Schritt aktiviert *seine* Kante.

## Konsequenz / Erzwingung

Neuer `forbidden`-Contract in `pyproject.toml`:

```
source_modules    = ["services.mcp_server"]
forbidden_modules = ["app.domains.leads.models", "app.domains.proposals.models"]
allow_indirect_imports = "True"
```

= die `interfaces/mcp`-Zeile der Roadmap-Kantentabelle, auf den
Lead/Proposal-Duplikat geschärft. Die Schritt-5-Billing-Regel wird im selben
Schritt nur **umbenannt** (Wegfall des veralteten Zusatzes „full interface
edge set Schritt 7"); inhaltlich unverändert.

**Lebenszyklus / Shim:** kein Shim stirbt in Schritt 7. Der `models`-Shim
hat weiter Aufrufer (`routes/*`, `services/proposals.py`,
`services/numbering.py`) → Tod erst im PR des letzten Aufrufers (Schritt 8).
Die `services/ai`+`services/linkedin_import`-Shims bedienen die
Schritt-6-Char-Tests, die bis Schritt 8 unverändert grün bleiben. Daher
**0-Diff im `tests/`-Netz, kein Char-Lifecycle-Delete** (werkgetreu zur
`characterization-map.md`: die Schritt-7-Tests sind exakt `test_mcp_tools` +
`test_proposals_routes` Update/mark-sent; sie werden über die nun dünnen
Tool-Aufrufer transitiv weiter abgedeckt — dasselbe Muster wie Schritt 6).

Akzeptanz-Gate: `make verify` grün (inkl. der neuen import-linter-Regel) +
die 90 %-Invoicing-Suite grün + die 140 Characterization-Tests **unverändert
grün** (0 `tests/`-Diff) + Doc-Gate grün.
