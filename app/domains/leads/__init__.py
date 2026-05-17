"""leads domain — CRM core (placeholder package).

Owns: Lead/Note/PlanningMessage tables, lead CRUD, dashboard aggregation,
LinkedIn-import orchestration, Lead→Proposal creation, and the planning
chat history (planning belongs to the Lead, not the Proposal).

Today this logic lives in `models.py` + `routes/leads.py` +
`services/linkedin_import.py`; it moves here in Schritt 4 (models) and
Schritt 6 (service, behind the Schritt-0.5 characterization net). Empty
package by design in Schritt 2 — `make new-domain` is for *new* domains;
this one is populated by the move steps.
"""
