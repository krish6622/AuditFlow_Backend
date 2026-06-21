"""Pydantic models for the audit log API (admin-facing, read-only)."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import AuditAction, UserRole


class AuditLogRead(BaseModel):
    """One audit entry, flattened with the actor/subject display names.

    ``performed_by_name`` / ``affected_user_name`` are NULL when the referenced
    user has since been removed (the FKs are ``ON DELETE SET NULL``).
    """

    id: uuid.UUID
    action: AuditAction
    old_role: UserRole | None
    new_role: UserRole | None
    performed_by_user_id: uuid.UUID | None
    performed_by_name: str | None
    affected_user_id: uuid.UUID | None
    affected_user_name: str | None
    # Set for customer-master changes (``entity_name`` is a snapshot that
    # survives a hard delete; ``customer_id`` is NULL once the row is gone).
    customer_id: uuid.UUID | None = None
    customer_name: str | None = None
    timestamp: datetime


class AuditLogListResponse(BaseModel):
    items: list[AuditLogRead]
    total: int
    page: int
    page_size: int
