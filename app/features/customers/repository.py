"""Data access for the customer master, org-scoped.

Every query is filtered by ``organization_id`` so a customer can never leak
across tenants. The service owns the transaction; this layer only reads and
stages writes.
"""
from __future__ import annotations

import uuid

from sqlalchemy import Integer, cast, func, or_, select
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.enums import CustomerType
from app.models.invoice import Invoice
from app.models.work_order import WorkOrder

# Numeric suffix of a "CUS-0001" code, for computing the next sequence per org.
_CODE_SUFFIX = cast(func.regexp_replace(Customer.customer_code, r"\D", "", "g"), Integer)


class CustomerRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list(
        self,
        *,
        organization_id: uuid.UUID,
        search: str | None = None,
        customer_type: CustomerType | None = None,
        status: str | None = None,  # "active" | "inactive"
        city: str | None = None,
    ) -> list[Customer]:
        filters = [Customer.organization_id == organization_id]
        if customer_type is not None:
            filters.append(Customer.customer_type == customer_type)
        if status == "active":
            filters.append(Customer.is_active.is_(True))
        elif status == "inactive":
            filters.append(Customer.is_active.is_(False))
        if city:
            filters.append(Customer.city == city)
        if search:
            like = f"%{search.strip()}%"
            filters.append(
                or_(
                    Customer.client_name.ilike(like),
                    Customer.business_name.ilike(like),
                    Customer.customer_code.ilike(like),
                    Customer.mobile_number.ilike(like),
                    Customer.gst_number.ilike(like),
                    Customer.pan_number.ilike(like),
                )
            )
        rows = (
            self.db.execute(
                select(Customer).where(*filters).order_by(Customer.customer_code.asc())
            )
            .scalars()
            .all()
        )
        return list(rows)

    def get(
        self, *, organization_id: uuid.UUID, customer_id: uuid.UUID
    ) -> Customer | None:
        return self.db.execute(
            select(Customer).where(
                Customer.id == customer_id,
                Customer.organization_id == organization_id,
            )
        ).scalar_one_or_none()

    def stats(self, *, organization_id: uuid.UUID) -> dict[str, int]:
        rows = self.db.execute(
            select(Customer.customer_type, Customer.is_active).where(
                Customer.organization_id == organization_id
            )
        ).all()
        total = len(rows)
        gst = sum(1 for t, _ in rows if t == CustomerType.GST)
        income_tax = sum(1 for t, _ in rows if t == CustomerType.INCOME_TAX)
        active = sum(1 for _, a in rows if a)
        return {
            "total": total,
            "gst": gst,
            "income_tax": income_tax,
            "active": active,
            "inactive": total - active,
        }

    def distinct_cities(self, *, organization_id: uuid.UUID) -> list[str]:
        rows = self.db.execute(
            select(Customer.city)
            .where(
                Customer.organization_id == organization_id,
                Customer.city.is_not(None),
                Customer.city != "",
            )
            .distinct()
            .order_by(Customer.city.asc())
        ).scalars().all()
        return list(rows)

    def next_code_sequence(self, *, organization_id: uuid.UUID) -> int:
        """Next ``CUS-XXXX`` sequence number for the organization (max + 1)."""
        current_max = self.db.execute(
            select(func.coalesce(func.max(_CODE_SUFFIX), 0)).where(
                Customer.organization_id == organization_id
            )
        ).scalar_one()
        return int(current_max or 0) + 1

    def find_duplicate(
        self,
        *,
        organization_id: uuid.UUID,
        gst_number: str | None = None,
        pan_number: str | None = None,
        mobile_number: str | None = None,
        email: str | None = None,
    ) -> Customer | None:
        """Locate an existing customer by the dedup priority: GST > PAN > Mobile
        > Email. Returns the first match found, in that order."""
        for column, value in (
            (Customer.gst_number, gst_number),
            (Customer.pan_number, pan_number),
            (Customer.mobile_number, mobile_number),
            (Customer.email, email),
        ):
            if not value:
                continue
            match = self.db.execute(
                select(Customer).where(
                    Customer.organization_id == organization_id,
                    func.lower(column) == value.strip().lower(),
                )
            ).scalars().first()
            if match is not None:
                return match
        return None

    def work_orders_for(self, *, customer_id: uuid.UUID) -> list[WorkOrder]:
        rows = (
            self.db.execute(
                select(WorkOrder)
                .where(WorkOrder.customer_id == customer_id)
                .order_by(WorkOrder.created_at.desc())
            )
            .scalars()
            .all()
        )
        return list(rows)

    def invoices_for(self, *, customer_id: uuid.UUID) -> list[Invoice]:
        rows = (
            self.db.execute(
                select(Invoice)
                .where(Invoice.customer_id == customer_id)
                .order_by(Invoice.created_at.desc())
            )
            .scalars()
            .all()
        )
        return list(rows)

    def has_work_orders(self, *, customer_id: uuid.UUID) -> bool:
        return (
            self.db.execute(
                select(func.count())
                .select_from(WorkOrder)
                .where(WorkOrder.customer_id == customer_id)
            ).scalar_one()
            > 0
        )

    def has_invoices(self, *, customer_id: uuid.UUID) -> bool:
        return (
            self.db.execute(
                select(func.count())
                .select_from(Invoice)
                .where(Invoice.customer_id == customer_id)
            ).scalar_one()
            > 0
        )

    def add(self, customer: Customer) -> Customer:
        self.db.add(customer)
        return customer

    def delete(self, customer: Customer) -> None:
        self.db.delete(customer)
