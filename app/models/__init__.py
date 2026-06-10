"""Aggregate model imports.

Importing this package registers every model on ``Base.metadata``. Alembic's
``env.py`` imports it so autogenerate sees the full schema.
"""
from app.db.base import Base
from app.models.customer import Customer
from app.models.enums import (
    InvoiceStatus,
    SubscriptionStatus,
    UserRole,
    WorkOrderPriority,
    WorkOrderStatus,
)
from app.models.invoice import Invoice, InvoiceItem
from app.models.invoice_record import InvoiceLineItem, InvoiceRecord
from app.models.organization import Organization
from app.models.token import PasswordResetToken, RefreshToken
from app.models.user import User
from app.models.work_order import (
    WorkOrder,
    WorkOrderAttachment,
    WorkOrderEvent,
    WorkOrderNote,
)

__all__ = [
    "Base",
    "Organization",
    "User",
    "RefreshToken",
    "PasswordResetToken",
    "Customer",
    "WorkOrder",
    "WorkOrderNote",
    "WorkOrderAttachment",
    "WorkOrderEvent",
    "Invoice",
    "InvoiceItem",
    "InvoiceRecord",
    "InvoiceLineItem",
    "UserRole",
    "SubscriptionStatus",
    "WorkOrderStatus",
    "WorkOrderPriority",
    "InvoiceStatus",
]
