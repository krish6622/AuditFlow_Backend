"""Response models for the dashboard summary."""
from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, ConfigDict

from app.models.enums import WorkOrderStatus


class KpiTotals(BaseModel):
    work_orders: int
    completed_work_orders: int
    invoices: int
    awaiting_assignment: int


class KpiDeltas(BaseModel):
    """Month-over-month change, in percent. ``None`` when last month had none."""

    work_orders_pct: float | None
    completed_pct: float | None
    invoices_pct: float | None


class RecentWorkOrder(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    number: str
    customer_name: str | None
    assigned_employee_name: str | None
    status: WorkOrderStatus
    due_date: date | None


class DashboardSummary(BaseModel):
    totals: KpiTotals
    deltas: KpiDeltas
    recent_work_orders: list[RecentWorkOrder]
    awaiting_assignment: list[RecentWorkOrder]
