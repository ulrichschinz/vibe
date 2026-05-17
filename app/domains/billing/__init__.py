"""billing domain — invoicing bounded context (placeholder package).

The future home of today's `services/invoicing/` (compliance core, §14
UStG / ZUGFeRD, ~90 % coverage). **Move-not-rewrite:** the code is
relocated unchanged; its existing tests are the safety net and stay green
every step. The only behavioural change anywhere is replacing
`_snapshot_customer()`'s direct `Lead` read with the `BillingOrder`
contract (Schritt 5).

Hardest import-linter rule (end state): `domains/billing/*` may import only
`core/*`, `shared/*`, `contracts/billing_order` and its own package —
**never** any `domains/*` or top-level `models`. That rule is the seed
`services.invoicing ↛ routes` today and sharpens onto this package in
Schritt 5. Empty package by design in Schritt 2 (models move Schritt 4).
"""
