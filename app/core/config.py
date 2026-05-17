"""app.core.config — central configuration (Schritt 3, pydantic-settings).

Single home for every environment variable. Replaces the scattered ad-hoc
env reads that were spread across 6 modules in the Ist state (database.py,
main.py, routes/admin.py, routes/api.py, services/mcp_server.py,
services/invoicing/archive.py).

Behaviour-preservation contract (roadmap discipline: *keine
Verhaltensänderung* every step):

- **Defaults are byte-identical** to the previous per-site fallbacks. No
  field is `required`, because no Ist site hard-failed on a missing var —
  making one required would be a behaviour change. The roadmap's
  "fail-fast on missing var" is the Soll *aspiration*; it materializes
  only for genuinely required vars in a later step, never by regressing
  observed behaviour here.
- **Per-call semantics preserved.** `get_settings()` returns a *fresh*
  `Settings()` on every call (deliberately not cached). Several Ist sites
  read the environment per call and the test suite `monkeypatch.setenv`s
  env per test (e.g. `INVOICE_ARCHIVE_ROOT`); a cached singleton would
  freeze those and change behaviour. A fresh instance re-reads
  `os.environ` each call — exactly the per-call stdlib env-read semantics
  it replaces. These are cold paths (startup, archive-on-finalize,
  api-key check), so the re-instantiation cost is irrelevant.
- **Raw values only.** All post-processing (`... or None`,
  `.lower() == "true"`) stays verbatim at the original call sites, so the
  exact value semantics are unchanged. Fields are typed `str`/`str | None`
  with the same defaults the previous fallbacks used — no pydantic bool
  coercion (which would differ from `.lower() == "true"`).

`.env` loading is intentionally NOT configured here: `main.py` keeps its
`load_dotenv()` call, which populates `os.environ` before `Settings()` is
constructed — preserving the existing dotenv semantics with zero shift.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process configuration, sourced from the environment.

    Field name (case-insensitively) == the env var name, matching the Ist
    per-site env keys one-to-one. Each default equals the previous per-site
    fallback exactly.
    """

    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    # database.py
    database_url: str = "sqlite:///./leads.db"

    # routes/api.py — legacy API_KEY fallback (read per request)
    api_key: str = ""

    # main.py — session signing (read at app construction)
    secret_key: str = "dev-secret-change-me"

    # services/mcp_server.py, routes/admin.py — public host for URLs
    app_host: str = ""

    # main.py bootstrap_admin() — both must be set or bootstrap is skipped
    admin_email: str | None = None
    admin_password: str | None = None

    # main.py bootstrap_issuer() — ENV seeds the singleton on first boot
    issuer_legal_name: str | None = None
    issuer_street: str = ""
    issuer_postal_code: str = ""
    issuer_city: str = ""
    issuer_country_code: str = "DE"
    issuer_steuernummer: str | None = None
    issuer_ustid: str | None = None
    # kept as str (not bool): the Ist site is `.lower() == "true"`, which
    # differs from pydantic bool parsing (e.g. "yes" -> False here, True there)
    issuer_kleinunternehmer: str = "false"
    issuer_bank_holder: str = ""
    issuer_bank_iban: str = ""
    issuer_bank_bic: str | None = None
    issuer_contact_email: str = ""
    issuer_contact_phone: str | None = None

    # services/invoicing/archive.py — archive root override (read per finalize)
    invoice_archive_root: str | None = None


def get_settings() -> Settings:
    """Return a fresh Settings instance (NOT cached — see module docstring).

    Re-reads os.environ on every call, preserving the per-call env-read
    semantics the Ist code relied on and the test suite's per-test
    `monkeypatch.setenv`.
    """
    return Settings()
