"""Employee management API (``/api/v1/employees``) — Organization Admin only."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core import rbac
from app.core.dependencies import require_permissions
from app.db.session import get_db
from app.features.employees import schemas
from app.features.employees.service import EmployeeService
from app.models.user import User

router = APIRouter(prefix="/employees", tags=["Employees"])


def get_service(db: Session = Depends(get_db)) -> EmployeeService:
    return EmployeeService(db)


@router.get("", response_model=list[schemas.EmployeeRead])
def list_employees(
    current_user: User = Depends(require_permissions(rbac.EMPLOYEE_VIEW)),
    service: EmployeeService = Depends(get_service),
    search: str | None = Query(default=None, max_length=255),
    status_filter: str | None = Query(default=None, alias="status", pattern="^(active|inactive)$"),
    include_deleted: bool = Query(default=False),
) -> list[schemas.EmployeeRead]:
    members = service.list(
        current_user, search=search, status=status_filter, include_deleted=include_deleted
    )
    return [schemas.EmployeeRead.model_validate(e) for e in members]


@router.post("", response_model=schemas.EmployeeRead, status_code=status.HTTP_201_CREATED)
def create_employee(
    data: schemas.EmployeeCreate,
    current_user: User = Depends(require_permissions(rbac.EMPLOYEE_MANAGE)),
    service: EmployeeService = Depends(get_service),
) -> schemas.EmployeeRead:
    return schemas.EmployeeRead.model_validate(service.create(current_user, data))


@router.get("/{employee_id}", response_model=schemas.EmployeeRead)
def get_employee(
    employee_id: uuid.UUID,
    current_user: User = Depends(require_permissions(rbac.EMPLOYEE_VIEW)),
    service: EmployeeService = Depends(get_service),
) -> schemas.EmployeeRead:
    return schemas.EmployeeRead.model_validate(service.get(current_user, employee_id))


@router.put("/{employee_id}", response_model=schemas.EmployeeRead)
def update_employee(
    employee_id: uuid.UUID,
    data: schemas.EmployeeUpdate,
    current_user: User = Depends(require_permissions(rbac.EMPLOYEE_MANAGE)),
    service: EmployeeService = Depends(get_service),
) -> schemas.EmployeeRead:
    return schemas.EmployeeRead.model_validate(service.update(current_user, employee_id, data))


@router.patch("/{employee_id}/role", response_model=schemas.EmployeeRead)
def set_employee_role(
    employee_id: uuid.UUID,
    data: schemas.EmployeeRoleUpdate,
    current_user: User = Depends(require_permissions(rbac.EMPLOYEE_MANAGE)),
    service: EmployeeService = Depends(get_service),
) -> schemas.EmployeeRead:
    """Promote an employee to ADMIN or demote an admin to EMPLOYEE.

    Blocks removing the last active admin (409). The change is recorded in the
    audit log.
    """
    return schemas.EmployeeRead.model_validate(
        service.set_role(current_user, employee_id, data.role)
    )


@router.patch("/{employee_id}/activate", response_model=schemas.EmployeeRead)
def activate_employee(
    employee_id: uuid.UUID,
    current_user: User = Depends(require_permissions(rbac.EMPLOYEE_MANAGE)),
    service: EmployeeService = Depends(get_service),
) -> schemas.EmployeeRead:
    """Reactivate an employee."""
    return schemas.EmployeeRead.model_validate(service.activate(current_user, employee_id))


@router.patch("/{employee_id}/deactivate", response_model=schemas.EmployeeRead)
def deactivate_employee(
    employee_id: uuid.UUID,
    current_user: User = Depends(require_permissions(rbac.EMPLOYEE_MANAGE)),
    service: EmployeeService = Depends(get_service),
) -> schemas.EmployeeRead:
    """Deactivate an employee. Blocks deactivating the last active admin (409)."""
    return schemas.EmployeeRead.model_validate(service.deactivate(current_user, employee_id))


@router.delete("/{employee_id}", response_model=schemas.EmployeeRead)
def delete_employee(
    employee_id: uuid.UUID,
    current_user: User = Depends(require_permissions(rbac.EMPLOYEE_MANAGE)),
    service: EmployeeService = Depends(get_service),
) -> schemas.EmployeeRead:
    """Soft-delete an employee. Enforces self / last-admin / active-work-order rules."""
    return schemas.EmployeeRead.model_validate(service.delete(current_user, employee_id))


@router.patch("/{employee_id}/status", response_model=schemas.EmployeeRead)
def set_employee_status(
    employee_id: uuid.UUID,
    data: schemas.EmployeeStatusUpdate,
    current_user: User = Depends(require_permissions(rbac.EMPLOYEE_MANAGE)),
    service: EmployeeService = Depends(get_service),
) -> schemas.EmployeeRead:
    """Activate or deactivate a member (alias of /activate + /deactivate)."""
    return schemas.EmployeeRead.model_validate(
        service.set_active(current_user, employee_id, data.is_active)
    )
