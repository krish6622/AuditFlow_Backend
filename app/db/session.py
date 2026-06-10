"""Database engine and session management.

A single engine/sessionmaker pair is created at import time. FastAPI routes
obtain a session via the ``get_db`` dependency, which guarantees the session is
closed (and rolled back on error) after each request.
"""
from __future__ import annotations

from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,      # transparently recover dropped connections (Neon idle)
    pool_size=5,
    max_overflow=10,
    future=True,
    echo=False,
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a transactional session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
