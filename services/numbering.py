from sqlmodel import Session, select, func
from datetime import datetime


def next_proposal_number(session: Session) -> str:
    from app.domains.proposals.models import Proposal
    year = datetime.utcnow().year
    prefix = f"AR-{year}-"
    count = session.exec(
        select(func.count(Proposal.id)).where(Proposal.number.like(f"{prefix}%"))
    ).one()
    return f"{prefix}{count + 1:03d}"
