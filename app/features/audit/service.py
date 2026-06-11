"""Audit log read service (admin-facing). Always scoped to the caller's org."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.features.audit import schemas
from app.features.audit.repository import AuditRepository
from app.models.audit_log import AuditLog
from app.models.enums import AuditAction
from app.models.user import User


class AuditService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = AuditRepository(db)

    def list(
        self,
        admin: User,
        *,
        action: AuditAction | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> schemas.AuditLogListResponse:
        if admin.organization_id is None:
            raise ValidationError("This account is not associated with an organization")

        rows, total = self.repo.list(
            organization_id=admin.organization_id,
            action=action,
            page=page,
            page_size=page_size,
        )
        return schemas.AuditLogListResponse(
            items=[self._to_read(r) for r in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    @staticmethod
    def _to_read(entry: AuditLog) -> schemas.AuditLogRead:
        return schemas.AuditLogRead(
            id=entry.id,
            action=entry.action,
            old_role=entry.old_role,
            new_role=entry.new_role,
            performed_by_user_id=entry.performed_by_user_id,
            performed_by_name=entry.performed_by.full_name if entry.performed_by else None,
            affected_user_id=entry.affected_user_id,
            affected_user_name=entry.affected_user.full_name if entry.affected_user else None,
            timestamp=entry.created_at,
        )
