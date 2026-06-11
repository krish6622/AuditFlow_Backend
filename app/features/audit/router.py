"""Audit log API (``/api/v1/audit-logs``) — Organization Admin only.

Read-only. Scoped to the caller's organization (rule 6: an admin can only ever
see their own org's trail). Newest entries first.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core import rbac
from app.core.dependencies import require_permissions
from app.db.session import get_db
from app.features.audit import schemas
from app.features.audit.service import AuditService
from app.models.enums import AuditAction
from app.models.user import User

router = APIRouter(prefix="/audit-logs", tags=["Audit"])


def get_service(db: Session = Depends(get_db)) -> AuditService:
    return AuditService(db)


@router.get("", response_model=schemas.AuditLogListResponse)
def list_audit_logs(
    current_user: User = Depends(require_permissions(rbac.AUDIT_VIEW)),
    service: AuditService = Depends(get_service),
    action: AuditAction | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> schemas.AuditLogListResponse:
    """List the organization's audit trail, optionally filtered by action."""
    return service.list(current_user, action=action, page=page, page_size=page_size)
