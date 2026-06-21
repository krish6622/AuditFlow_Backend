"""Data access for the audit log, org-scoped.

The audit trail is append-only: this repository writes new entries and reads
them back, but never updates or deletes. Callers own the transaction (``record``
adds to the session; the surrounding service commits).
"""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.audit_log import AuditLog
from app.models.enums import AuditAction, UserRole


class AuditRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(
        self,
        *,
        organization_id: uuid.UUID,
        action: AuditAction | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[AuditLog], int]:
        """Return a page of audit entries (newest first) and the total count.

        Actor/subject relationships are eagerly loaded so the serializer can
        render display names without N+1 queries.
        """
        filters = [AuditLog.organization_id == organization_id]
        if action is not None:
            filters.append(AuditLog.action == action)

        total = self.db.execute(
            select(func.count()).select_from(AuditLog).where(*filters)
        ).scalar_one()

        rows = (
            self.db.execute(
                select(AuditLog)
                .where(*filters)
                .options(
                    joinedload(AuditLog.performed_by),
                    joinedload(AuditLog.affected_user),
                )
                .order_by(AuditLog.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            .scalars()
            .all()
        )
        return list(rows), total

    def list_for_customer(
        self, *, organization_id: uuid.UUID, customer_id: uuid.UUID, limit: int = 100
    ) -> list[AuditLog]:
        """The audit trail for one customer (newest first), actor eagerly loaded."""
        rows = (
            self.db.execute(
                select(AuditLog)
                .where(
                    AuditLog.organization_id == organization_id,
                    AuditLog.customer_id == customer_id,
                )
                .options(joinedload(AuditLog.performed_by))
                .order_by(AuditLog.created_at.desc())
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return list(rows)

    def record(
        self,
        *,
        organization_id: uuid.UUID,
        performed_by_user_id: uuid.UUID | None,
        affected_user_id: uuid.UUID | None = None,
        action: AuditAction,
        old_role: UserRole | None = None,
        new_role: UserRole | None = None,
        customer_id: uuid.UUID | None = None,
        entity_name: str | None = None,
    ) -> AuditLog:
        """Append one audit entry (not committed — the caller commits).

        User changes set ``affected_user_id``; customer changes set
        ``customer_id`` and snapshot the readable ``entity_name`` so the trail
        survives a hard delete (the FK is ``ON DELETE SET NULL``).
        """
        entry = AuditLog(
            organization_id=organization_id,
            performed_by_user_id=performed_by_user_id,
            affected_user_id=affected_user_id,
            action=action,
            old_role=old_role,
            new_role=new_role,
            customer_id=customer_id,
            entity_name=entity_name,
        )
        self.db.add(entry)
        return entry
