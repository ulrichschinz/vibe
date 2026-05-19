"""interfaces.mcp — FastMCP delivery layer (Schritt 8).

`register(app)` mounts the X-API-Key-gated MCP ASGI app at ``/mcp`` and
returns the FastMCP session-manager context so `main.py`'s lifespan can run
it (mounted sub-apps have no own lifespan). The 16 tools live in
`services/mcp_server.py` (frozen `m.engine` seam — ADR-009 §B); Schritt 7
made them thin (delegate to `app/domains/*/service.py`), Schritt 8 routed
the invoice tools through the billing facade so this layer constructs no
domain models (import-linter edge).
"""

from __future__ import annotations

from fastapi import FastAPI

from app.interfaces.mcp.mount import mcp_app
from services.mcp_server import mcp


def register(app: FastAPI) -> None:
    app.mount("/mcp", mcp_app)


def session_manager():
    """FastMCP session-manager context — driven by `main.py`'s lifespan."""
    return mcp.session_manager.run()
