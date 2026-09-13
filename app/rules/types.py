from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum


class Severity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


SEVERITY_ORDER = {Severity.CRITICAL: 0, Severity.WARNING: 1, Severity.INFO: 2}


@dataclass(frozen=True)
class Evidence:
    source: str
    field: str
    value: str
    observed_at: datetime | None = None


@dataclass(frozen=True)
class Discrepancy:
    code: str
    severity: Severity
    title: str
    detail: str
    evidence: tuple[Evidence, ...]
    suggested_action: str


@dataclass(frozen=True)
class PaymentView:
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


@dataclass(frozen=True)
class DeliveryView:
    id: int
    status: str
    scheduled_date: date | None
    slot: str | None
    hub: str
    blocked_reason: str | None
    completed_at: datetime | None


@dataclass(frozen=True)
class EventView:
    id: int
    event_type: str
    source_system: str
    payload: dict
    occurred_at: datetime


@dataclass(frozen=True)
class CustomerView:
    id: int
    name: str
    phone: str
    email: str
    city: str


@dataclass(frozen=True)
class VehicleView:
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


@dataclass(frozen=True)
class OrderSnapshot:
    order_id: int
    status: str
    total_amount: Decimal
    booking_amount: Decimal
    created_at: datetime
    updated_at: datetime
    customer: CustomerView
    vehicle: VehicleView
    payments: tuple[PaymentView, ...]
    delivery: DeliveryView | None
    events: tuple[EventView, ...]
    as_of: datetime

    def inbound_payments(self) -> tuple[PaymentView, ...]:
        return tuple(p for p in self.payments if not p.is_refund)

    def refunds(self) -> tuple[PaymentView, ...]:
        return tuple(p for p in self.payments if p.is_refund)

    def amount_in_states(self, states: set[str]) -> Decimal:
        return sum(
            (p.amount for p in self.inbound_payments() if p.status in states),
            Decimal("0"),
        )

    def events_of_type(self, event_type: str) -> tuple[EventView, ...]:
        return tuple(e for e in self.events if e.event_type == event_type)

    def first_event_at(self, event_type: str) -> datetime | None:
        matches = self.events_of_type(event_type)
        return min((e.occurred_at for e in matches), default=None)


Rule = Callable[[OrderSnapshot], "Discrepancy | None"]
