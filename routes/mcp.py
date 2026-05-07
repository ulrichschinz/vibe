"""ASGI mount-point for the MCP server with X-API-Key gating.

Wraps the FastMCP streamable-HTTP app in an ASGI middleware that checks the
X-API-Key header against the same ApiKey table the REST API uses. Reuses
validate_api_key from routes/api.py so revoking a key in the admin UI takes
effect for both REST and MCP on the next request.
"""
from sqlmodel import Session
from starlette.responses import PlainTextResponse

from database import engine
from routes.api import validate_api_key
from services.mcp_server import mcp

_mcp_asgi = mcp.streamable_http_app()


class _ApiKeyAuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        api_key = ""
        for name, value in scope.get("headers", []):
            if name == b"x-api-key":
                api_key = value.decode("latin-1")
                break

        if not api_key:
            await PlainTextResponse("API key required", status_code=401)(scope, receive, send)
            return

        with Session(engine) as session:
            if not validate_api_key(api_key, session):
                await PlainTextResponse("Invalid API key", status_code=401)(scope, receive, send)
                return

        await self.app(scope, receive, send)


mcp_app = _ApiKeyAuthMiddleware(_mcp_asgi)
