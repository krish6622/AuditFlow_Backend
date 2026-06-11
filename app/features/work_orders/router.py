"""Work Orders API (``/api/v1/work-orders``).

Authorization:
- create / edit / delete  → ``workorder:manage``      (Organization Admin)
- list / detail           → ``workorder:view_all``     (Organization Admin)

Every handler is tenant-scoped via the authenticated user's organization.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core import rbac
from app.core.dependencies import get_current_active_user, require_permissions
from app.db.session import get_db
from app.features.work_orders import schemas
from app.features.work_orders.service import WorkOrderService
from app.models.enums import WorkOrderStatus
from app.models.user import User

router = APIRouter(prefix="/work-orders", tags=["Work Orders"])


def get_service(db: Session = Depends(get_db)) -> WorkOrderService:
    return WorkOrderService(db)


@router.post(
    "",
    response_model=schemas.WorkOrderRead,
    status_code=status.HTTP_201_CREATED,
)
def create_work_order(
    data: schemas.WorkOrderCreate,
    current_user: User = Depends(require_permissions(rbac.WORKORDER_CREATE_REQUEST)),
    service: WorkOrderService = Depends(get_service),
) -> schemas.WorkOrderRead:
    """Create a work order.

    Admins may assign on create (→ ASSIGNED); employees raise a request that the
    service forces to AWAITING_ASSIGNMENT (no assignee/due date/status), stamped
    with ``requested_by``.
    """
    return schemas.WorkOrderRead.model_validate(service.create(current_user, data))


@router.get("", response_model=schemas.WorkOrderListResponse)
def list_work_orders(
    current_user: User = Depends(require_permissions(rbac.WORKORDER_VIEW_ALL)),
    service: WorkOrderService = Depends(get_service),
    status_filter: WorkOrderStatus | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None, max_length=255),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> schemas.WorkOrderListResponse:
    """List work orders with optional status filter, text search, and pagination."""
    return service.list(
        current_user,
        status=status_filter,
        search=search,
        page=page,
        page_size=page_size,
    )


@router.get("/mine", response_model=schemas.WorkOrderListResponse)
def list_my_work_orders(
    current_user: User = Depends(get_current_active_user),
    service: WorkOrderService = Depends(get_service),
    status_filter: WorkOrderStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> schemas.WorkOrderListResponse:
    """Work orders assigned to the authenticated employee."""
    return service.list_assigned(
        current_user, status=status_filter, page=page, page_size=page_size
    )


@router.get("/my-requests", response_model=schemas.WorkOrderListResponse)
def list_my_requests(
    current_user: User = Depends(require_permissions(rbac.WORKORDER_CREATE_REQUEST)),
    service: WorkOrderService = Depends(get_service),
    status_filter: WorkOrderStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> schemas.WorkOrderListResponse:
    """Work orders the authenticated user raised (their submitted requests)."""
    return service.list_requested(
        current_user, status=status_filter, page=page, page_size=page_size
    )


@router.patch("/{work_order_id}/status", response_model=schemas.WorkOrderRead)
def update_work_order_status(
    work_order_id: uuid.UUID,
    data: schemas.WorkOrderStatusUpdate,
    current_user: User = Depends(get_current_active_user),
    service: WorkOrderService = Depends(get_service),
) -> schemas.WorkOrderRead:
    """Progress an order (assignee or admin): ASSIGNED→IN_PROGRESS→COMPLETED."""
    return schemas.WorkOrderRead.model_validate(
        service.update_status(current_user, work_order_id, data)
    )


@router.patch("/{work_order_id}/assign", response_model=schemas.WorkOrderRead)
def assign_work_order(
    work_order_id: uuid.UUID,
    data: schemas.WorkOrderAssign,
    current_user: User = Depends(require_permissions(rbac.WORKORDER_MANAGE)),
    service: WorkOrderService = Depends(get_service),
) -> schemas.WorkOrderRead:
    """Admin assigns an employee (+ optional due date) → ASSIGNED."""
    return schemas.WorkOrderRead.model_validate(
        service.assign(current_user, work_order_id, data)
    )


@router.patch("/{work_order_id}/close", response_model=schemas.WorkOrderRead)
def close_work_order(
    work_order_id: uuid.UUID,
    current_user: User = Depends(require_permissions(rbac.WORKORDER_MANAGE)),
    service: WorkOrderService = Depends(get_service),
) -> schemas.WorkOrderRead:
    """Admin review: COMPLETED → CLOSED."""
    return schemas.WorkOrderRead.model_validate(service.close(current_user, work_order_id))


@router.patch("/{work_order_id}/cancel", response_model=schemas.WorkOrderRead)
def cancel_work_order(
    work_order_id: uuid.UUID,
    current_user: User = Depends(require_permissions(rbac.WORKORDER_MANAGE)),
    service: WorkOrderService = Depends(get_service),
) -> schemas.WorkOrderRead:
    """Admin cancels an open order."""
    return schemas.WorkOrderRead.model_validate(service.cancel(current_user, work_order_id))


@router.get("/{work_order_id}", response_model=schemas.WorkOrderRead)
def get_work_order(
    work_order_id: uuid.UUID,
    current_user: User = Depends(require_permissions(rbac.WORKORDER_VIEW_ALL)),
    service: WorkOrderService = Depends(get_service),
) -> schemas.WorkOrderRead:
    return schemas.WorkOrderRead.model_validate(service.get(current_user, work_order_id))


@router.put("/{work_order_id}", response_model=schemas.WorkOrderRead)
def update_work_order(
    work_order_id: uuid.UUID,
    data: schemas.WorkOrderUpdate,
    current_user: User = Depends(require_permissions(rbac.WORKORDER_MANAGE)),
    service: WorkOrderService = Depends(get_service),
) -> schemas.WorkOrderRead:
    """Edit a work order (partial update — only provided fields change)."""
    return schemas.WorkOrderRead.model_validate(
        service.update(current_user, work_order_id, data)
    )


@router.delete("/{work_order_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_work_order(
    work_order_id: uuid.UUID,
    current_user: User = Depends(require_permissions(rbac.WORKORDER_MANAGE)),
    service: WorkOrderService = Depends(get_service),
) -> Response:
    service.delete(current_user, work_order_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
