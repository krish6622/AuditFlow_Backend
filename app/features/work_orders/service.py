"""Business logic for the Work Orders module.

Every method is tenant-scoped: the organization id comes from the authenticated
user, never from client input, so an org can only ever touch its own orders.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import rbac
from app.core.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from app.core.logging import get_logger
from app.features.notifications.repository import NotificationRepository
from app.features.work_orders import schemas
from app.features.work_orders.repository import WorkOrderRepository
from app.models.enums import (
    NotificationType,
    UserRole,
    WorkOrderCategory,
    WorkOrderStatus,
)
from app.models.user import User
from app.models.work_order import WorkOrder, WorkOrderNote

logger = get_logger(__name__)

_MAX_NUMBER_RETRIES = 5

# Forward-only progress transitions allowed through the /status endpoint
# (assignee or admin). Assignment, closing and cancelling have their own paths.
_PROGRESS_NEXT: dict[WorkOrderStatus, set[WorkOrderStatus]] = {
    WorkOrderStatus.ASSIGNED: {WorkOrderStatus.IN_PROGRESS},
    WorkOrderStatus.IN_PROGRESS: {WorkOrderStatus.COMPLETED},
}
# States from which an admin may still cancel an order.
_CANCELLABLE = {
    WorkOrderStatus.AWAITING_ASSIGNMENT,
    WorkOrderStatus.ASSIGNED,
    WorkOrderStatus.IN_PROGRESS,
}


class WorkOrderService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = WorkOrderRepository(db)
        self.notifications = NotificationRepository(db)

    @staticmethod
    def _require_org(user: User) -> uuid.UUID:
        if user.organization_id is None:
            # Super admins have no tenant; the platform role can't own work orders.
            raise ValidationError("This account is not associated with an organization")
        return user.organization_id

    # ------------------------------------------------------------------ #
    # Notification helpers (added to the session; the caller commits)
    # ------------------------------------------------------------------ #
    def _notify_user(
        self,
        *,
        org_id: uuid.UUID,
        user_id: uuid.UUID | None,
        ntype: NotificationType,
        title: str,
        body: str | None,
        work_order_id: uuid.UUID,
    ) -> None:
        if user_id is None:
            return
        self.notifications.add(
            organization_id=org_id,
            user_id=user_id,
            type=ntype,
            title=title,
            body=body,
            work_order_id=work_order_id,
        )

    def _notify_admins(
        self,
        *,
        org_id: uuid.UUID,
        ntype: NotificationType,
        title: str,
        body: str | None,
        work_order_id: uuid.UUID,
        exclude: uuid.UUID | None = None,
    ) -> None:
        for admin_id in self.notifications.active_admin_ids(
            organization_id=org_id, exclude=exclude
        ):
            self.notifications.add(
                organization_id=org_id,
                user_id=admin_id,
                type=ntype,
                title=title,
                body=body,
                work_order_id=work_order_id,
            )

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
        is_admin = rbac.has_permission(user.role, rbac.WORKORDER_MANAGE)

        # Only OTHERS carries a free-text category description.
        category_other = (
            (data.category_other or "").strip() or None
            if data.category == WorkOrderCategory.OTHERS
            else None
        )

        if is_admin:
            # Admins may assign (and set a due date) at creation time.
            assignee_id, assignee_name = self._resolve_assignee(org_id, data.assignee_id)
            display_name = assignee_name or ((data.assigned_employee_name or "").strip() or None)
            due_date = data.due_date
            status = (
                WorkOrderStatus.ASSIGNED
                if assignee_id is not None
                else WorkOrderStatus.AWAITING_ASSIGNMENT
            )
        else:
            # Employee request: never an assignee, due date or chosen status —
            # it always enters the queue awaiting an admin's assignment.
            assignee_id, display_name, due_date = None, None, None
            status = WorkOrderStatus.AWAITING_ASSIGNMENT

        work_order = WorkOrder(
            organization_id=org_id,
            category=data.category,
            category_other=category_other,
            customer_name=data.customer_name.strip(),
            contact_number=data.contact_number.strip(),
            assignee_id=assignee_id,
            assigned_employee_name=display_name,
            requested_by_id=user.id,
            description=data.description.strip(),
            priority=data.urgency,
            order_date=data.order_date or date.today(),
            due_date=due_date,
            notes=(data.notes or "").strip() or None,
            status=status,
            completed_at=None,
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
            message=f"Work order created with status '{status.value}'",
        )

        # Notifications: employee request → admins; admin-assigned-on-create → assignee.
        if not is_admin:
            self._notify_admins(
                org_id=org_id,
                ntype=NotificationType.WORKORDER_REQUESTED,
                title=f"New work request {work_order.number}",
                body=f"{user.full_name} raised a request for {work_order.customer_name}.",
                work_order_id=work_order.id,
                exclude=user.id,
            )
        elif assignee_id is not None:
            self._notify_user(
                org_id=org_id,
                user_id=assignee_id,
                ntype=NotificationType.WORKORDER_ASSIGNED,
                title=f"Work order {work_order.number} assigned to you",
                body=f"{work_order.customer_name}: {work_order.description[:80]}",
                work_order_id=work_order.id,
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
        """Progress an order (ASSIGNED→IN_PROGRESS→COMPLETED). The assignee or an
        admin may do this; the transition must be a valid forward step."""
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
        note = (data.note or "").strip()

        if data.status != previous:
            if data.status not in _PROGRESS_NEXT.get(previous, set()):
                raise ValidationError(
                    f"A {previous.value} order cannot move to {data.status.value}"
                )
            wo.status = data.status
            wo.completed_at = (
                datetime.now(timezone.utc)
                if data.status == WorkOrderStatus.COMPLETED
                else None
            )

        if note:
            self.db.add(WorkOrderNote(work_order_id=wo.id, author_id=user.id, body=note))

        self.db.flush()
        if wo.status != previous:
            self.repo.add_event(
                work_order_id=wo.id,
                actor_id=user.id,
                event_type="status_changed",
                message=f"{previous.value} → {wo.status.value}" + (f": {note}" if note else ""),
            )
            if wo.status == WorkOrderStatus.COMPLETED:
                self._notify_admins(
                    org_id=org_id,
                    ntype=NotificationType.WORKORDER_COMPLETED,
                    title=f"Work order {wo.number} completed",
                    body=f"{wo.assigned_employee_name or 'An employee'} completed "
                    f"{wo.customer_name}'s job — ready for review.",
                    work_order_id=wo.id,
                )
        self.db.commit()
        self.db.refresh(wo)
        return wo

    # ------------------------------------------------------------------ #
    # Admin workflow actions
    # ------------------------------------------------------------------ #
    def assign(
        self, admin: User, work_order_id: uuid.UUID, data: schemas.WorkOrderAssign
    ) -> WorkOrder:
        """Assign an employee (+ optional due date). AWAITING_ASSIGNMENT/ASSIGNED → ASSIGNED."""
        org_id = self._require_org(admin)
        wo = self.repo.get(work_order_id=work_order_id, organization_id=org_id)
        if wo is None:
            raise NotFoundError("Work order not found")
        if wo.status not in (WorkOrderStatus.AWAITING_ASSIGNMENT, WorkOrderStatus.ASSIGNED):
            raise ValidationError(f"A {wo.status.value} order cannot be (re)assigned")

        assignee_id, assignee_name = self._resolve_assignee(org_id, data.assignee_id)
        previous = wo.status
        wo.assignee_id = assignee_id
        wo.assigned_employee_name = assignee_name
        if data.due_date is not None:
            wo.due_date = data.due_date
        wo.status = WorkOrderStatus.ASSIGNED

        self.db.flush()
        self.repo.add_event(
            work_order_id=wo.id,
            actor_id=admin.id,
            event_type="assigned",
            message=f"Assigned to {assignee_name} ({previous.value} → assigned)",
        )
        self._notify_user(
            org_id=org_id,
            user_id=assignee_id,
            ntype=NotificationType.WORKORDER_ASSIGNED,
            title=f"Work order {wo.number} assigned to you",
            body=f"{wo.customer_name}"
            + (f" · due {wo.due_date}" if wo.due_date else ""),
            work_order_id=wo.id,
        )
        self.db.commit()
        self.db.refresh(wo)
        logger.info("Work order %s assigned to %s", wo.number, assignee_id)
        return wo

    def close(self, admin: User, work_order_id: uuid.UUID) -> WorkOrder:
        """Admin review: COMPLETED → CLOSED."""
        org_id = self._require_org(admin)
        wo = self.repo.get(work_order_id=work_order_id, organization_id=org_id)
        if wo is None:
            raise NotFoundError("Work order not found")
        if wo.status != WorkOrderStatus.COMPLETED:
            raise ValidationError("Only completed work orders can be closed")

        wo.status = WorkOrderStatus.CLOSED
        self.db.flush()
        self.repo.add_event(
            work_order_id=wo.id, actor_id=admin.id, event_type="closed",
            message="completed → closed",
        )
        self._notify_user(
            org_id=org_id,
            user_id=wo.requested_by_id,
            ntype=NotificationType.WORKORDER_CLOSED,
            title=f"Work order {wo.number} closed",
            body=f"Your request for {wo.customer_name} has been reviewed and closed.",
            work_order_id=wo.id,
        )
        self.db.commit()
        self.db.refresh(wo)
        return wo

    def cancel(self, admin: User, work_order_id: uuid.UUID) -> WorkOrder:
        """Admin cancels an open order."""
        org_id = self._require_org(admin)
        wo = self.repo.get(work_order_id=work_order_id, organization_id=org_id)
        if wo is None:
            raise NotFoundError("Work order not found")
        if wo.status not in _CANCELLABLE:
            raise ValidationError(f"A {wo.status.value} order cannot be cancelled")

        previous = wo.status
        wo.status = WorkOrderStatus.CANCELLED
        self.db.flush()
        self.repo.add_event(
            work_order_id=wo.id, actor_id=admin.id, event_type="cancelled",
            message=f"{previous.value} → cancelled",
        )
        self.db.commit()
        self.db.refresh(wo)
        return wo

    def list_requested(
        self,
        user: User,
        *,
        status: WorkOrderStatus | None,
        page: int,
        page_size: int,
    ) -> schemas.WorkOrderListResponse:
        """Work orders the calling employee raised (their submitted requests)."""
        org_id = self._require_org(user)
        page = max(page, 1)
        page_size = min(max(page_size, 1), 100)
        items, total = self.repo.list(
            organization_id=org_id,
            status=status,
            search=None,
            limit=page_size,
            offset=(page - 1) * page_size,
            requested_by_id=user.id,
        )
        return schemas.WorkOrderListResponse(
            items=[schemas.WorkOrderRead.model_validate(i) for i in items],
            total=total,
            page=page,
            page_size=page_size,
        )

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

        if "category" in fields and fields["category"] is not None:
            wo.category = fields["category"]
        if "category_other" in fields:
            wo.category_other = (fields["category_other"] or "").strip() or None
        # Keep the invariant: a free-text description only exists for OTHERS.
        if wo.category is not None and wo.category != WorkOrderCategory.OTHERS:
            wo.category_other = None
        elif wo.category == WorkOrderCategory.OTHERS and not (wo.category_other or "").strip():
            raise ValidationError("Please describe the category when 'Others' is selected")
        if "contact_number" in fields:
            value = (fields["contact_number"] or "").strip()
            if not value:
                raise ValidationError("Contact number is required.")
            wo.contact_number = value
        if "urgency" in fields and fields["urgency"] is not None:
            wo.priority = fields["urgency"]
        if "order_date" in fields and fields["order_date"] is not None:
            wo.order_date = fields["order_date"]
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
        if "due_date" in fields:
            wo.due_date = fields["due_date"]
        if "notes" in fields:
            value = (fields["notes"] or "").strip()
            wo.notes = value or None
        # Status is NOT changed here — transitions go through assign / status /
        # close / cancel so the workflow rules are always enforced.

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
