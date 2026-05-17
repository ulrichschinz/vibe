"""interfaces.mcp — FastMCP tools (placeholder).

Soll: today's `services/mcp_server.py` (16 tools) + `routes/mcp.py`
mount/X-API-Key wrapper, with tools calling `domains/*/service.py` instead
of constructing `Lead(...)` themselves (Schritt 7). An import-linter rule
will forbid domain-model construction here so the duplicate logic cannot
return. Empty by design in Schritt 2.
"""
