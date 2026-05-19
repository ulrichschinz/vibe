# Characterization-Map — Test → Migrationsschritt

> Schritt 0.5 von [`scaling-roadmap.md`](scaling-roadmap.md). Diese Tests
> sind das Sicherheitsnetz für die untesteten Bruchstellen, die Schritte
> 5–8 anfassen (die 90 %-Coverage liegt in `invoicing/` — *dort, wo nichts
> geändert wird*).

## Härtekriterium & Lebenszyklus

- **Granularität:** HTTP-Status + Redirect-`Location` + DB-Seiteneffekt
  (Web); Rückgabe-Payload-*Shape* + DB-Seiteneffekt (MCP). **Kein
  HTML-Body** — der wäre kosmetik-fragil über die Service-Extraktion.
  Externe Aufrufe (Anthropic, LinkedIn-PDF, VIES) sind gestubbt →
  deterministisch.
- **Härte:** Diese Tests bleiben über die PRs der Schritte 5–8
  **unverändert grün**. Ein Diff an einem Characterization-Test in jenen
  PRs ist ein Rotflag und **begründungspflichtig**.
- **Lebenszyklus:** Ein Eintrag wird **erst in demselben PR gelöscht, der
  den äquivalenten Service-Unit-Test einführt** — nie vorher (sonst Netz
  mit Loch).
- Lauf-Lane: Marker `characterization`, läuft in `make test-fast`
  (`-m "not contract and not e2e"`) → bei **jedem** PR.

## Mapping

| Test | Bruchstelle (heute) | Schützt Schritt |
|---|---|---|
| `test_leads_routes.py::test_dashboard_aggregation_over_all_stages_returns_200` | `routes/leads.py` Dashboard-Aggregation | **6** → `domains/leads/service.py` |
| `test_leads_routes.py::test_linkedin_import_happy_path_renders_preview_without_persisting` | `routes/leads.py` LinkedIn-Import-Orchestrierung (preview-only) | **6** → `domains/leads/service.py` |
| `test_leads_routes.py::test_linkedin_import_non_pdf_redirects_and_persists_nothing` | `routes/leads.py` LinkedIn-Validierung/Redirect | **6** |
| `test_leads_routes.py::test_linkedin_import_extraction_error_redirects_and_persists_nothing` | `routes/leads.py` LinkedIn-Fehlerpfad | **6** |
| `test_leads_routes.py::test_lead_to_proposal_creates_row_and_redirects` | `routes/proposals.py` Lead→Proposal-Erzeugung | **6** → `domains/proposals/service.py` |
| `test_leads_routes.py::test_lead_to_proposal_unknown_lead_is_404` | Lead→Proposal Fehlerpfad | **6** |
| `test_proposals_routes.py::test_from_plan_calls_llm_once_and_writes_nothing` | `routes/proposals.py` AI-Draft-Erzeugung + Merge | **6** → `domains/proposals/service.py`; AI-Adapter **6** → `core/ai` |
| `test_proposals_routes.py::test_from_plan_llm_error_falls_back_without_5xx_or_write` | AI-Draft Fallback (verbatim, **kein** Robustheits-Fix in Schritt 6) | **6** |
| `test_proposals_routes.py::test_proposal_update_persists_fields_and_redirects` | `routes/proposals.py` Proposal-Mutation | **7** (MCP-Entdopplung teilt diese Logik) |
| `test_proposals_routes.py::test_proposal_mark_sent_sets_status_and_redirects` | `routes/proposals.py` mark-sent | **7** |
| `test_mcp_tools.py::test_create_lead_payload_shape_and_row` | `services/mcp_server.py` `create_lead` (Duplikat-Konstruktion) | **7** |
| `test_mcp_tools.py::test_create_lead_requires_name_or_company` | `create_lead` Guard | **7** |
| `test_mcp_tools.py::test_update_lead_patches_only_given_fields` | `services/mcp_server.py` `update_lead` (Duplikat-Konstruktion) | **7** |
| `test_mcp_tools.py::test_update_lead_unknown_id_raises_lookup` | `update_lead` Fehlerpfad | **7** |
| `test_mcp_tools.py::test_create_proposal_shape_and_row` | `services/mcp_server.py` `create_proposal` | **7** |
| `test_mcp_tools.py::test_mark_proposal_sent_shape_and_row` | `services/mcp_server.py` `mark_proposal_sent` | **7** |
| `test_mcp_tools.py::test_finalize_chain_draft_to_finalized` | `services/mcp_server.py` Finalize-Kette | **7** (Finalize → BillingOrder-Vertrag) |
| ~~`test_api_errors.py` (alle 7)~~ → **Schritt 8 RETIRED** (Lifecycle-Delete, ADR-009 §C). Pinnten bewusst den *alten* FastAPI-Default-`{"detail"}`-Body, damit der RFC-7807-Wechsel ein **sichtbarer, gewollter** Diff ist. Ersetzt im **selben PR** durch den äquivalenten Unit-Test `tests/unit/test_rfc7807_mapper.py` (Mapper-Unit + App-Level: problem+json-Shape, Statuscodes, **422-vor-409** erhalten, REST→problem+json / Web→Default unverändert). | `routes/api.py` Inline-RFC-7807-Coercion → `app/interfaces/api` + `app/core/errors` zentraler Mapper | **8** (+ Finalize-Naht **5**) |

## Abdeckungs-Check gegen den Vertrag

Jeder im Vertrag gelistete Handler/Tool hat ≥1 Test (Status + Seiteneffekt):

- `routes/leads.py`: Dashboard ✓, LinkedIn-Import ✓ (happy + 2 Fehlerpfade),
  Lead→Proposal ✓.
- `routes/proposals.py`: AI-Draft + Merge ✓ (happy + Fallback);
  Update/mark-sent ✓.
- `services/mcp_server.py`: `create_lead`/`update_lead` ✓, Proposal-Tools ✓,
  Finalize-Kette ✓.
- `routes/api.py` → `app/interfaces/api` + `app/core/errors`: in Schritt 8
  vom Characterization-Netz auf den äquivalenten Unit-Test
  `tests/unit/test_rfc7807_mapper.py` umgestellt (Lifecycle-Delete im
  selben PR — der einzige sanktionierte `tests/`-Diff in Schritt 8;
  ADR-009 §C). Die übrigen 132 Characterization-Tests bleiben 0-Diff.
