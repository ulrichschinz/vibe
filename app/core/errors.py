"""app.core.errors — central RFC-7807 problem+json mapper (Schritt 8).

Ist (Schritt 0.5 Bruchstelle): `routes/api.py` coerced error bodies inline
per endpoint (`raise HTTPException(status, str)`, FastAPI-Default
``{"detail": …}``). Soll (ADR-009 §C): **one** mapper here, emitting real
``application/problem+json`` (`{type,title,status,detail}` per RFC-7807),
wired from `app.interfaces.api`. Status codes and the catch ordering are
preserved — the *body format* is the single sanctioned, characterized diff.

Pure: stdlib + Starlette/FastAPI only (no `app.domains`/`app.interfaces`
import — `core/*` is domain-agnostic). The billing-exception → status
handlers live in `app.interfaces.api` (the interface layer may import
`services.invoicing`); this module owns only the wire format + the generic
`HTTPException` handler, both gated to the REST surface so the Jinja web
routes keep their existing (HTML/redirect) error behaviour unchanged.
"""

from __future__ import annotations

from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse

PROBLEM_JSON = "application/problem+json"
API_PREFIX = "/api"

_TITLES: dict[int, str] = {
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    409: "Conflict",
    422: "Unprocessable Entity",
    500: "Internal Server Error",
}


def problem_response(status: int, detail: object | None) -> JSONResponse:
    """Build an RFC-7807 ``application/problem+json`` response.

    ``type`` is ``about:blank`` (RFC-7807 §4.2: the status code carries the
    semantics), ``title`` the HTTP reason phrase, ``status`` the code, and
    ``detail`` the human-readable message (omitted when empty).
    """
    body: dict[str, object] = {
        "type": "about:blank",
        "title": _TITLES.get(status, "Error"),
        "status": status,
    }
    if detail is not None and detail != "":
        body["detail"] = detail
    return JSONResponse(body, status_code=status, media_type=PROBLEM_JSON)


def is_api_request(request: Request) -> bool:
    """True for the REST surface only — web (Jinja) errors stay HTML/default."""
    return bool(request.url.path.startswith(API_PREFIX))


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Generic `HTTPException` → problem+json on the REST surface.

    Off the REST surface this reproduces FastAPI's default body
    (``{"detail": …}``) so the web UI's error behaviour is byte-identical.
    """
    if is_api_request(request):
        return problem_response(exc.status_code, exc.detail)
    return JSONResponse(
        {"detail": exc.detail},
        status_code=exc.status_code,
        headers=getattr(exc, "headers", None),
    )
