"""Small operational CLI.

Usage:
    python -m app.cli seed-superadmin     # create/update the platform super admin

Kept dependency-free (no Typer/Click) so it runs anywhere the app runs.
"""
from __future__ import annotations

import sys

from sqlalchemy import select

from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.enums import UserRole
from app.models.user import User

logger = get_logger(__name__)


def seed_superadmin() -> None:
    """Create the super admin from env vars, or reset its password if it exists."""
    email = settings.SUPERADMIN_EMAIL.lower()
    with SessionLocal() as db:
        existing = db.execute(
            select(User).where(User.email == email)
        ).scalar_one_or_none()

        if existing:
            existing.hashed_password = hash_password(settings.SUPERADMIN_PASSWORD)
            existing.is_active = True
            existing.role = UserRole.SUPER_ADMIN
            db.commit()
            logger.info("Super admin %s already existed — password reset.", email)
            return

        user = User(
            email=email,
            hashed_password=hash_password(settings.SUPERADMIN_PASSWORD),
            full_name="Platform Super Admin",
            role=UserRole.SUPER_ADMIN,
            organization_id=None,
            is_active=True,
        )
        db.add(user)
        db.commit()
        logger.info("Super admin %s created.", email)


_COMMANDS = {"seed-superadmin": seed_superadmin}


def main() -> int:
    configure_logging()
    if len(sys.argv) < 2 or sys.argv[1] not in _COMMANDS:
        print(f"Usage: python -m app.cli [{' | '.join(_COMMANDS)}]")
        return 1
    _COMMANDS[sys.argv[1]]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
