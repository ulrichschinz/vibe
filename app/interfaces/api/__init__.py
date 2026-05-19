"""interfaces.api — REST router + central RFC-7807 error mapping (Schritt 8).

`register(app)` mounts the REST router and installs the central
`application/problem+json` exception handlers (ADR-009 §C), replacing the
former inline per-endpoint `HTTPException` coercion in `routes/api.py`:

- generic `HTTPException` → `app.core.errors.http_exception_handler`
  (problem+json on the REST surface, FastAPI-default body off it so the
  Jinja web routes are byte-identical);
- `InvoiceValidationError` (⊂ `FinalizeError`) → **422**;
- `FinalizeError` → **409**.

FastAPI dispatches the most specific handler first, so a raised
`InvoiceValidationError` maps to 422 even though it subclasses
`FinalizeError` — the exact 422-before-409 ordering the Schritt-0.5
characterization pinned (`test_double_finalize_is_422_and_lines_on_
finalized_is_409`).
"""

from __future__ import annotations

from fastapi import FastAPI
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.errors import http_exception_handler, problem_response
from app.interfaces.api.router import router
from services.invoicing.finalize import FinalizeError, InvoiceValidationError


async def _invoice_validation_handler(
    request: Request, exc: InvoiceValidationError
) -> JSONResponse:
    return problem_response(422, str(exc))


async def _finalize_error_handler(request: Request, exc: FinalizeError) -> JSONResponse:
    return problem_response(409, str(exc))


def register(app: FastAPI) -> None:
    app.include_router(router)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(InvoiceValidationError, _invoice_validation_handler)
    app.add_exception_handler(FinalizeError, _finalize_error_handler)
