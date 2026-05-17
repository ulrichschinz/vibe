"""Reusable kernel — knows no domain (import-linter: core ↛ domains).

Entry points (filled by later steps):
  config.py   pydantic-settings, fail-fast on missing env (Schritt 3)
  db.py       shared SQLModel base + session dependency (this step seeds it;
              Schritt 3 swaps in the config-driven engine)
  security.py password hashing, auth dependencies (Schritt 6)
  logging.py  structured logging / request-ids (currently absent in Ist)
  errors.py   shared error types + the central RFC-7807 mapper (Schritt 8)
  ai.py       Anthropic adapter + prompt registry + ===MARKER=== parsing,
              moved verbatim from services/ai.py (Schritt 6)
"""
