"""Data access for work orders — always scoped to a single organization."""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models.enums import WorkOrderStatus
from app.models.work_order import WorkOrder, WorkOrderEvent


class WorkOrderRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def add(self, work_order: WorkOrder) -> WorkOrder:
        self.db.add(work_order)
        return work_order

    def get(self, *, work_order_id: uuid.UUID, organization_id: uuid.UUID) -> WorkOrder | None:
        stmt = select(WorkOrder).where(
            WorkOrder.id == work_order_id,
            WorkOrder.organization_id == organization_id,  # tenant guard
        )
        return self.db.execute(stmt).scalar_one_or_none()

    def list(
        self,
        *,
        organization_id: uuid.UUID,
        status: WorkOrderStatus | None,
        search: str | None,
        limit: int,
        offset: int,
        assignee_id: uuid.UUID | None = None,
        requested_by_id: uuid.UUID | None = None,
    ) -> tuple[list[WorkOrder], int]:
        filters = [WorkOrder.organization_id == organization_id]
        if assignee_id is not None:
            filters.append(WorkOrder.assignee_id == assignee_id)
        if requested_by_id is not None:
            filters.append(WorkOrder.requested_by_id == requested_by_id)
        if status is not None:
            filters.append(WorkOrder.status == status)
        if search:
            like = f"%{search.strip()}%"
            filters.append(
                or_(
                    WorkOrder.number.ilike(like),
                    WorkOrder.customer_name.ilike(like),
                    WorkOrder.assigned_employee_name.ilike(like),
                    WorkOrder.description.ilike(like),
                )
            )

        total = self.db.execute(
            select(func.count()).select_from(WorkOrder).where(*filters)
        ).scalar_one()

        rows = (
            self.db.execute(
                select(WorkOrder)
                .where(*filters)
                .order_by(WorkOrder.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            .scalars()
            .all()
        )
        return list(rows), int(total)

    def next_number(self, *, organization_id: uuid.UUID) -> str:
        """Generate the next per-org, per-day work-order number, e.g.
        ``WO-20260611-01``. The sequence resets every calendar day."""
        prefix = f"WO-{datetime.now(timezone.utc):%Y%m%d}-"
        numbers = self.db.execute(
            select(WorkOrder.number).where(
                WorkOrder.organization_id == organization_id,
                WorkOrder.number.like(f"{prefix}%"),
            )
        ).scalars().all()

        max_seq = 0
        for number in numbers:
            match = re.search(r"(\d+)$", number or "")
            if match:
                max_seq = max(max_seq, int(match.group(1)))
        return f"{prefix}{max_seq + 1:02d}"

    def add_event(
        self,
        *,
        work_order_id: uuid.UUID,
        actor_id: uuid.UUID | None,
        event_type: str,
        message: str | None = None,
    ) -> None:
        self.db.add(
            WorkOrderEvent(
                work_order_id=work_order_id,
                actor_id=actor_id,
                event_type=event_type,
                message=message,
            )
        )
