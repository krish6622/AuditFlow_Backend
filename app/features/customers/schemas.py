"""Pydantic models for customer management (the client master).

``customer_code`` is server-assigned (CUS-0001) and immutable, so it never
appears on create/update. ``status`` is a read-only projection of ``is_active``
(ACTIVE / INACTIVE) — activation flows through the dedicated status endpoints.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, computed_field

from app.models.enums import CustomerType


class CustomerBase(BaseModel):
    customer_type: CustomerType
    client_name: str = Field(min_length=1, max_length=255)
    business_name: str | None = Field(default=None, max_length=255)
    proprietor_name: str | None = Field(default=None, max_length=255)
    mobile_number: str | None = Field(default=None, max_length=40)
    alternate_mobile_number: str | None = Field(default=None, max_length=40)
    email: EmailStr | None = None
    date_of_birth: date | None = None
    gst_number: str | None = Field(default=None, max_length=20)
    pan_number: str | None = Field(default=None, max_length=20)
    aadhaar_number: str | None = Field(default=None, max_length=20)
    address_line_1: str | None = None
    address_line_2: str | None = None
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    pincode: str | None = Field(default=None, max_length=12)
    remarks: str | None = None


class CustomerCreate(CustomerBase):
    is_active: bool = True


class CustomerUpdate(BaseModel):
    """All fields optional; ``customer_code`` is immutable and not editable."""

    customer_type: CustomerType | None = None
    client_name: str | None = Field(default=None, min_length=1, max_length=255)
    business_name: str | None = Field(default=None, max_length=255)
    proprietor_name: str | None = Field(default=None, max_length=255)
    mobile_number: str | None = Field(default=None, max_length=40)
    alternate_mobile_number: str | None = Field(default=None, max_length=40)
    email: EmailStr | None = None
    date_of_birth: date | None = None
    gst_number: str | None = Field(default=None, max_length=20)
    pan_number: str | None = Field(default=None, max_length=20)
    aadhaar_number: str | None = Field(default=None, max_length=20)
    address_line_1: str | None = None
    address_line_2: str | None = None
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    pincode: str | None = Field(default=None, max_length=12)
    remarks: str | None = None
    is_active: bool | None = None


class CustomerStatusUpdate(BaseModel):
    is_active: bool


class CustomerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_code: str
    customer_type: CustomerType
    client_name: str
    business_name: str | None
    proprietor_name: str | None
    mobile_number: str | None
    alternate_mobile_number: str | None
    email: str | None
    date_of_birth: date | None
    gst_number: str | None
    pan_number: str | None
    aadhaar_number: str | None
    address_line_1: str | None
    address_line_2: str | None
    city: str | None
    state: str | None
    pincode: str | None
    remarks: str | None
    is_active: bool
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def status(self) -> str:
        return "ACTIVE" if self.is_active else "INACTIVE"


class CustomerStats(BaseModel):
    """Dashboard cards for the customer screen."""

    total: int
    gst: int
    income_tax: int
    active: int
    inactive: int


class CustomerLookupItem(BaseModel):
    """Slim projection for the work-order / invoice customer picker."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_code: str
    customer_type: CustomerType
    client_name: str
    business_name: str | None
    mobile_number: str | None
    gst_number: str | None
    pan_number: str | None
    address_line_1: str | None
    address_line_2: str | None
    city: str | None
    state: str | None
    pincode: str | None


class CustomerAuditEntry(BaseModel):
    """One audit row for the customer details page."""

    id: uuid.UUID
    action: str
    performed_by_name: str | None
    customer_name: str | None
    timestamp: datetime


class CustomerWorkOrderItem(BaseModel):
    """Work-order summary for the customer's history tab."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    number: str
    title: str | None
    status: str
    order_date: date | None
    created_at: datetime


class CustomerInvoiceItem(BaseModel):
    """Invoice summary for the customer's history tab."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    number: str
    status: str
    total: Decimal
    issue_date: date | None
    created_at: datetime
