"""proposals domain — offers/quotes (placeholder package).

Owns: Proposal/ProposalLineItem tables, proposal CRUD, PDF rendering, and
the AI draft-creation + merge orchestration (the AI *adapter* itself lives
in `app.core.ai`; orchestration stays in the owning domain's service).

Today this logic lives in `models.py` + `routes/proposals.py` +
`routes/ai.py` + `services/proposals.py`/`pdf.py`; it moves here in Schritt
4 (models) and Schritt 6 (service). Empty package by design in Schritt 2.
"""
