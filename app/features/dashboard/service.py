"""Dashboard aggregation logic — all metrics scoped to the caller's org.

Revenue is the sum of ``amount`` over completed work orders (the Invoice module
will supersede this once invoicing lands). Month-over-month deltas compare the
current calendar month against the previous one.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Numeric, and_, cast, func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.features.dashboard import schemas
from app.models.enums import WorkOrderStatus
from app.models.invoice import Invoice
from app.models.user import User
from app.models.work_order import WorkOrder

_RECENT_LIMIT = 5


def _pct(this: float, last: float) -> float | None:
    if last == 0:
        return None
    return round((this - last) / last * 100, 1)


class DashboardService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def summary(self, user: User) -> schemas.DashboardSummary:
        if user.organization_id is None:
            raise ValidationError("This account is not associated with an organization")
        org_id = user.organization_id

        totals = self._totals(org_id)
        deltas = self._deltas(org_id)
        recent = self._recent(org_id)
        return schemas.DashboardSummary(totals=totals, deltas=deltas, recent_work_orders=recent)

    # ------------------------------------------------------------------ #
    def _totals(self, org_id: uuid.UUID) -> schemas.KpiTotals:
        work_orders = self.db.execute(
            select(func.count()).select_from(WorkOrder).where(WorkOrder.organization_id == org_id)
        ).scalar_one()

        completed = self.db.execute(
            select(func.count())
            .select_from(WorkOrder)
            .where(
                WorkOrder.organization_id == org_id,
                WorkOrder.status == WorkOrderStatus.COMPLETED,
            )
        ).scalar_one()

        invoices = self.db.execute(
            select(func.count()).select_from(Invoice).where(Invoice.organization_id == org_id)
        ).scalar_one()

        revenue = self.db.execute(
            select(func.coalesce(func.sum(WorkOrder.amount), cast(0, Numeric(12, 2)))).where(
                WorkOrder.organization_id == org_id,
                WorkOrder.status == WorkOrderStatus.COMPLETED,
            )
        ).scalar_one()

        return schemas.KpiTotals(
            work_orders=int(work_orders),
            completed_work_orders=int(completed),
            invoices=int(invoices),
            revenue=Decimal(revenue),
        )

    def _deltas(self, org_id: uuid.UUID) -> schemas.KpiDeltas:
        now = datetime.now(timezone.utc)
        cur_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_start = (
            cur_start.replace(year=cur_start.year - 1, month=12)
            if cur_start.month == 1
            else cur_start.replace(month=cur_start.month - 1)
        )

        def count_between(column, start, end, extra=None):
            conds = [WorkOrder.organization_id == org_id, column >= start, column < end]
            if extra is not None:
                conds.append(extra)
            return self.db.execute(
                select(func.count()).select_from(WorkOrder).where(and_(*conds))
            ).scalar_one()

        def revenue_between(start, end):
            return self.db.execute(
                select(func.coalesce(func.sum(WorkOrder.amount), cast(0, Numeric(12, 2)))).where(
                    WorkOrder.organization_id == org_id,
                    WorkOrder.status == WorkOrderStatus.COMPLETED,
                    WorkOrder.completed_at >= start,
                    WorkOrder.completed_at < end,
                )
            ).scalar_one()

        wo_this = count_between(WorkOrder.created_at, cur_start, now)
        wo_last = count_between(WorkOrder.created_at, last_start, cur_start)

        comp = WorkOrder.status == WorkOrderStatus.COMPLETED
        comp_this = count_between(WorkOrder.completed_at, cur_start, now, comp)
        comp_last = count_between(WorkOrder.completed_at, last_start, cur_start, comp)

        rev_this = float(revenue_between(cur_start, now))
        rev_last = float(revenue_between(last_start, cur_start))

        return schemas.KpiDeltas(
            work_orders_pct=_pct(int(wo_this), int(wo_last)),
            completed_pct=_pct(int(comp_this), int(comp_last)),
            invoices_pct=None,  # invoicing not yet implemented
            revenue_pct=_pct(rev_this, rev_last),
        )

    def _recent(self, org_id: uuid.UUID) -> list[schemas.RecentWorkOrder]:
        rows = (
            self.db.execute(
                select(WorkOrder)
                .where(WorkOrder.organization_id == org_id)
                .order_by(WorkOrder.created_at.desc())
                .limit(_RECENT_LIMIT)
            )
            .scalars()
            .all()
        )
        return [schemas.RecentWorkOrder.model_validate(r) for r in rows]
