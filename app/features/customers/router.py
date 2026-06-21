"""Customer management API (``/api/v1/customers``).

Reads require ``customer:view`` (admins and — for lookup during work-order
creation — employees). All mutations require ``customer:manage`` (admin only).
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core import rbac
from app.core.dependencies import require_permissions
from app.db.session import get_db
from app.features.customers import schemas
from app.features.customers.service import CustomerService
from app.models.enums import CustomerType
from app.models.user import User

router = APIRouter(prefix="/customers", tags=["Customers"])


def get_service(db: Session = Depends(get_db)) -> CustomerService:
    return CustomerService(db)


@router.get("", response_model=list[schemas.CustomerRead])
def list_customers(
    current_user: User = Depends(require_permissions(rbac.CUSTOMER_VIEW)),
    service: CustomerService = Depends(get_service),
    search: str | None = Query(default=None, max_length=255),
    customer_type: CustomerType | None = Query(default=None),
    status_filter: str | None = Query(
        default=None, alias="status", pattern="^(active|inactive)$"
    ),
    city: str | None = Query(default=None, max_length=120),
) -> list[schemas.CustomerRead]:
    customers = service.list(
        current_user,
        search=search,
        customer_type=customer_type,
        status=status_filter,
        city=city,
    )
    return [schemas.CustomerRead.model_validate(c) for c in customers]


@router.get("/stats", response_model=schemas.CustomerStats)
def customer_stats(
    current_user: User = Depends(require_permissions(rbac.CUSTOMER_VIEW)),
    service: CustomerService = Depends(get_service),
) -> schemas.CustomerStats:
    return service.stats(current_user)


@router.get("/cities", response_model=list[str])
def customer_cities(
    current_user: User = Depends(require_permissions(rbac.CUSTOMER_VIEW)),
    service: CustomerService = Depends(get_service),
) -> list[str]:
    """Distinct cities present in the master — powers the city filter dropdown."""
    return service.cities(current_user)


@router.get("/lookup", response_model=list[schemas.CustomerLookupItem])
def lookup_customers(
    current_user: User = Depends(require_permissions(rbac.CUSTOMER_VIEW)),
    service: CustomerService = Depends(get_service),
    search: str | None = Query(default=None, max_length=255),
) -> list[schemas.CustomerLookupItem]:
    """Active-customer picker for work-order / invoice creation. Searches by
    client name, mobile, GST, or PAN; returns the fields needed to auto-populate."""
    customers = service.list(current_user, search=search, status="active")
    return [schemas.CustomerLookupItem.model_validate(c) for c in customers]


@router.post("", response_model=schemas.CustomerRead, status_code=status.HTTP_201_CREATED)
def create_customer(
    data: schemas.CustomerCreate,
    current_user: User = Depends(require_permissions(rbac.CUSTOMER_MANAGE)),
    service: CustomerService = Depends(get_service),
) -> schemas.CustomerRead:
    return schemas.CustomerRead.model_validate(service.create(current_user, data))


@router.get("/{customer_id}", response_model=schemas.CustomerRead)
def get_customer(
    customer_id: uuid.UUID,
    current_user: User = Depends(require_permissions(rbac.CUSTOMER_VIEW)),
    service: CustomerService = Depends(get_service),
) -> schemas.CustomerRead:
    return schemas.CustomerRead.model_validate(service.get(current_user, customer_id))


@router.get("/{customer_id}/audit-logs", response_model=list[schemas.CustomerAuditEntry])
def customer_audit_logs(
    customer_id: uuid.UUID,
    current_user: User = Depends(require_permissions(rbac.CUSTOMER_VIEW)),
    service: CustomerService = Depends(get_service),
) -> list[schemas.CustomerAuditEntry]:
    """The audit history for one customer (create / update / status / delete)."""
    entries = service.audit_trail(current_user, customer_id)
    return [
        schemas.CustomerAuditEntry(
            id=e.id,
            action=e.action.value,
            performed_by_name=e.performed_by.full_name if e.performed_by else None,
            customer_name=e.entity_name,
            timestamp=e.created_at,
        )
        for e in entries
    ]


@router.get(
    "/{customer_id}/work-orders", response_model=list[schemas.CustomerWorkOrderItem]
)
def customer_work_orders(
    customer_id: uuid.UUID,
    current_user: User = Depends(require_permissions(rbac.CUSTOMER_VIEW)),
    service: CustomerService = Depends(get_service),
) -> list[schemas.CustomerWorkOrderItem]:
    """Work-order history for one customer (newest first)."""
    return [
        schemas.CustomerWorkOrderItem(
            id=wo.id,
            number=wo.number,
            title=wo.title,
            status=wo.status.value,
            order_date=wo.order_date,
            created_at=wo.created_at,
        )
        for wo in service.work_orders(current_user, customer_id)
    ]


@router.get("/{customer_id}/invoices", response_model=list[schemas.CustomerInvoiceItem])
def customer_invoices(
    customer_id: uuid.UUID,
    current_user: User = Depends(require_permissions(rbac.CUSTOMER_VIEW)),
    service: CustomerService = Depends(get_service),
) -> list[schemas.CustomerInvoiceItem]:
    """Invoice history for one customer (newest first)."""
    return [
        schemas.CustomerInvoiceItem(
            id=inv.id,
            number=inv.number,
            status=inv.status.value,
            total=inv.total,
            issue_date=inv.issue_date,
            created_at=inv.created_at,
        )
        for inv in service.invoices(current_user, customer_id)
    ]


@router.put("/{customer_id}", response_model=schemas.CustomerRead)
def update_customer(
    customer_id: uuid.UUID,
    data: schemas.CustomerUpdate,
    current_user: User = Depends(require_permissions(rbac.CUSTOMER_MANAGE)),
    service: CustomerService = Depends(get_service),
) -> schemas.CustomerRead:
    return schemas.CustomerRead.model_validate(
        service.update(current_user, customer_id, data)
    )


@router.patch("/{customer_id}/activate", response_model=schemas.CustomerRead)
def activate_customer(
    customer_id: uuid.UUID,
    current_user: User = Depends(require_permissions(rbac.CUSTOMER_MANAGE)),
    service: CustomerService = Depends(get_service),
) -> schemas.CustomerRead:
    return schemas.CustomerRead.model_validate(service.activate(current_user, customer_id))


@router.patch("/{customer_id}/deactivate", response_model=schemas.CustomerRead)
def deactivate_customer(
    customer_id: uuid.UUID,
    current_user: User = Depends(require_permissions(rbac.CUSTOMER_MANAGE)),
    service: CustomerService = Depends(get_service),
) -> schemas.CustomerRead:
    return schemas.CustomerRead.model_validate(service.deactivate(current_user, customer_id))


@router.patch("/{customer_id}/status", response_model=schemas.CustomerRead)
def set_customer_status(
    customer_id: uuid.UUID,
    data: schemas.CustomerStatusUpdate,
    current_user: User = Depends(require_permissions(rbac.CUSTOMER_MANAGE)),
    service: CustomerService = Depends(get_service),
) -> schemas.CustomerRead:
    return schemas.CustomerRead.model_validate(
        service.set_active(current_user, customer_id, data.is_active)
    )


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_customer(
    customer_id: uuid.UUID,
    current_user: User = Depends(require_permissions(rbac.CUSTOMER_MANAGE)),
    service: CustomerService = Depends(get_service),
) -> Response:
    """Hard-delete a customer (admin only). Blocked if referenced by work orders
    or invoices."""
    service.delete(current_user, customer_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
