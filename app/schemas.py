from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class EvidenceOut(BaseModel):
    source: str
    field: str
    value: str
    observed_at: datetime | None = None


class DiscrepancyOut(BaseModel):
    code: str
    severity: str
    title: str
    detail: str
    evidence: list[EvidenceOut]
    suggested_action: str


class PaymentOut(BaseModel):
    id: int
    amount: Decimal
    method: str
    status: str
    gateway_ref: str
    bank_utr: str | None
    initiated_at: datetime
    settled_at: datetime | None
    failure_reason: str | None
    is_refund: bool


class DeliveryOut(BaseModel):
    id: int
    status: str
    scheduled_date: date | None
    slot: str | None
    hub: str
    blocked_reason: str | None
    completed_at: datetime | None


class EventOut(BaseModel):
    id: int
    event_type: str
    source_system: str
    payload: dict
    occurred_at: datetime


class CustomerOut(BaseModel):
    id: int
    name: str
    phone: str
    email: str
    city: str


class VehicleOut(BaseModel):
    id: int
    registration_no: str
    make: str
    model: str
    variant: str
    year: int
    fuel_type: str
    transmission: str
    odometer_km: int
    hub: str


class OrderOut(BaseModel):
    order_id: int
    status: str
    total_amount: Decimal
    booking_amount: Decimal
    created_at: datetime
    updated_at: datetime
    customer: CustomerOut
    vehicle: VehicleOut
    payments: list[PaymentOut]
    delivery: DeliveryOut | None
    events: list[EventOut]


class DiagnosisOut(BaseModel):
    order_id: int
    order_status: str
    evaluated_at: datetime
    clean: bool
    discrepancies: list[DiscrepancyOut]


class QueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    conversation_id: str | None = None


class ToolInvocationOut(BaseModel):
    name: str
    arguments: dict
    latency_ms: int
    ok: bool
    error: str | None = None


class QueryResponse(BaseModel):
    answer: str
    order_ids_resolved: list[int]
    tools_called: list[ToolInvocationOut]
    discrepancies: list[dict]
    facts_used: list[str]
    degraded: bool
    iterations: int
    request_id: str
    latency_ms: int
