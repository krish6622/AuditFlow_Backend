"""Dashboard API (``/api/v1/dashboard``)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core import rbac
from app.core.dependencies import require_permissions
from app.db.session import get_db
from app.features.dashboard import schemas
from app.features.dashboard.service import DashboardService
from app.models.user import User

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/summary", response_model=schemas.DashboardSummary)
def dashboard_summary(
    current_user: User = Depends(require_permissions(rbac.REPORT_VIEW)),
    db: Session = Depends(get_db),
) -> schemas.DashboardSummary:
    """KPI totals, month-over-month deltas, and recent work orders for the org."""
    return DashboardService(db).summary(current_user)
