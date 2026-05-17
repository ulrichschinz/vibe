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
| `test_api_errors.py::test_missing_api_key_is_401_detail` | `routes/api.py` Auth-Fehler-Shape | **8** → zentraler RFC-7807-Mapper |
| `test_api_errors.py::test_invalid_api_key_is_401_detail` | `routes/api.py` Auth-Fehler-Shape | **8** |
| `test_api_errors.py::test_create_lead_without_name_or_company_is_422_detail` | `routes/api.py` Inline-422-Coercion | **8** |
| `test_api_errors.py::test_add_line_to_unknown_invoice_is_404_detail` | `routes/api.py` Inline-404-Coercion | **8** |
| `test_api_errors.py::test_get_unknown_invoice_is_404` | `routes/api.py` Inline-404 | **8** |
| `test_api_errors.py::test_finalize_without_lines_is_422_detail_string` | `routes/api.py` `InvoiceValidationError`→422 | **8** (+ Finalize-Naht **5**) |
| `test_api_errors.py::test_double_finalize_is_422_and_lines_on_finalized_is_409` | `routes/api.py` Doppel-Finalize→**422** (InvoiceValidationError vor FinalizeError gefangen) / Draft-Guard→409 | **8** (+ Finalize-Naht **5**) |

## Abdeckungs-Check gegen den Vertrag

Jeder im Vertrag gelistete Handler/Tool hat ≥1 Test (Status + Seiteneffekt):

- `routes/leads.py`: Dashboard ✓, LinkedIn-Import ✓ (happy + 2 Fehlerpfade),
  Lead→Proposal ✓.
- `routes/proposals.py`: AI-Draft + Merge ✓ (happy + Fallback);
  Update/mark-sent ✓.
- `services/mcp_server.py`: `create_lead`/`update_lead` ✓, Proposal-Tools ✓,
  Finalize-Kette ✓.
- `routes/api.py`: Inline-RFC-7807-Endpoints (leads, invoice-lines,
  finalize, get) ✓ + Auth-Shape ✓.
