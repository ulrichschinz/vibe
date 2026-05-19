"""interfaces.web.admin — Jinja UI: user/api-key/issuer/VIES admin
(Schritt 8, moved verbatim from `routes/admin.py`; model imports point at
`app.core.*`/`app.domains.*` directly).
"""

import secrets
from datetime import datetime
from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from app.core.config import get_settings
from database import get_session
from app.core.identity import User, UserRole, ApiKey
from app.core.ai_settings import AiProvider
from app.core import identity_service, ai_settings_service
from app.domains.billing.service import IssuerProfile, ViesAuditEntry
from app.domains.billing import service as billing_service
from app.shared.labels import USER_ROLE_LABELS, AI_PROVIDER_LABELS
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
    return templates.TemplateResponse(
        "admin/user_form.html",
        {
            "request": request,
            "user": None,
            "action": "/admin/users",
            "error": None,
        },
    )


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
        return templates.TemplateResponse(
            "admin/user_form.html",
            {
                "request": request,
                "user": None,
                "action": "/admin/users",
                "error": "E-Mail bereits vergeben.",
            },
            status_code=400,
        )
    identity_service.create_user(
        session,
        name=name,
        email=email,
        hashed_password=hash_password(password),
        role=UserRole(role),
    )
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
    return templates.TemplateResponse(
        "admin/user_form.html",
        {
            "request": request,
            "user": user,
            "action": f"/admin/users/{user_id}/update",
            "error": None,
        },
    )


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
    return templates.TemplateResponse(
        "admin/api_keys.html",
        {
            "request": request,
            "keys": keys,
            "new_key": None,
            "app_host": get_settings().app_host,
        },
    )


@router.post("/api-keys", response_class=HTMLResponse)
def api_key_create(
    request: Request,
    label: str = Form(...),
    session: Session = Depends(get_session),
    admin=Depends(require_admin),
):
    raw_key = secrets.token_urlsafe(32)
    identity_service.create_api_key(
        session,
        label=label,
        key_hash=hash_api_key(raw_key),
        created_by_id=admin.id,
    )
    keys = session.exec(select(ApiKey).order_by(ApiKey.created_at.desc())).all()
    return templates.TemplateResponse(
        "admin/api_keys.html",
        {
            "request": request,
            "keys": keys,
            "new_key": raw_key,
            "app_host": get_settings().app_host,
        },
    )


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
    settings = ai_settings_service.get_ai_settings_or_default(session)
    return templates.TemplateResponse(
        "admin/ai_settings.html",
        {
            "request": request,
            "settings": settings,
            "saved": False,
        },
    )


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
    settings = ai_settings_service.get_or_create_ai_settings(session)
    settings.provider = AiProvider(provider)
    settings.model = model.strip() or "claude-sonnet-4-6"
    settings.is_active = is_active == "on"
    if api_key.strip():
        settings.api_key = api_key.strip()
    session.add(settings)
    session.commit()
    session.refresh(settings)
    return templates.TemplateResponse(
        "admin/ai_settings.html",
        {
            "request": request,
            "settings": settings,
            "saved": True,
        },
    )


# ── Issuer (Rechnungs-Aussteller) ─────────────────────────────────────────


@router.get("/issuer", response_class=HTMLResponse)
def issuer_form(
    request: Request, session: Session = Depends(get_session), _=Depends(require_admin)
):
    issuer = session.get(IssuerProfile, 1)
    return templates.TemplateResponse(
        "admin/issuer.html",
        {
            "request": request,
            "issuer": issuer,
            "saved": request.query_params.get("saved") == "1",
            "msg": request.query_params.get("msg"),
        },
    )


@router.post("/issuer", response_class=RedirectResponse)
def issuer_save(
    legal_name: str = Form(...),
    street: str = Form(...),
    postal_code: str = Form(...),
    city: str = Form(...),
    country_code: str = Form("DE"),
    steuernummer: str = Form(""),
    ust_id: str = Form(""),
    is_kleinunternehmer: str = Form("off"),
    bank_holder: str = Form(""),
    bank_iban: str = Form(""),
    bank_bic: str = Form(""),
    contact_email: str = Form(""),
    contact_phone: str = Form(""),
    default_payment_terms_days: int = Form(14),
    default_payment_terms_text: str = Form("Zahlbar innerhalb 14 Tagen ohne Abzug."),
    session: Session = Depends(get_session),
    _=Depends(require_admin),
):
    issuer = billing_service.get_or_create_issuer_web(
        session,
        legal_name=legal_name,
        street=street,
        postal_code=postal_code,
        city=city,
    )
    issuer.legal_name = legal_name
    issuer.street = street
    issuer.postal_code = postal_code
    issuer.city = city
    issuer.country_code = country_code or "DE"
    issuer.steuernummer = steuernummer.strip() or None
    issuer.ust_id = ust_id.strip() or None
    issuer.is_kleinunternehmer = is_kleinunternehmer == "on"
    issuer.bank_holder = bank_holder
    issuer.bank_iban = bank_iban
    issuer.bank_bic = bank_bic.strip() or None
    issuer.contact_email = contact_email
    issuer.contact_phone = contact_phone.strip() or None
    issuer.default_payment_terms_days = int(default_payment_terms_days)
    issuer.default_payment_terms_text = default_payment_terms_text
    issuer.updated_at = datetime.utcnow()
    session.add(issuer)
    session.commit()
    return RedirectResponse("/admin/issuer?saved=1", status_code=303)


@router.get("/vies-overrides", response_class=HTMLResponse)
def vies_overrides(
    request: Request, session: Session = Depends(get_session), _=Depends(require_admin)
):
    audits = session.exec(
        select(ViesAuditEntry).order_by(ViesAuditEntry.queried_at.desc()).limit(100)
    ).all()
    return templates.TemplateResponse(
        "admin/vies_overrides.html",
        {
            "request": request,
            "audits": audits,
        },
    )
