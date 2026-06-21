"""Small operational CLI.

Usage:
    python -m app.cli seed-admin      # create/ensure the bootstrap org + first ADMIN
    python -m app.cli seed-demo       # seed-admin + sample employees & audit activity
    python -m app.cli seed-customers  # one-time import of the GST + Income-Tax registers

Kept dependency-free (no Typer/Click) so it runs anywhere the app runs.
"""
from __future__ import annotations

import re
import sys

from sqlalchemy import select

from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.enums import UserRole
from app.models.organization import Organization
from app.models.user import User

logger = get_logger(__name__)


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "org"


def seed_admin() -> None:
    """Ensure a bootstrap organization with one ADMIN user.

    Creates the org (from ``SUPERADMIN_ORG_NAME``) and an ADMIN user (from
    ``SUPERADMIN_EMAIL`` / ``SUPERADMIN_PASSWORD``). If the user already exists,
    its password is reset and it is (re)promoted to ADMIN and reactivated.
    """
    email = settings.SUPERADMIN_EMAIL.lower()
    org_name = settings.SUPERADMIN_ORG_NAME

    with SessionLocal() as db:
        existing = db.execute(
            select(User).where(User.email == email)
        ).scalar_one_or_none()

        if existing:
            existing.hashed_password = hash_password(settings.SUPERADMIN_PASSWORD)
            existing.is_active = True
            existing.role = UserRole.ADMIN
            db.commit()
            logger.info("Admin %s already existed — password reset, role=ADMIN.", email)
            return

        slug = _slugify(org_name)
        org = db.execute(
            select(Organization).where(Organization.slug == slug)
        ).scalar_one_or_none()
        if org is None:
            org = Organization(name=org_name, slug=slug)
            db.add(org)
            db.flush()  # assign org.id

        user = User(
            organization_id=org.id,
            email=email,
            hashed_password=hash_password(settings.SUPERADMIN_PASSWORD),
            full_name="Organization Admin",
            role=UserRole.ADMIN,
            is_active=True,
        )
        db.add(user)
        db.commit()
        logger.info("Admin %s created in organization '%s'.", email, org_name)


def seed_demo() -> None:
    """Seed realistic demo data on top of ``seed-admin``.

    Creates a handful of employees in the bootstrap org and generates a little
    audit activity (one promotion, one deactivation) by driving the real service
    — so the audit log has something to show. Idempotent: existing people are
    reused and already-applied changes no-op (so no duplicate audit rows).
    """
    seed_admin()

    from app.features.employees import schemas as emp_schemas
    from app.features.employees.service import EmployeeService

    email = settings.SUPERADMIN_EMAIL.lower()
    people = [
        ("Priya Raman", "9876500001", "priya.demo@example.com", "Senior Electrician"),
        ("Arun Kumar", "9876500002", "arun.demo@example.com", "Plumber"),
        ("Deepa Suresh", "9876500003", "deepa.demo@example.com", "AC Technician"),
        ("Vikram Nair", "9876500004", "vikram.demo@example.com", "Office Manager"),
    ]

    with SessionLocal() as db:
        admin = db.execute(select(User).where(User.email == email)).scalar_one()
        service = EmployeeService(db)

        created: dict[str, User] = {}
        for name, phone, mail, designation in people:
            existing = db.execute(
                select(User).where(User.phone == phone)
            ).scalar_one_or_none()
            if existing is not None:
                created[phone] = existing
                continue
            created[phone] = service.create(
                admin,
                emp_schemas.EmployeeCreate(
                    full_name=name,
                    phone=phone,
                    email=mail,
                    designation=designation,
                    password="Password123!",
                ),
            )

        # Generate sample audit activity (no-ops on re-run).
        service.set_role(admin, created["9876500004"].id, UserRole.ADMIN)   # promotion
        service.set_active(admin, created["9876500003"].id, False)          # deactivation

        logger.info("Demo data seeded (org='%s').", settings.SUPERADMIN_ORG_NAME)


def seed_customers() -> None:
    """One-time import of the legacy GST + Income-Tax client registers.

    Imports into the bootstrap admin's organization and applies duplicate
    detection (GST > PAN > Mobile > Email), so re-running never creates
    duplicates. Reads local CSV/XLSX under ``CUSTOMER_SEED_DIR`` if present,
    otherwise the shared Google Sheets. Not exposed to end users.
    """
    seed_admin()

    from app.features.customers.seed import import_customers

    email = settings.SUPERADMIN_EMAIL.lower()
    with SessionLocal() as db:
        admin = db.execute(select(User).where(User.email == email)).scalar_one()
        summary = import_customers(db, admin)

    logger.info("Customer import complete: %s", summary)
    if summary.errors:
        for err in summary.errors:
            logger.warning("  - %s", err)
        print("\nCustomer import finished WITH WARNINGS:")
        for err in summary.errors:
            print(f"  ! {err}")
    print(
        f"\nImported customers — created={summary.created}, "
        f"updated={summary.updated}, skipped(exact dup)={summary.skipped}."
    )


_COMMANDS = {
    "seed-admin": seed_admin,
    "seed-demo": seed_demo,
    "seed-customers": seed_customers,
}


def main() -> int:
    configure_logging()
    if len(sys.argv) < 2 or sys.argv[1] not in _COMMANDS:
        print(f"Usage: python -m app.cli [{' | '.join(_COMMANDS)}]")
        return 1
    _COMMANDS[sys.argv[1]]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
