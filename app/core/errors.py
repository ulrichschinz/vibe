"""app.core.errors — shared error types + central RFC-7807 mapper.

Placeholder until Schritt 8. Ist: `routes/api.py` coerces RFC-7807 error
bodies inline per endpoint (a Schritt-0.5 characterization breakpoint).
Soll: one mapper here, called from `interfaces/api`, replaces the inline
coercion. Empty by design in Schritt 2.
"""
