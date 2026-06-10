"""Business logic for the Work Orders module.

Every method is tenant-scoped: the organization id comes from the authenticated
user, never from client input, so an org can only ever touch its own orders.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import rbac
from app.core.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from app.core.logging import get_logger
from app.features.work_orders import schemas
from app.features.work_orders.repository import WorkOrderRepository
from app.models.enums import UserRole, WorkOrderStatus
from app.models.user import User
from app.models.work_order import WorkOrder, WorkOrderNote

logger = get_logger(__name__)

_MAX_NUMBER_RETRIES = 5


class WorkOrderService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = WorkOrderRepository(db)

    @staticmethod
    def _require_org(user: User) -> uuid.UUID:
        if user.organization_id is None:
            # Super admins have no tenant; the platform role can't own work orders.
            raise ValidationError("This account is not associated with an organization")
        return user.organization_id

    def _resolve_assignee(
        self, org_id: uuid.UUID, assignee_id: uuid.UUID | None
    ) -> tuple[uuid.UUID | None, str | None]:
        """Validate an assignee is an employee in this org; return (id, name)."""
        if assignee_id is None:
            return None, None
        emp = self.db.execute(
            select(User).where(
                User.id == assignee_id,
                User.organization_id == org_id,
                User.role == UserRole.EMPLOYEE,
            )
        ).scalar_one_or_none()
        if emp is None:
            raise ValidationError("Assigned employee not found in your organization")
        return emp.id, emp.full_name

    # ------------------------------------------------------------------ #
    # Create
    # ------------------------------------------------------------------ #
    def create(self, user: User, data: schemas.WorkOrderCreate) -> WorkOrder:
        org_id = self._require_org(user)

        assignee_id, assignee_name = self._resolve_assignee(org_id, data.assignee_id)
        # An explicit employee assignment wins over any free-text name.
        display_name = assignee_name or ((data.assigned_employee_name or "").strip() or None)

        work_order = WorkOrder(
            organization_id=org_id,
            customer_name=data.customer_name.strip(),
            assignee_id=assignee_id,
            assigned_employee_name=display_name,
            description=data.description.strip(),
            amount=data.amount,
            due_date=data.due_date,
            notes=(data.notes or "").strip() or None,
            status=data.status,
            completed_at=(
                datetime.now(timezone.utc)
                if data.status == WorkOrderStatus.COMPLETED
                else None
            ),
        )

        # Retry on the rare race where two orders grab the same generated number.
        for attempt in range(_MAX_NUMBER_RETRIES):
            work_order.number = self.repo.next_number(organization_id=org_id)
            self.repo.add(work_order)
            try:
                self.db.flush()
                break
            except IntegrityError:
                self.db.rollback()
                self.db.add(work_order)
                if attempt == _MAX_NUMBER_RETRIES - 1:
                    raise
        else:  # pragma: no cover - defensive
            raise ValidationError("Could not allocate a work order number")

        self.repo.add_event(
            work_order_id=work_order.id,
            actor_id=user.id,
            event_type="created",
            message=f"Work order created with status '{data.status.value}'",
        )
        self.db.commit()
        self.db.refresh(work_order)
        logger.info("Work order %s created in org %s", work_order.number, org_id)
        return work_order

    # ------------------------------------------------------------------ #
    # Read
    # ------------------------------------------------------------------ #
    def get(self, user: User, work_order_id: uuid.UUID) -> WorkOrder:
        org_id = self._require_org(user)
        wo = self.repo.get(work_order_id=work_order_id, organization_id=org_id)
        if wo is None:
            raise NotFoundError("Work order not found")
        return wo

    def list(
        self,
        user: User,
        *,
        status: WorkOrderStatus | None,
        search: str | None,
        page: int,
        page_size: int,
    ) -> schemas.WorkOrderListResponse:
        org_id = self._require_org(user)
        page = max(page, 1)
        page_size = min(max(page_size, 1), 100)
        items, total = self.repo.list(
            organization_id=org_id,
            status=status,
            search=search,
            limit=page_size,
            offset=(page - 1) * page_size,
        )
        return schemas.WorkOrderListResponse(
            items=[schemas.WorkOrderRead.model_validate(i) for i in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    def list_assigned(
        self,
        user: User,
        *,
        status: WorkOrderStatus | None,
        page: int,
        page_size: int,
    ) -> schemas.WorkOrderListResponse:
        """Work orders assigned to the calling employee."""
        org_id = self._require_org(user)
        page = max(page, 1)
        page_size = min(max(page_size, 1), 100)
        items, total = self.repo.list(
            organization_id=org_id,
            status=status,
            search=None,
            limit=page_size,
            offset=(page - 1) * page_size,
            assignee_id=user.id,
        )
        return schemas.WorkOrderListResponse(
            items=[schemas.WorkOrderRead.model_validate(i) for i in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    def update_status(
        self, user: User, work_order_id: uuid.UUID, data: schemas.WorkOrderStatusUpdate
    ) -> WorkOrder:
        """Change status (+ optional note). Admins may update any order; an
        employee may update only orders assigned to them."""
        org_id = self._require_org(user)
        wo = self.repo.get(work_order_id=work_order_id, organization_id=org_id)
        if wo is None:
            raise NotFoundError("Work order not found")

        can_manage = rbac.has_permission(user.role, rbac.WORKORDER_MANAGE)
        owns_it = (
            rbac.has_permission(user.role, rbac.WORKORDER_UPDATE_STATUS)
            and wo.assignee_id == user.id
        )
        if not (can_manage or owns_it):
            raise PermissionDeniedError("You can only update work orders assigned to you")

        previous = wo.status
        if data.status != previous:
            wo.status = data.status
            wo.completed_at = (
                datetime.now(timezone.utc)
                if data.status == WorkOrderStatus.COMPLETED
                else None
            )

        note = (data.note or "").strip()
        if note:
            self.db.add(WorkOrderNote(work_order_id=wo.id, author_id=user.id, body=note))

        self.db.flush()
        if data.status != previous:
            self.repo.add_event(
                work_order_id=wo.id,
                actor_id=user.id,
                event_type="status_changed",
                message=f"{previous.value} → {data.status.value}"
                + (f": {note}" if note else ""),
            )
        self.db.commit()
        self.db.refresh(wo)
        return wo

    # ------------------------------------------------------------------ #
    # Update
    # ------------------------------------------------------------------ #
    def update(
        self, user: User, work_order_id: uuid.UUID, data: schemas.WorkOrderUpdate
    ) -> WorkOrder:
        org_id = self._require_org(user)
        wo = self.repo.get(work_order_id=work_order_id, organization_id=org_id)
        if wo is None:
            raise NotFoundError("Work order not found")

        fields = data.model_dump(exclude_unset=True)
        previous_status = wo.status

        if "customer_name" in fields and fields["customer_name"]:
            wo.customer_name = fields["customer_name"].strip()
        if "description" in fields and fields["description"]:
            wo.description = fields["description"].strip()
        if "assigned_employee_name" in fields:
            value = (fields["assigned_employee_name"] or "").strip()
            wo.assigned_employee_name = value or None
        if "assignee_id" in fields:
            aid, aname = self._resolve_assignee(org_id, fields["assignee_id"])
            wo.assignee_id = aid
            if aid is not None:
                wo.assigned_employee_name = aname
            elif "assigned_employee_name" not in fields:
                wo.assigned_employee_name = None
        if "amount" in fields and fields["amount"] is not None:
            wo.amount = fields["amount"]
        if "due_date" in fields:
            wo.due_date = fields["due_date"]
        if "notes" in fields:
            value = (fields["notes"] or "").strip()
            wo.notes = value or None
        if "status" in fields and fields["status"] is not None:
            new_status: WorkOrderStatus = fields["status"]
            if new_status != previous_status:
                wo.status = new_status
                wo.completed_at = (
                    datetime.now(timezone.utc)
                    if new_status == WorkOrderStatus.COMPLETED
                    else None
                )

        self.db.flush()

        if wo.status != previous_status:
            self.repo.add_event(
                work_order_id=wo.id,
                actor_id=user.id,
                event_type="status_changed",
                message=f"{previous_status.value} → {wo.status.value}",
            )

        self.db.commit()
        self.db.refresh(wo)
        return wo

    # ------------------------------------------------------------------ #
    # Delete
    # ------------------------------------------------------------------ #
    def delete(self, user: User, work_order_id: uuid.UUID) -> None:
        org_id = self._require_org(user)
        wo = self.repo.get(work_order_id=work_order_id, organization_id=org_id)
        if wo is None:
            raise NotFoundError("Work order not found")
        self.db.delete(wo)
        self.db.commit()
