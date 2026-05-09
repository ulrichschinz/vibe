from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

from database import create_db, engine
from models import User, UserRole, IssuerProfile
import services.invoicing.immutability  # noqa: F401  registers SA event listeners
from sqlmodel import Session, select
from services.auth import hash_password, NeedsLoginException
from routes import leads, proposals, api, invoices
from routes import auth as auth_routes
from routes import admin as admin_routes
from routes import ai as ai_routes
from routes.mcp import mcp_app
from services.mcp_server import mcp as mcp_server

STATIC_DIR = Path(__file__).parent / "static"
BRAND_DIR = STATIC_DIR / "brand"


def bootstrap_admin():
    email = os.getenv("ADMIN_EMAIL")
    password = os.getenv("ADMIN_PASSWORD")
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
        legal_name = os.getenv("ISSUER_LEGAL_NAME")
        if not legal_name:
            # Without a name we can't construct a meaningful row; skip and let
            # the admin fill it in via the UI before the first finalize.
            return
        issuer = IssuerProfile(
            id=1,
            legal_name=legal_name,
            street=os.getenv("ISSUER_STREET", ""),
            postal_code=os.getenv("ISSUER_POSTAL_CODE", ""),
            city=os.getenv("ISSUER_CITY", ""),
            country_code=os.getenv("ISSUER_COUNTRY_CODE", "DE"),
            steuernummer=os.getenv("ISSUER_STEUERNUMMER") or None,
            ust_id=os.getenv("ISSUER_USTID") or None,
            is_kleinunternehmer=os.getenv("ISSUER_KLEINUNTERNEHMER", "false").lower() == "true",
            bank_holder=os.getenv("ISSUER_BANK_HOLDER", ""),
            bank_iban=os.getenv("ISSUER_BANK_IBAN", ""),
            bank_bic=os.getenv("ISSUER_BANK_BIC") or None,
            contact_email=os.getenv("ISSUER_CONTACT_EMAIL", ""),
            contact_phone=os.getenv("ISSUER_CONTACT_PHONE") or None,
        )
        session.add(issuer)
        session.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db()
    bootstrap_admin()
    bootstrap_issuer()
    # MCP session manager's task group must live for the app's lifetime
    async with mcp_server.session_manager.run():
        yield


app = FastAPI(title="Vibe", lifespan=lifespan)


@app.middleware("http")
async def attach_user(request: Request, call_next):
    # Runs after SessionMiddleware (added last = outermost = runs first).
    # Sets request.state.user so base.html can render user info without per-route injection.
    user_id = request.session.get("user_id")
    request.state.user = None
    if user_id:
        with Session(engine) as session:
            user = session.get(User, user_id)
            if user and user.is_active:
                request.state.user = user
    return await call_next(request)


app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "dev-secret-change-me"))

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.exception_handler(NeedsLoginException)
async def needs_login_handler(request: Request, exc: NeedsLoginException):
    return RedirectResponse(url="/login", status_code=303)


app.include_router(auth_routes.router)
app.include_router(admin_routes.router)
app.include_router(ai_routes.router)
app.include_router(leads.router)
app.include_router(proposals.router)
app.include_router(invoices.router)
app.include_router(api.router)
app.mount("/mcp", mcp_app)
