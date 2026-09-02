"""
db.py — Database engine setup and session factory.

Defaults to SQLite locally (zero config).
Set DATABASE_URL env var to a Postgres connection string for production.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from backend.models import Base

load_dotenv()

# ─────────────────────────────────────────────
# Engine — SQLite locally, Postgres in prod
# ─────────────────────────────────────────────

DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./bookkeeping.db")

# SQLite needs connect_args; Postgres does not
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    echo=False,          # set True for SQL debug logging
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ─────────────────────────────────────────────
# Public helpers
# ─────────────────────────────────────────────

def init_db() -> None:
    """Create all tables if they don't already exist."""
    Base.metadata.create_all(bind=engine)
    print(f"[db] Tables initialised — using: {DATABASE_URL.split('://')[0]}")


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """Context-manager session for use outside FastAPI dependency injection."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db_session() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a DB session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def health_check() -> bool:
    """Quick connectivity test — returns True if the DB is reachable."""
    try:
        with get_db() as db:
            db.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        print(f"[db] Health check failed: {exc}")
        return False
