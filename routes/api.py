from fastapi import APIRouter, Depends, HTTPException, Header
from sqlmodel import Session, select
from datetime import datetime
import hashlib
import json
import os

from database import get_session
from models import Lead, LeadCreate, LeadRead, LeadPatch, LeadSource, ApiKey

router = APIRouter(prefix="/api", tags=["agent-api"])


def validate_api_key(key: str, session: Session) -> bool:
    """Pure validation. Used by both the FastAPI dependency and the MCP middleware.

    Updates last_used_at for DB-backed keys. Falls back to the legacy API_KEY env var
    so existing agents keep working.
    """
    if not key:
        return False

    key_hash = hashlib.sha256(key.encode()).hexdigest()
    db_key = session.exec(
        select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.is_active == True)
    ).first()
    if db_key:
        db_key.last_used_at = datetime.utcnow()
        session.add(db_key)
        session.commit()
        return True

    legacy = os.getenv("API_KEY", "")
    if legacy and key == legacy:
        return True

    return False


def verify_api_key(x_api_key: str = Header(default=""), session: Session = Depends(get_session)):
    if not x_api_key:
        raise HTTPException(status_code=401, detail="API key required")
    if not validate_api_key(x_api_key, session):
        raise HTTPException(status_code=401, detail="Invalid API key")


@router.post("/leads", response_model=LeadRead, status_code=201)
def api_create_lead(
    payload: LeadCreate,
    session: Session = Depends(get_session),
    _=Depends(verify_api_key),
):
    if not payload.name and not payload.company:
        raise HTTPException(status_code=422, detail="name oder company muss angegeben sein.")
    lead = Lead(
        name=payload.name,
        company=payload.company,
        email=payload.email,
        phone=payload.phone,
        source=payload.source,
        notes=payload.notes,
        tags=json.dumps(payload.tags) if payload.tags else None,
        agent_metadata=json.dumps(payload.agent_metadata) if payload.agent_metadata else None,
    )
    session.add(lead)
    session.commit()
    session.refresh(lead)
    return lead


@router.get("/leads", response_model=list[LeadRead])
def api_list_leads(
    stage: str | None = None,
    source: str | None = None,
    session: Session = Depends(get_session),
    _=Depends(verify_api_key),
):
    query = select(Lead)
    if stage:
        query = query.where(Lead.stage == stage)
    if source:
        query = query.where(Lead.source == source)
    return session.exec(query.order_by(Lead.created_at.desc())).all()


@router.get("/leads/{lead_id}", response_model=LeadRead)
def api_get_lead(
    lead_id: int,
    session: Session = Depends(get_session),
    _=Depends(verify_api_key),
):
    lead = session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead


@router.patch("/leads/{lead_id}", response_model=LeadRead)
def api_patch_lead(
    lead_id: int,
    payload: LeadPatch,
    session: Session = Depends(get_session),
    _=Depends(verify_api_key),
):
    lead = session.get(Lead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(lead, k, v)
    lead.updated_at = datetime.utcnow()
    session.add(lead)
    session.commit()
    session.refresh(lead)
    return lead
