from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class FuelType(str, Enum):
    PETROL = "PETROL"
    DIESEL = "DIESEL"
    CNG = "CNG"
    ELECTRIC = "ELECTRIC"


class Transmission(str, Enum):
    MANUAL = "MANUAL"
    AUTOMATIC = "AUTOMATIC"


class OrderStatus(str, Enum):
    CREATED = "CREATED"
    PENDING_PAYMENT = "PENDING_PAYMENT"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    CONFIRMED = "CONFIRMED"
    READY_FOR_DELIVERY = "READY_FOR_DELIVERY"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"
    REFUND_INITIATED = "REFUND_INITIATED"
    REFUNDED = "REFUNDED"


class PaymentMethod(str, Enum):
    UPI = "UPI"
    NETBANKING = "NETBANKING"
    CARD = "CARD"
    EMI = "EMI"
    CASH = "CASH"


class PaymentStatus(str, Enum):
    INITIATED = "INITIATED"
    AUTHORIZED = "AUTHORIZED"
    CAPTURED = "CAPTURED"
    SETTLED = "SETTLED"
    FAILED = "FAILED"
    REFUND_PENDING = "REFUND_PENDING"
    REFUNDED = "REFUNDED"


class DeliveryStatus(str, Enum):
    NOT_SCHEDULED = "NOT_SCHEDULED"
    SCHEDULED = "SCHEDULED"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


def _enum_check(column: str, enum_cls: type[Enum], name: str) -> CheckConstraint:
    values = ", ".join(f"'{member.value}'" for member in enum_cls)
    return CheckConstraint(f"{column} IN ({values})", name=name)


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(160), nullable=False)
    city: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    orders: Mapped[list[Order]] = relationship(back_populates="customer")


class Vehicle(Base):
    __tablename__ = "vehicles"
    __table_args__ = (
        _enum_check("fuel_type", FuelType, "ck_vehicles_fuel_type"),
        _enum_check("transmission", Transmission, "ck_vehicles_transmission"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    registration_no: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    make: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(60), nullable=False)
    variant: Mapped[str] = mapped_column(String(60), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    fuel_type: Mapped[str] = mapped_column(String(20), nullable=False)
    transmission: Mapped[str] = mapped_column(String(20), nullable=False)
    odometer_km: Mapped[int] = mapped_column(Integer, nullable=False)
    listed_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    hub: Mapped[str] = mapped_column(String(60), nullable=False)

    orders: Mapped[list[Order]] = relationship(back_populates="vehicle")


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        _enum_check("status", OrderStatus, "ck_orders_status"),
        Index("ix_orders_customer_id", "customer_id"),
        Index("ix_orders_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    booking_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    customer: Mapped[Customer] = relationship(back_populates="orders")
    vehicle: Mapped[Vehicle] = relationship(back_populates="orders")
    payments: Mapped[list[Payment]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )
    delivery: Mapped[Delivery | None] = relationship(
        back_populates="order", uselist=False, cascade="all, delete-orphan"
    )
    events: Mapped[list[OrderEvent]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        _enum_check("method", PaymentMethod, "ck_payments_method"),
        _enum_check("status", PaymentStatus, "ck_payments_status"),
        Index("ix_payments_order_id", "order_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    method: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    gateway_ref: Mapped[str] = mapped_column(String(40), nullable=False)
    bank_utr: Mapped[str | None] = mapped_column(String(30), nullable=True)
    initiated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_refund: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    order: Mapped[Order] = relationship(back_populates="payments")


class Delivery(Base):
    __tablename__ = "deliveries"
    __table_args__ = (
        _enum_check("status", DeliveryStatus, "ck_deliveries_status"),
        Index("ix_deliveries_order_id", "order_id", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    scheduled_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    slot: Mapped[str | None] = mapped_column(String(30), nullable=True)
    hub: Mapped[str] = mapped_column(String(60), nullable=False)
    blocked_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    order: Mapped[Order] = relationship(back_populates="delivery")


class OrderEvent(Base):
    __tablename__ = "order_events"
    __table_args__ = (Index("ix_order_events_order_id_occurred_at", "order_id", "occurred_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    source_system: Mapped[str] = mapped_column(String(40), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    order: Mapped[Order] = relationship(back_populates="events")
