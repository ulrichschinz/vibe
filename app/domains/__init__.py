"""app.domains — one package per bounded context.

Each domain is a self-contained, excisable unit
(models/schemas/service/repository/router). Cross-domain data flows **only**
via `app.contracts` (import-linter: domains/<x> ↛ domains/<y>). Routers are
auto-discovered by `interfaces/*` (Schritt 8 iterates this package); the
scaffold patches no central registry.

`make new-domain X` is the one-command way to add a genuinely new domain.
The existing leads/proposals/billing logic still lives in
`routes/`+`services/`+`models.py` until Schritt 4–8 move it in here.
"""
