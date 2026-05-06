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
from models import User, UserRole
from sqlmodel import Session, select
from services.auth import hash_password, NeedsLoginException
from routes import leads, proposals, api
from routes import auth as auth_routes
from routes import admin as admin_routes
from routes import ai as ai_routes

BRAND_DIR = Path(__file__).parent.parent / "brand"
STATIC_DIR = Path(__file__).parent / "static"


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db()
    bootstrap_admin()
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

app.mount("/static/brand", StaticFiles(directory=str(BRAND_DIR)), name="brand")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.exception_handler(NeedsLoginException)
async def needs_login_handler(request: Request, exc: NeedsLoginException):
    return RedirectResponse(url="/login", status_code=303)


app.include_router(auth_routes.router)
app.include_router(admin_routes.router)
app.include_router(ai_routes.router)
app.include_router(leads.router)
app.include_router(proposals.router)
app.include_router(api.router)
