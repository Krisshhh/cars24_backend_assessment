from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Customer, Order
from app.rules.types import (
    CustomerView,
    DeliveryView,
    EventView,
    OrderSnapshot,
    PaymentView,
    VehicleView,
)


def _load_order(db: Session, order_id: int) -> Order | None:
    stmt = (
        select(Order)
        .where(Order.id == order_id)
        .options(
            selectinload(Order.customer),
            selectinload(Order.vehicle),
            selectinload(Order.payments),
            selectinload(Order.delivery),
            selectinload(Order.events),
        )
    )
    return db.execute(stmt).scalar_one_or_none()


def get_order_snapshot(
    db: Session, order_id: int, as_of: datetime | None = None
) -> OrderSnapshot | None:
    order = _load_order(db, order_id)
    if order is None:
        return None

    return OrderSnapshot(
        order_id=order.id,
        status=order.status,
        total_amount=order.total_amount,
        booking_amount=order.booking_amount,
        created_at=order.created_at,
        updated_at=order.updated_at,
        customer=CustomerView(
            id=order.customer.id,
            name=order.customer.name,
            phone=order.customer.phone,
            email=order.customer.email,
            city=order.customer.city,
        ),
        vehicle=VehicleView(
            id=order.vehicle.id,
            registration_no=order.vehicle.registration_no,
            make=order.vehicle.make,
            model=order.vehicle.model,
            variant=order.vehicle.variant,
            year=order.vehicle.year,
            fuel_type=order.vehicle.fuel_type,
            transmission=order.vehicle.transmission,
            odometer_km=order.vehicle.odometer_km,
            hub=order.vehicle.hub,
        ),
        payments=tuple(
            PaymentView(
                id=p.id,
                amount=p.amount,
                method=p.method,
                status=p.status,
                gateway_ref=p.gateway_ref,
                bank_utr=p.bank_utr,
                initiated_at=p.initiated_at,
                settled_at=p.settled_at,
                failure_reason=p.failure_reason,
                is_refund=p.is_refund,
            )
            for p in sorted(order.payments, key=lambda x: x.id)
        ),
        delivery=(
            DeliveryView(
                id=order.delivery.id,
                status=order.delivery.status,
                scheduled_date=order.delivery.scheduled_date,
                slot=order.delivery.slot,
                hub=order.delivery.hub,
                blocked_reason=order.delivery.blocked_reason,
                completed_at=order.delivery.completed_at,
            )
            if order.delivery is not None
            else None
        ),
        events=tuple(
            EventView(
                id=e.id,
                event_type=e.event_type,
                source_system=e.source_system,
                payload=e.payload,
                occurred_at=e.occurred_at,
            )
            for e in sorted(order.events, key=lambda x: (x.occurred_at, x.id))
        ),
        as_of=as_of or datetime.now(timezone.utc),
    )


def get_payment_history(db: Session, order_id: int) -> tuple[PaymentView, ...] | None:
    snapshot = get_order_snapshot(db, order_id)
    return snapshot.payments if snapshot else None


def get_delivery_status(db: Session, order_id: int) -> DeliveryView | None:
    snapshot = get_order_snapshot(db, order_id)
    return snapshot.delivery if snapshot else None


def get_order_timeline(
    db: Session, order_id: int, limit: int = 50
) -> tuple[EventView, ...] | None:
    snapshot = get_order_snapshot(db, order_id)
    return snapshot.events[:limit] if snapshot else None


def find_orders_by_customer(
    db: Session, phone: str | None = None, name: str | None = None, limit: int = 10
) -> list[int]:
    if phone is None and name is None:
        return []

    stmt = select(Order.id).join(Customer, Order.customer_id == Customer.id)
    if phone is not None:
        stmt = stmt.where(Customer.phone == phone)
    if name is not None:
        stmt = stmt.where(Customer.name.ilike(f"%{name}%"))

    return list(db.execute(stmt.order_by(Order.id.desc()).limit(limit)).scalars().all())
