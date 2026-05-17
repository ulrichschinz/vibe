"""app.contracts — published DTOs (the anti-corruption seam).

Pure pydantic data only — import-linter end state: contracts ↛
domains/core/interfaces (dependency-free DTO).

Entry point (Schritt 5): `billing_order.py` — the explicit
`BillingOrder` an extraction-ready billing context consumes instead of
reaching into CRM. It carries an immutable snapshot (issuer, customer,
lines, meta) so `domains/billing` imports nothing from `domains/*`/`models`
— replacing today's `finalize.py::_snapshot_customer()` Lead read. Empty by
design in Schritt 2.
"""
