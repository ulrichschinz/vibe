"""Application package — the Soll (domain-oriented) layout.

Scaling-roadmap Schritt 2: this is the *final* skeleton, created early so
every later step moves code **once** to its end location (no shim+later
churn). It is intentionally empty bar module docstrings until Schritt 3–8
migrate the existing `routes/`+`services/`+`models.py` code in.

Structure (see docs/scaling-roadmap.md):
  core/        reusable kernel — config, db, security, logging, errors, ai
  contracts/   published DTOs (anti-corruption seam, e.g. BillingOrder)
  domains/     one package per bounded context (leads, proposals, billing)
  interfaces/  delivery layer — web (Jinja), api (REST), mcp (FastMCP)
  shared/      cross-cutting helpers — labels/i18n, pdf, numbering, money

Until the code-move steps land, the live application is still the
top-level `main.py` app; nothing imports `app.*` in production yet.
"""
