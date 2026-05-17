"""app.core.config — central configuration (placeholder until Schritt 3).

Soll: a single pydantic-settings model replaces every scattered ad-hoc
environment-variable read (Ist: 6 files reading the stdlib env directly —
database.py, main.py, routes/admin.py, routes/api.py,
services/mcp_server.py, services/invoicing/archive.py) and fails fast at
startup on a missing/invalid variable.

Entry point (Schritt 3): `Settings` (BaseSettings) + a cached accessor;
`app.core.db` will build its engine from it. Empty by design in Schritt 2
— the skeleton is created early so the move lands once, in place.
"""
