import os
import secrets
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from database import get_session
from models import User, UserRole, ApiKey, USER_ROLE_LABELS, AiSettings, AiProvider, AI_PROVIDER_LABELS
from services.auth import require_admin, hash_password, hash_api_key

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="templates")
templates.env.globals["USER_ROLE_LABELS"] = USER_ROLE_LABELS
templates.env.globals["UserRole"] = UserRole
templates.env.globals["AI_PROVIDER_LABELS"] = AI_PROVIDER_LABELS
templates.env.globals["AiProvider"] = AiProvider


# ── Users ──────────────────────────────────────────────────────────────────

@router.get("/users", response_class=HTMLResponse)
def users_list(request: Request, session: Session = Depends(get_session), _=Depends(require_admin)):
    users = session.exec(select(User).order_by(User.created_at)).all()
    return templates.TemplateResponse("admin/users.html", {"request": request, "users": users})


@router.get("/users/new", response_class=HTMLResponse)
def user_new(request: Request, _=Depends(require_admin)):
    return templates.TemplateResponse("admin/user_form.html", {
        "request": request, "user": None, "action": "/admin/users", "error": None,
    })


@router.post("/users")
def user_create(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    session: Session = Depends(get_session),
    _=Depends(require_admin),
):
    if session.exec(select(User).where(User.email == email)).first():
        return templates.TemplateResponse("admin/user_form.html", {
            "request": request, "user": None, "action": "/admin/users",
            "error": "E-Mail bereits vergeben.",
        }, status_code=400)
    user = User(
        name=name,
        email=email,
        hashed_password=hash_password(password),
        role=UserRole(role),
    )
    session.add(user)
    session.commit()
    return RedirectResponse("/admin/users", status_code=303)


@router.get("/users/{user_id}/edit", response_class=HTMLResponse)
def user_edit(
    request: Request,
    user_id: int,
    session: Session = Depends(get_session),
    _=Depends(require_admin),
):
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse("admin/user_form.html", {
        "request": request, "user": user,
        "action": f"/admin/users/{user_id}/update", "error": None,
    })


@router.post("/users/{user_id}/update")
def user_update(
    user_id: int,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(""),
    role: str = Form(...),
    is_active: str = Form("off"),
    session: Session = Depends(get_session),
    _=Depends(require_admin),
):
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404)
    user.name = name
    user.email = email
    user.role = UserRole(role)
    user.is_active = is_active == "on"
    if password:
        user.hashed_password = hash_password(password)
    session.add(user)
    session.commit()
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/{user_id}/delete")
def user_delete(
    user_id: int,
    request: Request,
    session: Session = Depends(get_session),
    _=Depends(require_admin),
):
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404)
    if request.state.user and request.state.user.id == user_id:
        return RedirectResponse("/admin/users", status_code=303)
    session.delete(user)
    session.commit()
    return RedirectResponse("/admin/users", status_code=303)


# ── API Keys ───────────────────────────────────────────────────────────────

@router.get("/api-keys", response_class=HTMLResponse)
def api_keys_list(
    request: Request,
    session: Session = Depends(get_session),
    _=Depends(require_admin),
):
    keys = session.exec(select(ApiKey).order_by(ApiKey.created_at.desc())).all()
    return templates.TemplateResponse("admin/api_keys.html", {
        "request": request, "keys": keys, "new_key": None,
        "app_host": os.getenv("APP_HOST", ""),
    })


@router.post("/api-keys", response_class=HTMLResponse)
def api_key_create(
    request: Request,
    label: str = Form(...),
    session: Session = Depends(get_session),
    admin=Depends(require_admin),
):
    raw_key = secrets.token_urlsafe(32)
    key = ApiKey(
        label=label,
        key_hash=hash_api_key(raw_key),
        created_by_id=admin.id,
    )
    session.add(key)
    session.commit()
    keys = session.exec(select(ApiKey).order_by(ApiKey.created_at.desc())).all()
    return templates.TemplateResponse("admin/api_keys.html", {
        "request": request, "keys": keys, "new_key": raw_key,
        "app_host": os.getenv("APP_HOST", ""),
    })


@router.post("/api-keys/{key_id}/revoke")
def api_key_revoke(
    key_id: int,
    session: Session = Depends(get_session),
    _=Depends(require_admin),
):
    key = session.get(ApiKey, key_id)
    if key:
        key.is_active = False
        session.add(key)
        session.commit()
    return RedirectResponse("/admin/api-keys", status_code=303)


# ── AI Settings ────────────────────────────────────────────────────────────

@router.get("/ai", response_class=HTMLResponse)
def ai_settings_page(
    request: Request,
    session: Session = Depends(get_session),
    _=Depends(require_admin),
):
    settings = session.get(AiSettings, 1) or AiSettings()
    return templates.TemplateResponse("admin/ai_settings.html", {
        "request": request, "settings": settings, "saved": False,
    })


@router.post("/ai", response_class=HTMLResponse)
def ai_settings_save(
    request: Request,
    provider: str = Form(...),
    api_key: str = Form(""),
    model: str = Form("claude-sonnet-4-6"),
    is_active: str = Form("off"),
    session: Session = Depends(get_session),
    _=Depends(require_admin),
):
    settings = session.get(AiSettings, 1)
    if not settings:
        settings = AiSettings(id=1)
    settings.provider = AiProvider(provider)
    settings.model = model.strip() or "claude-sonnet-4-6"
    settings.is_active = is_active == "on"
    if api_key.strip():
        settings.api_key = api_key.strip()
    session.add(settings)
    session.commit()
    session.refresh(settings)
    return templates.TemplateResponse("admin/ai_settings.html", {
        "request": request, "settings": settings, "saved": True,
    })
