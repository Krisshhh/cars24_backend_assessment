from __future__ import annotations

import random
from datetime import datetime, timedelta
from decimal import Decimal

from app.models import (
    Customer,
    Delivery,
    DeliveryStatus,
    FuelType,
    Order,
    OrderEvent,
    OrderStatus,
    Payment,
    PaymentMethod,
    PaymentStatus,
    Transmission,
    Vehicle,
)

RNG = random.Random(20240913)

FIRST_NAMES = [
    "Rohan", "Priya", "Aditya", "Sneha", "Vikram", "Ananya", "Karan", "Meera",
    "Arjun", "Divya", "Nikhil", "Pooja", "Rahul", "Kavya", "Siddharth", "Isha",
    "Manish", "Neha", "Varun", "Shreya",
]
LAST_NAMES = [
    "Sharma", "Patel", "Mehta", "Desai", "Iyer", "Reddy", "Nair", "Joshi",
    "Shah", "Kulkarni", "Gupta", "Rao", "Chauhan", "Trivedi", "Bhatt",
]
CITIES = ["Ahmedabad", "Mumbai", "Pune", "Bengaluru", "Hyderabad", "Delhi", "Surat", "Jaipur"]
HUBS = [
    "Ahmedabad-Sarkhej", "Mumbai-Andheri", "Pune-Wakad", "Bengaluru-Whitefield",
    "Hyderabad-Gachibowli", "Delhi-Dwarka", "Surat-Adajan", "Jaipur-Malviya",
]
CATALOGUE = [
    ("Maruti", "Swift", "VXi", FuelType.PETROL, Transmission.MANUAL, 520000),
    ("Maruti", "Baleno", "Zeta", FuelType.PETROL, Transmission.AUTOMATIC, 690000),
    ("Hyundai", "Creta", "SX Opt", FuelType.DIESEL, Transmission.AUTOMATIC, 1420000),
    ("Hyundai", "i20", "Asta", FuelType.PETROL, Transmission.MANUAL, 715000),
    ("Tata", "Nexon", "XZ Plus", FuelType.PETROL, Transmission.MANUAL, 895000),
    ("Tata", "Harrier", "XZA", FuelType.DIESEL, Transmission.AUTOMATIC, 1680000),
    ("Honda", "City", "ZX CVT", FuelType.PETROL, Transmission.AUTOMATIC, 1150000),
    ("Mahindra", "XUV700", "AX5", FuelType.DIESEL, Transmission.MANUAL, 1780000),
    ("Kia", "Seltos", "HTK Plus", FuelType.PETROL, Transmission.MANUAL, 1240000),
    ("Maruti", "Ertiga", "VXi CNG", FuelType.CNG, Transmission.MANUAL, 880000),
]
STATE_CODES = ["GJ01", "MH02", "MH12", "KA05", "TS09", "DL08", "GJ05", "RJ14"]

STATUS_WEIGHTS = [
    (OrderStatus.DELIVERED, 60),
    (OrderStatus.CONFIRMED, 12),
    (OrderStatus.READY_FOR_DELIVERY, 8),
    (OrderStatus.PENDING_PAYMENT, 12),
    (OrderStatus.CANCELLED, 5),
    (OrderStatus.PARTIALLY_PAID, 3),
]


def _phone(index: int) -> str:
    return f"+919{RNG.randint(10, 99)}{index:07d}"[:13]


