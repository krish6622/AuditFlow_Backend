"""Pydantic models for the standalone Invoice module."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class LineItemIn(BaseModel):
    description: str = Field(min_length=1, max_length=500)
    amount: Decimal = Field(ge=0, max_digits=12, decimal_places=2)


class InvoiceCreate(BaseModel):
    # Optional: when omitted/blank the server auto-generates {PREFIX}-YYYYMMDD-NNN.
    invoice_number: str | None = Field(default=None, max_length=60)
    invoice_date: date
    customer_name: str = Field(min_length=1, max_length=255)
    customer_address: str | None = None
    mca_charges: Decimal = Field(default=Decimal("0.00"), ge=0, max_digits=12, decimal_places=2)
    discount_percent: Decimal = Field(default=Decimal("0.00"), ge=0, le=100, max_digits=5, decimal_places=2)
    items: list[LineItemIn] = Field(min_length=1)


class LineItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    position: int
    description: str
    amount: Decimal


class InvoiceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_number: str
    invoice_date: date
    customer_name: str
    customer_address: str | None
    mca_charges: Decimal
    discount_percent: Decimal
    gross_total: Decimal
    discount_amount: Decimal
    net_total: Decimal
    items: list[LineItemRead]
    created_at: datetime


class InvoiceListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_number: str
    invoice_date: date
    customer_name: str
    net_total: Decimal
    created_at: datetime


class NextNumberResponse(BaseModel):
    invoice_number: str
