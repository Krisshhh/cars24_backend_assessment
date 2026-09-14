from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.rules.types import (
    CustomerView,
    DeliveryView,
    EventView,
    OrderSnapshot,
    PaymentView,
    VehicleView,
)

NOW = datetime(2026, 9, 13, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _isolate_test_environment(monkeypatch):
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    monkeypatch.setattr(settings, "openai_api_key", "")
    monkeypatch.setattr(settings, "gemini_api_key", "")


CUSTOMER = CustomerView(
    id=1, name="Test Customer", phone="+919800000001", email="t@example.com", city="Pune"
)

VEHICLE = VehicleView(
    id=1,
    registration_no="MH12AA0001",
    make="Hyundai",
    model="Creta",
    variant="SX",
    year=2021,
    fuel_type="DIESEL",
    transmission="AUTOMATIC",
    odometer_km=41200,
    hub="Pune-Wakad",
)


def payment(
    payment_id: int = 1,
    amount: str = "1000000",
    status: str = "SETTLED",
    is_refund: bool = False,
    initiated_offset: timedelta = timedelta(hours=-5),
    settled_offset: timedelta | None = timedelta(hours=-4),
    bank_utr: str | None = "UTR000000000001",
    failure_reason: str | None = None,
    gateway_ref: str = "pay_test_0001",
    method: str = "UPI",
) -> PaymentView:
    return PaymentView(
        id=payment_id,
        amount=Decimal(amount),
        method=method,
        status=status,
        gateway_ref=gateway_ref,
        bank_utr=bank_utr,
        initiated_at=NOW + initiated_offset,
        settled_at=NOW + settled_offset if settled_offset is not None else None,
        failure_reason=failure_reason,
        is_refund=is_refund,
    )


def delivery(
    status: str = "SCHEDULED",
    blocked_reason: str | None = None,
    delivery_id: int = 1,
) -> DeliveryView:
    return DeliveryView(
        id=delivery_id,
        status=status,
        scheduled_date=(NOW + timedelta(days=2)).date() if status == "SCHEDULED" else None,
        slot="10:00-13:00" if status == "SCHEDULED" else None,
        hub="Pune-Wakad",
        blocked_reason=blocked_reason,
        completed_at=None,
    )


def event(
    event_type: str,
    offset: timedelta,
    event_id: int = 1,
    source_system: str = "PAYMENT_GATEWAY",
    payload: dict | None = None,
) -> EventView:
    return EventView(
        id=event_id,
        event_type=event_type,
        source_system=source_system,
        payload=payload or {},
        occurred_at=NOW + offset,
    )


def snapshot(
    status: str = "CONFIRMED",
    total: str = "1000000",
    booking: str = "25000",
    payments: tuple[PaymentView, ...] = (),
    delivery_view: DeliveryView | None = None,
    events: tuple[EventView, ...] = (),
    created_offset: timedelta = timedelta(days=-6),
    updated_offset: timedelta = timedelta(days=-5),
) -> OrderSnapshot:
    return OrderSnapshot(
        order_id=9999,
        status=status,
        total_amount=Decimal(total),
        booking_amount=Decimal(booking),
        created_at=NOW + created_offset,
        updated_at=NOW + updated_offset,
        customer=CUSTOMER,
        vehicle=VEHICLE,
        payments=payments,
        delivery=delivery_view,
        events=events,
        as_of=NOW,
    )
