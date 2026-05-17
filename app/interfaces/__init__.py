"""app.interfaces — the delivery layer (web / api / mcp).

One logic, three clients: web (Jinja UI), api (REST), and mcp (FastMCP)
all call the same `domains/*/service.py` — no duplicated logic. Schritt 8
finalizes the split; Schritt 7 removes the MCP duplication.

import-linter end state: interfaces/* may import
`domains/*/{router,service,schemas}`, `core/*`, `shared/*` — **not**
`domains/*/models` (no model access from interfaces) or
`domains/*/repository`. `interfaces/mcp` additionally must not construct
domain models (kills the MCP logic duplicate). Empty by design in Schritt 2.
"""
