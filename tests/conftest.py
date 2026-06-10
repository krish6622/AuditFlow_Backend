"""Shared pytest fixtures.

Integration tests need a PostgreSQL database (the schema uses native UUID/ENUM
types). Point them at a throwaway database via ``TEST_DATABASE_URL``; if it is
unset or unreachable, the DB-backed tests are skipped (unit tests still run).

    # Windows PowerShell example:
    $env:TEST_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/elangovan_test"
    pytest
"""
from __future__ import annotations

import os
from typing import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL not set — skipping database integration tests")

    eng = create_engine(TEST_DATABASE_URL, future=True)
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"Test database unreachable: {exc}")

    from app.models import Base

    with eng.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture
def db_session(engine: Engine) -> Iterator[Session]:
    """A clean session per test; rolls back all changes afterwards."""
    TestSession = sessionmaker(bind=engine, expire_on_commit=False, class_=Session)
    session = TestSession()
    # Start from an empty users/orgs state for isolation.
    session.execute(text("TRUNCATE organizations, users RESTART IDENTITY CASCADE"))
    session.commit()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(engine: Engine, db_session: Session):
    """FastAPI TestClient wired to the test database session."""
    from fastapi.testclient import TestClient

    from app.db.session import get_db
    from app.main import app

    def _override_get_db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def org_admin(db_session: Session):
    """Create an active organization with one org-admin user."""
    from app.core.security import hash_password
    from app.models.enums import UserRole
    from app.models.organization import Organization
    from app.models.user import User

    org = Organization(name="Acme Plumbing", slug="acme-plumbing", is_active=True)
    db_session.add(org)
    db_session.flush()

    user = User(
        organization_id=org.id,
        email="admin@acme.test",
        hashed_password=hash_password("Password123!"),
        full_name="Acme Admin",
        role=UserRole.ORG_ADMIN,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user
