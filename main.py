from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from database import create_db, engine
from app.core.config import get_settings
from app.core.identity import User, UserRole
from app.domains.billing.models import IssuerProfile
import services.invoicing.immutability  # noqa: F401  registers SA event listeners
from sqlmodel import Session, select
from services.auth import hash_password, NeedsLoginException
from app.interfaces import api as api_iface
from app.interfaces import mcp as mcp_iface
from app.interfaces import web as web_iface

STATIC_DIR = Path(__file__).parent / "static"
BRAND_DIR = STATIC_DIR / "brand"


def bootstrap_admin():
    settings = get_settings()
    email = settings.admin_email
    password = settings.admin_password
    if not email or not password:
        return
    with Session(engine) as session:
        if session.exec(select(User)).first():
            return
        admin = User(
            email=email,
            name="Admin",
            hashed_password=hash_password(password),
            role=UserRole.admin,
        )
        session.add(admin)
        session.commit()


def bootstrap_issuer():
    """Seed the singleton IssuerProfile (id=1) from ENV on first boot.

    Subsequent boots see an existing row and do nothing — the admin manages
    the data via /admin/issuer afterwards. ENV values are only the bootstrap
    defaults, so changing ENV after first boot has no effect.
    """
    with Session(engine) as session:
        existing = session.get(IssuerProfile, 1)
        if existing is not None:
            return
        settings = get_settings()
        legal_name = settings.issuer_legal_name
        if not legal_name:
            # Without a name we can't construct a meaningful row; skip and let
            # the admin fill it in via the UI before the first finalize.
            return
        issuer = IssuerProfile(
            id=1,
            legal_name=legal_name,
            street=settings.issuer_street,
            postal_code=settings.issuer_postal_code,
            city=settings.issuer_city,
            country_code=settings.issuer_country_code,
            steuernummer=settings.issuer_steuernummer or None,
            ust_id=settings.issuer_ustid or None,
            is_kleinunternehmer=settings.issuer_kleinunternehmer.lower() == "true",
            bank_holder=settings.issuer_bank_holder,
            bank_iban=settings.issuer_bank_iban,
            bank_bic=settings.issuer_bank_bic or None,
            contact_email=settings.issuer_contact_email,
            contact_phone=settings.issuer_contact_phone or None,
        )
        session.add(issuer)
        session.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db()
    bootstrap_admin()
    bootstrap_issuer()
    # MCP session manager's task group must live for the app's lifetime
    async with mcp_iface.session_manager():
        yield


app = FastAPI(title="Vibe", lifespan=lifespan)


@app.middleware("http")
async def attach_user(request: Request, call_next):
    # Runs after SessionMiddleware (added last = outermost = runs first).
    # Sets request.state.user so base.html can render user info without per-route injection.
    request.state.user = None
    # Skip the DB lookup for paths that never render base.html. Static assets
    # used to fail with 500 on transient SQLite locks because each request
    # opened a transaction here just to ignore the result.
    path = request.url.path
    if path.startswith("/static") or path.startswith("/mcp") or path.startswith("/api"):
        return await call_next(request)
    user_id = request.session.get("user_id")
    if user_id:
        with Session(engine) as session:
            user = session.get(User, user_id)
            if user and user.is_active:
                request.state.user = user
    return await call_next(request)


app.add_middleware(SessionMiddleware, secret_key=get_settings().secret_key)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.exception_handler(NeedsLoginException)
async def needs_login_handler(request: Request, exc: NeedsLoginException):
    return RedirectResponse(url="/login", status_code=303)


# Schritt 8: the delivery layer is wired through app.interfaces.{web,api,mcp}
# instead of the old top-level routes/ modules. `web.register` includes the
# Jinja routers (+ Scaffold-Vertrag domain auto-discovery), `api.register`
# adds the REST router + the central RFC-7807 problem+json mapper, and
# `mcp.register` mounts the X-API-Key-gated FastMCP app at /mcp. The web
# routers keep their FastAPI-default error behaviour; only the REST surface
# gets problem+json (ADR-009).
web_iface.register(app)
api_iface.register(app)
mcp_iface.register(app)
