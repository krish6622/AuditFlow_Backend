"""Employee management business logic.

Employees are ``User`` rows with ``role = employee`` belonging to the admin's
organization. Phone is the primary login identity (always required and unique);
email is optional and, when present, must be unique so it can also be used to
sign in.
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.core.security import hash_password
from app.features.audit.repository import AuditRepository
from app.features.employees import schemas
from app.features.employees.repository import EmployeeRepository
from app.models.enums import AuditAction, UserRole
from app.models.user import User

logger = get_logger(__name__)

# Surfaced to the client (and the UI) when a guard blocks removing the last admin.
LAST_ADMIN_MESSAGE = "At least one Admin must exist in the organization."


class EmployeeService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = EmployeeRepository(db)
        self.audit = AuditRepository(db)

    @staticmethod
    def _org(admin: User) -> uuid.UUID:
        if admin.organization_id is None:
            raise ValidationError("This account is not associated with an organization")
        return admin.organization_id

    def list(self, admin: User, *, search: str | None = None) -> list[User]:
        return self.repo.list(organization_id=self._org(admin), search=search)

    def get(self, admin: User, employee_id: uuid.UUID) -> User:
        emp = self.repo.get(organization_id=self._org(admin), user_id=employee_id)
        if emp is None:
            raise NotFoundError("Employee not found")
        return emp

    def create(self, admin: User, data: schemas.EmployeeCreate) -> User:
        org_id = self._org(admin)
        email = (data.email or "").strip().lower() or None
        phone = data.phone.strip()

        if self.repo.phone_taken(phone):
            raise ConflictError("An account with this phone number already exists")
        if email and self.repo.email_taken(email):
            raise ConflictError("An account with this email already exists")

        employee = User(
            organization_id=org_id,
            role=UserRole.EMPLOYEE,
            full_name=data.full_name.strip(),
            phone=phone,
            email=email,
            designation=(data.designation or "").strip() or None,
            hashed_password=hash_password(data.password),
            is_active=data.is_active,
        )
        self.repo.add(employee)
        self.db.commit()
        self.db.refresh(employee)
        logger.info("Employee %s created in org %s", employee.full_name, org_id)
        return employee

    def update(
        self, admin: User, employee_id: uuid.UUID, data: schemas.EmployeeUpdate
    ) -> User:
        emp = self.get(admin, employee_id)
        fields = data.model_dump(exclude_unset=True)

        if "phone" in fields and fields["phone"]:
            phone = fields["phone"].strip()
            if self.repo.phone_taken(phone, exclude_id=emp.id):
                raise ConflictError("An account with this phone number already exists")
            emp.phone = phone
        if "email" in fields:
            email = (fields["email"] or "").strip().lower() or None
            if email and self.repo.email_taken(email, exclude_id=emp.id):
                raise ConflictError("An account with this email already exists")
            emp.email = email
        if "full_name" in fields and fields["full_name"]:
            emp.full_name = fields["full_name"].strip()
        if "designation" in fields:
            emp.designation = (fields["designation"] or "").strip() or None
        if "is_active" in fields and fields["is_active"] is not None:
            emp.is_active = fields["is_active"]
        if fields.get("password"):
            emp.hashed_password = hash_password(fields["password"])

        self.db.commit()
        self.db.refresh(emp)
        return emp

    def set_active(self, admin: User, employee_id: uuid.UUID, is_active: bool) -> User:
        org_id = self._org(admin)
        member = self.get(admin, employee_id)

        if member.is_active == is_active:
            return member  # no-op — nothing to change or audit

        # Business rule: never deactivate the last remaining active admin.
        if (
            not is_active
            and member.role == UserRole.ADMIN
            and member.is_active
            and self.repo.count_active_admins(organization_id=org_id) <= 1
        ):
            raise ConflictError(LAST_ADMIN_MESSAGE)

        member.is_active = is_active
        self.audit.record(
            organization_id=org_id,
            performed_by_user_id=admin.id,
            affected_user_id=member.id,
            action=AuditAction.STATUS_ACTIVATED if is_active else AuditAction.STATUS_DEACTIVATED,
        )
        self.db.commit()
        self.db.refresh(member)
        logger.info("User %s active=%s (by %s)", member.id, is_active, admin.id)
        return member

    def set_role(
        self, admin: User, employee_id: uuid.UUID, new_role: UserRole
    ) -> User:
        """Promote an employee to ADMIN or demote an admin to EMPLOYEE.

        Authorization (only admins may call) is enforced by the route's
        ``EMPLOYEE_MANAGE`` permission. ``get`` scopes lookup to the admin's own
        organization, so cross-org targets surface as 404 (rule 6). Employees
        lack the permission entirely, so they can never change any role (rule 5).
        """
        org_id = self._org(admin)
        member = self.get(admin, employee_id)

        if member.role == new_role:
            return member  # no-op — already in the requested role

        # Demotion (ADMIN -> EMPLOYEE) must not remove the last active admin.
        # This also blocks the last admin demoting themselves (rule 2).
        if (
            member.role == UserRole.ADMIN
            and new_role == UserRole.EMPLOYEE
            and member.is_active
            and self.repo.count_active_admins(organization_id=org_id) <= 1
        ):
            raise ConflictError(LAST_ADMIN_MESSAGE)

        old_role = member.role
        member.role = new_role
        action = (
            AuditAction.ROLE_PROMOTED
            if new_role == UserRole.ADMIN
            else AuditAction.ROLE_DEMOTED
        )
        self.audit.record(
            organization_id=org_id,
            performed_by_user_id=admin.id,
            affected_user_id=member.id,
            action=action,
            old_role=old_role,
            new_role=new_role,
        )
        self.db.commit()
        self.db.refresh(member)
        logger.info(
            "User %s role %s -> %s (by %s)", member.id, old_role.value, new_role.value, admin.id
        )
        return member
