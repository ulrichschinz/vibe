from sqlmodel import create_engine, SQLModel, Session
from sqlalchemy import text
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./leads.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


def create_db():
    SQLModel.metadata.create_all(engine)
    # Safe additive migrations for new nullable columns
    _safe_add_column("ALTER TABLE lead ADD COLUMN salutation TEXT")


def _safe_add_column(stmt: str):
    with engine.connect() as conn:
        try:
            conn.execute(text(stmt))
            conn.commit()
        except Exception:
            pass  # Column already exists


def get_session():
    with Session(engine) as session:
        yield session
