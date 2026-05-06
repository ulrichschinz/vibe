from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlmodel import Session, select
from typing import Optional

from database import get_session
from models import AiSettings
from services.auth import require_editor
from services.ai import generate_text

router = APIRouter(prefix="/ai")


class GenerateRequest(BaseModel):
    field: str
    notes: str = ""
    lead_name: Optional[str] = None
    lead_company: Optional[str] = None
    proposal_title: Optional[str] = None
    service_title: Optional[str] = None


@router.post("/generate")
def ai_generate(
    payload: GenerateRequest,
    session: Session = Depends(get_session),
    _=Depends(require_editor),
):
    settings = session.get(AiSettings, 1)
    if not settings or not settings.is_active or not settings.api_key:
        raise HTTPException(status_code=503, detail="KI nicht konfiguriert. Bitte unter Admin → KI einrichten.")

    context = {
        "lead_name": payload.lead_name,
        "lead_company": payload.lead_company,
        "proposal_title": payload.proposal_title,
        "service_title": payload.service_title,
    }

    try:
        text = generate_text(payload.field, payload.notes, context, settings)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"KI-Fehler: {e}")

    return {"text": text}
