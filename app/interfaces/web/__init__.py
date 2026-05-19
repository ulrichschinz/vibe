"""interfaces.web — Jinja2 UI routers (Schritt 8).

`register(app)` wires the web delivery layer:

1. **Auto-discovery (Scaffold-Vertrag "Registrierungs-Mechanismus"):**
   it iterates `app.domains.*` and includes any `router` a domain exposes
   (a freshly scaffolded `make new-domain X --kind=web` lands its handlers
   in `app/domains/X/router.py`; the interface picks it up with **zero**
   central-registry edits). No existing domain ships a router yet, so this
   currently yields nothing — it is the forward mechanism.
2. The moved interface-organized web routers (`leads, proposals, invoices,
   admin, ai, auth`) — interface-shaped, not domain-shaped, so they live
   here, not under `domains/*/router.py`.

import-linter: this package may import `domains/*/{router,service,schemas}`,
`core/*`, `shared/*` — not `domains/*/models` (it does so only transitively
via the moved handlers' direct model imports, which `allow_indirect_imports`
permits, exactly as the Schritt-7 mcp rule; ADR-009 §G).
"""

from __future__ import annotations

import importlib
import pkgutil

from fastapi import FastAPI

from app import domains as _domains_pkg  # module-level alias: the

# `register(app)`/`_discover_domain_routers(app)` params shadow the `app`
# package name, so the domain auto-discovery must reach the package via
# this alias, not `app.domains`.
from app.interfaces.web import admin, ai, auth, invoices, leads, proposals

_WEB_ROUTERS = (auth, admin, ai, leads, proposals, invoices)


def _discover_domain_routers(app: FastAPI) -> None:
    """Include `router` from every `app.domains.<x>.router` that exists.

    The Scaffold-Vertrag forward mechanism: a new domain is one command and
    needs no central registry patch. Domains without a `router` module are
    skipped silently (they are pure logic/data packages today).
    """
    for mod in pkgutil.iter_modules(_domains_pkg.__path__):
        try:
            router_mod = importlib.import_module(f"app.domains.{mod.name}.router")
        except ModuleNotFoundError:
            continue
        router = getattr(router_mod, "router", None)
        if router is not None:
            app.include_router(router)


def register(app: FastAPI) -> None:
    _discover_domain_routers(app)
    for module in _WEB_ROUTERS:
        app.include_router(module.router)
