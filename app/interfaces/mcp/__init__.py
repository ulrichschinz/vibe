"""interfaces.mcp — FastMCP delivery layer (Schritt 8 + T7-D).

`register(app)` mounts the X-API-Key-gated MCP ASGI app at ``/mcp`` and
returns the FastMCP session-manager context so `main.py`'s lifespan can run
it (mounted sub-apps have no own lifespan). The 16 tools live in
`app/interfaces/mcp/server.py` (T7-D/ADR-017 cashed in the `m.engine`-seam
relocation deferred by ADR-009 §B); Schritt 7 made them thin (delegate to
`app/domains/*/service.py`), Schritt 8 routed the invoice tools through
the billing facade so this layer constructs no domain models (import-linter
edge).
"""

from __future__ import annotations

from fastapi import FastAPI

from app.interfaces.mcp.mount import mcp_app
from app.interfaces.mcp.server import mcp


def register(app: FastAPI) -> None:
    app.mount("/mcp", mcp_app)


def session_manager():
    """FastMCP session-manager context — driven by `main.py`'s lifespan."""
    return mcp.session_manager.run()
