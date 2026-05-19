import hashlib
import bcrypt
from fastapi import Depends, HTTPException, Request
from sqlmodel import Session

from database import get_session
from app.core.identity import User, UserRole


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


class NeedsLoginException(Exception):
    pass


def require_login(request: Request, session: Session = Depends(get_session)) -> User:
    user_id = request.session.get("user_id")
    if not user_id:
        raise NeedsLoginException()
    user = session.get(User, user_id)
    if not user or not user.is_active:
        raise NeedsLoginException()
    request.state.user = user
    return user


def require_editor(user: User = Depends(require_login)) -> User:
    if user.role == UserRole.viewer:
        raise HTTPException(status_code=403, detail="Keine Berechtigung")
    return user


def require_admin(user: User = Depends(require_login)) -> User:
    if user.role != UserRole.admin:
        raise HTTPException(status_code=403, detail="Nur für Administratoren")
    return user
