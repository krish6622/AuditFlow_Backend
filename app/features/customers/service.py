"""Customer master business logic.

Customers are the single source of truth a work order or invoice is raised
against. Admins manage them; employees only read (enforced at the route via
RBAC). Every mutating action is recorded in the shared audit trail with a
snapshot of the client name so the log stays readable after a hard delete.
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.features.audit.repository import AuditRepository
from app.features.customers import schemas
from app.features.customers.repository import CustomerRepository
from app.models.audit_log import AuditLog
from app.models.customer import Customer
from app.models.enums import AuditAction, CustomerType
from app.models.user import User

logger = get_logger(__name__)

# Customer cannot be deleted while referenced by work orders / invoices (the FKs
# are ON DELETE RESTRICT). Deactivate instead to keep the history intact.
HAS_WORK_ORDERS_MESSAGE = (
    "This customer has work orders. Deactivate the customer instead of deleting it."
)
HAS_INVOICES_MESSAGE = (
    "This customer has invoices. Deactivate the customer instead of deleting it."
)

# Master-data text fields a duplicate import may fill in when missing.
_FILLABLE_FIELDS = (
    "business_name",
    "proprietor_name",
    "mobile_number",
    "alternate_mobile_number",
    "email",
    "date_of_birth",
    "gst_number",
    "pan_number",
    "aadhaar_number",
    "address_line_1",
    "address_line_2",
    "city",
    "state",
    "pincode",
    "remarks",
)


class CustomerService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = CustomerRepository(db)
        self.audit = AuditRepository(db)

    @staticmethod
    def _org(actor: User) -> uuid.UUID:
        if actor.organization_id is None:
            raise ValidationError("This account is not associated with an organization")
        return actor.organization_id

    # ---- Reads ----

    def list(
        self,
        actor: User,
        *,
        search: str | None = None,
        customer_type: CustomerType | None = None,
        status: str | None = None,
        city: str | None = None,
    ) -> list[Customer]:
        return self.repo.list(
            organization_id=self._org(actor),
            search=search,
            customer_type=customer_type,
            status=status,
            city=city,
        )

    def get(self, actor: User, customer_id: uuid.UUID) -> Customer:
        customer = self.repo.get(organization_id=self._org(actor), customer_id=customer_id)
        if customer is None:
            raise NotFoundError("Customer not found")
        return customer

    def stats(self, actor: User) -> schemas.CustomerStats:
        return schemas.CustomerStats(**self.repo.stats(organization_id=self._org(actor)))

    def cities(self, actor: User) -> list[str]:
        return self.repo.distinct_cities(organization_id=self._org(actor))

    def audit_trail(self, actor: User, customer_id: uuid.UUID) -> list[AuditLog]:
        # Ensures the customer exists and belongs to the caller's org (404 else).
        self.get(actor, customer_id)
        return self.audit.list_for_customer(
            organization_id=self._org(actor), customer_id=customer_id
        )

    def work_orders(self, actor: User, customer_id: uuid.UUID):
        self.get(actor, customer_id)  # 404 / cross-tenant guard
        return self.repo.work_orders_for(customer_id=customer_id)

    def invoices(self, actor: User, customer_id: uuid.UUID):
        self.get(actor, customer_id)  # 404 / cross-tenant guard
        return self.repo.invoices_for(customer_id=customer_id)

    # ---- Writes ----

    def _generate_code(self, organization_id: uuid.UUID) -> str:
        seq = self.repo.next_code_sequence(organization_id=organization_id)
        return f"CUS-{seq:04d}"

    def create(self, admin: User, data: schemas.CustomerCreate) -> Customer:
        org_id = self._org(admin)
        customer = Customer(
            organization_id=org_id,
            customer_code=self._generate_code(org_id),
            created_by=admin.id,
            **_normalize(data.model_dump(exclude={"is_active"})),
            is_active=data.is_active,
        )
        self.repo.add(customer)
        self.db.flush()  # assign id for the audit row
        self.audit.record(
            organization_id=org_id,
            performed_by_user_id=admin.id,
            action=AuditAction.CUSTOMER_CREATED,
            customer_id=customer.id,
            entity_name=customer.client_name,
        )
        self.db.commit()
        self.db.refresh(customer)
        logger.info("Customer %s (%s) created in org %s", customer.customer_code, customer.client_name, org_id)
        return customer

    def update(
        self, admin: User, customer_id: uuid.UUID, data: schemas.CustomerUpdate
    ) -> Customer:
        org_id = self._org(admin)
        customer = self.get(admin, customer_id)

        fields = _normalize(data.model_dump(exclude_unset=True, exclude={"is_active"}))
        for field, value in fields.items():
            setattr(customer, field, value)
        if data.is_active is not None:
            customer.is_active = data.is_active

        self.audit.record(
            organization_id=org_id,
            performed_by_user_id=admin.id,
            action=AuditAction.CUSTOMER_UPDATED,
            customer_id=customer.id,
            entity_name=customer.client_name,
        )
        self.db.commit()
        self.db.refresh(customer)
        logger.info("Customer %s updated (by %s)", customer.customer_code, admin.id)
        return customer

    def set_active(self, admin: User, customer_id: uuid.UUID, is_active: bool) -> Customer:
        org_id = self._org(admin)
        customer = self.get(admin, customer_id)

        if customer.is_active == is_active:
            return customer  # no-op — nothing to change or audit

        customer.is_active = is_active
        self.audit.record(
            organization_id=org_id,
            performed_by_user_id=admin.id,
            action=AuditAction.CUSTOMER_ACTIVATED if is_active else AuditAction.CUSTOMER_DEACTIVATED,
            customer_id=customer.id,
            entity_name=customer.client_name,
        )
        self.db.commit()
        self.db.refresh(customer)
        logger.info("Customer %s active=%s (by %s)", customer.customer_code, is_active, admin.id)
        return customer

    def activate(self, admin: User, customer_id: uuid.UUID) -> Customer:
        return self.set_active(admin, customer_id, True)

    def deactivate(self, admin: User, customer_id: uuid.UUID) -> Customer:
        return self.set_active(admin, customer_id, False)

    def delete(self, admin: User, customer_id: uuid.UUID) -> None:
        """Hard-delete a customer. Blocked while referenced by work orders or
        invoices (those FKs are RESTRICT) — deactivate instead to keep history."""
        org_id = self._org(admin)
        customer = self.get(admin, customer_id)

        if self.repo.has_work_orders(customer_id=customer.id):
            raise ConflictError(HAS_WORK_ORDERS_MESSAGE)
        if self.repo.has_invoices(customer_id=customer.id):
            raise ConflictError(HAS_INVOICES_MESSAGE)

        name = customer.client_name
        # Record first; the customer FK is SET NULL on delete, entity_name keeps
        # the trail readable.
        self.audit.record(
            organization_id=org_id,
            performed_by_user_id=admin.id,
            action=AuditAction.CUSTOMER_DELETED,
            customer_id=customer.id,
            entity_name=name,
        )
        self.db.flush()
        self.repo.delete(customer)
        self.db.commit()
        logger.info("Customer %s (%s) deleted (by %s)", customer_id, name, admin.id)


def _normalize(data: dict) -> dict:
    """Trim strings and coerce blanks to NULL so the master stays clean."""
    cleaned: dict = {}
    for key, value in data.items():
        # ``type(value) is str`` (not isinstance) so enum members like
        # CustomerType — which subclass str — pass through untouched.
        if type(value) is str:
            value = value.strip() or None
            if value and key == "email":
                value = value.lower()
        cleaned[key] = value
    return cleaned