def _registration(index: int) -> str:
    code = RNG.choice(STATE_CODES)
    letters = "".join(RNG.choice("ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(2))
    return f"{code}{letters}{RNG.randint(1000, 9999)}"


def _weighted_status() -> OrderStatus:
    population = [status for status, _ in STATUS_WEIGHTS]
    weights = [weight for _, weight in STATUS_WEIGHTS]
    return RNG.choices(population, weights=weights, k=1)[0]


def build_bulk(count: int, now: datetime) -> dict[str, list]:
    customers: list[Customer] = []
    vehicles: list[Vehicle] = []
    orders: list[Order] = []
    payments: list[Payment] = []
    deliveries: list[Delivery] = []
    events: list[OrderEvent] = []

    payment_id = 1
    delivery_id = 1
    event_id = 1

    used_registrations: set[str] = set()

    for index in range(1, count + 1):
        first = RNG.choice(FIRST_NAMES)
        last = RNG.choice(LAST_NAMES)
        city_index = RNG.randrange(len(CITIES))

        customers.append(
            Customer(
                id=index,
                name=f"{first} {last}",
                phone=_phone(index),
                email=f"{first.lower()}.{last.lower()}{index}@example.com",
                city=CITIES[city_index],
                created_at=now - timedelta(days=RNG.randint(40, 900)),
            )
        )

        make, model, variant, fuel, transmission, base_price = RNG.choice(CATALOGUE)
        registration = _registration(index)
        while registration in used_registrations:
            registration = _registration(index)
        used_registrations.add(registration)

        listed_price = Decimal(base_price) + Decimal(RNG.randrange(-60000, 60001, 5000))

        vehicles.append(
            Vehicle(
                id=index,
                registration_no=registration,
                make=make,
                model=model,
                variant=variant,
                year=RNG.randint(2015, 2024),
                fuel_type=fuel.value,
                transmission=transmission.value,
                odometer_km=RNG.randrange(9000, 128000, 500),
                listed_price=listed_price,
                hub=HUBS[city_index],
            )
        )

        status = _weighted_status()
        created_at = now - timedelta(days=RNG.randint(2, 180), hours=RNG.randint(0, 23))
        booking_amount = Decimal(RNG.choice([10000, 25000]))

        orders.append(
            Order(
                id=index,
                customer_id=index,
                vehicle_id=index,
                status=status.value,
                total_amount=listed_price,
                booking_amount=booking_amount,
                created_at=created_at,
                updated_at=created_at + timedelta(hours=RNG.randint(1, 72)),
            )
        )

        events.append(
            OrderEvent(
                id=event_id,
                order_id=index,
                event_type="ORDER_CREATED",
                source_system="ORDER_SVC",
                payload={"channel": RNG.choice(["APP", "WEB", "HUB_WALKIN"])},
                occurred_at=created_at,
            )
        )
        event_id += 1

        method = RNG.choice(list(PaymentMethod))

        if status in {
            OrderStatus.CONFIRMED,
            OrderStatus.READY_FOR_DELIVERY,
            OrderStatus.DELIVERED,
        }:
            settled_at = created_at + timedelta(hours=RNG.randint(1, 20))
            payments.append(
                Payment(
                    id=payment_id,
                    order_id=index,
                    amount=listed_price,
                    method=method.value,
                    status=PaymentStatus.SETTLED.value,
                    gateway_ref=f"pay_{RNG.randrange(10**9, 10**10):x}",
                    bank_utr=f"UTR{RNG.randrange(10**11, 10**12)}",
                    initiated_at=created_at + timedelta(minutes=RNG.randint(5, 240)),
                    settled_at=settled_at,
                    is_refund=False,
                )
            )
            payment_id += 1
            events.append(
                OrderEvent(
                    id=event_id,
                    order_id=index,
                    event_type="PAYMENT_WEBHOOK_RECEIVED",
                    source_system="PAYMENT_GATEWAY",
                    payload={"event": "payment.captured"},
                    occurred_at=settled_at,
                )
            )
            event_id += 1

        elif status is OrderStatus.PARTIALLY_PAID:
            settled_at = created_at + timedelta(hours=RNG.randint(1, 12))
            payments.append(
                Payment(
                    id=payment_id,
                    order_id=index,
                    amount=booking_amount,
                    method=method.value,
                    status=PaymentStatus.SETTLED.value,
                    gateway_ref=f"pay_{RNG.randrange(10**9, 10**10):x}",
                    bank_utr=f"UTR{RNG.randrange(10**11, 10**12)}",
                    initiated_at=created_at + timedelta(minutes=RNG.randint(5, 90)),
                    settled_at=settled_at,
                    is_refund=False,
                )
            )
            payment_id += 1

        elif status is OrderStatus.PENDING_PAYMENT and RNG.random() < 0.5:
            payments.append(
                Payment(
                    id=payment_id,
                    order_id=index,
                    amount=listed_price,
                    method=method.value,
                    status=PaymentStatus.FAILED.value,
                    gateway_ref=f"pay_{RNG.randrange(10**9, 10**10):x}",
                    bank_utr=None,
                    initiated_at=created_at + timedelta(minutes=RNG.randint(5, 200)),
                    settled_at=None,
                    failure_reason=RNG.choice(
                        ["Insufficient funds", "Bank declined", "Session timeout"]
                    ),
                    is_refund=False,
                )
            )
            payment_id += 1

        if status is OrderStatus.DELIVERED:
            completed_at = created_at + timedelta(days=RNG.randint(2, 14))
            delivery_status = DeliveryStatus.COMPLETED
            scheduled = completed_at.date()
            blocked_reason = None
        elif status in {OrderStatus.CONFIRMED, OrderStatus.READY_FOR_DELIVERY}:
            delivery_status = DeliveryStatus.SCHEDULED
            scheduled = (now + timedelta(days=RNG.randint(1, 10))).date()
            completed_at = None
            blocked_reason = None
        elif status is OrderStatus.CANCELLED:
            delivery_status = DeliveryStatus.CANCELLED
            scheduled = None
            completed_at = None
            blocked_reason = None
        else:
            delivery_status = DeliveryStatus.NOT_SCHEDULED
            scheduled = None
            completed_at = None
            blocked_reason = None

        deliveries.append(
            Delivery(
                id=delivery_id,
                order_id=index,
                status=delivery_status.value,
                scheduled_date=scheduled,
                slot=RNG.choice(["10:00-13:00", "13:00-16:00", "16:00-19:00"])
                if scheduled
                else None,
                hub=HUBS[city_index],
                blocked_reason=blocked_reason,
                completed_at=completed_at,
            )
        )
        delivery_id += 1

    return {
        "customers": customers,
        "vehicles": vehicles,
        "orders": orders,
        "payments": payments,
        "deliveries": deliveries,
        "events": events,
        "next_payment_id": payment_id,
        "next_delivery_id": delivery_id,
        "next_event_id": event_id,
    }
