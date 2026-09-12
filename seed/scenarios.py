from __future__ import annotations

from dataclasses import dataclass, field
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

SCENARIO_ORDER_IDS = [4521, 1289, 2231, 3310, 7742, 5108, 6003]


@dataclass
class ScenarioBundle:
    customers: list[Customer] = field(default_factory=list)
    vehicles: list[Vehicle] = field(default_factory=list)
    orders: list[Order] = field(default_factory=list)
    payments: list[Payment] = field(default_factory=list)
    deliveries: list[Delivery] = field(default_factory=list)
    events: list[OrderEvent] = field(default_factory=list)


class _IdPool:
    def __init__(self, payment_start: int, delivery_start: int, event_start: int) -> None:
        self.payment = payment_start
        self.delivery = delivery_start
        self.event = event_start

    def next_payment(self) -> int:
        value = self.payment
        self.payment += 1
        return value

    def next_delivery(self) -> int:
        value = self.delivery
        self.delivery += 1
        return value

    def next_event(self) -> int:
        value = self.event
        self.event += 1
        return value


def _actor(entity_id: int, name: str, phone_tail: str, city: str, now: datetime) -> Customer:
    return Customer(
        id=entity_id,
        name=name,
        phone=f"+9198{phone_tail}",
        email=f"{name.split()[0].lower()}.{entity_id}@example.com",
        city=city,
        created_at=now - timedelta(days=210),
    )


def _car(
    entity_id: int,
    registration: str,
    make: str,
    model: str,
    variant: str,
    year: int,
    fuel: FuelType,
    transmission: Transmission,
    odometer: int,
    price: int,
    hub: str,
) -> Vehicle:
    return Vehicle(
        id=entity_id,
        registration_no=registration,
        make=make,
        model=model,
        variant=variant,
        year=year,
        fuel_type=fuel.value,
        transmission=transmission.value,
        odometer_km=odometer,
        listed_price=Decimal(price),
        hub=hub,
    )


def build_scenarios(now: datetime, ids: _IdPool) -> ScenarioBundle:
    bundle = ScenarioBundle()

    _scenario_4521(bundle, now, ids)
    _scenario_1289(bundle, now, ids)
    _scenario_2231(bundle, now, ids)
    _scenario_3310(bundle, now, ids)
    _scenario_7742(bundle, now, ids)
    _scenario_5108(bundle, now, ids)
    _scenario_6003(bundle, now, ids)

    return bundle


def _scenario_4521(bundle: ScenarioBundle, now: datetime, ids: _IdPool) -> None:
    customer_id = 9001
    created = now - timedelta(days=6)
    settled = created + timedelta(hours=4)

    bundle.customers.append(_actor(customer_id, "Rohan Sharma", "10004521", "Ahmedabad", now))
    bundle.vehicles.append(
        _car(
            customer_id, "GJ01KP4521", "Maruti", "Baleno", "Zeta", 2022,
            FuelType.PETROL, Transmission.AUTOMATIC, 24500, 690000, "Ahmedabad-Sarkhej",
        )
    )
    bundle.orders.append(
        Order(
            id=4521,
            customer_id=customer_id,
            vehicle_id=customer_id,
            status=OrderStatus.CONFIRMED.value,
            total_amount=Decimal(690000),
            booking_amount=Decimal(25000),
            created_at=created,
            updated_at=settled,
        )
    )
    bundle.payments.append(
        Payment(
            id=ids.next_payment(),
            order_id=4521,
            amount=Decimal(690000),
            method=PaymentMethod.NETBANKING.value,
            status=PaymentStatus.SETTLED.value,
            gateway_ref="pay_Nx8s2Kd91a",
            bank_utr="UTR409812337745",
            initiated_at=created + timedelta(hours=3),
            settled_at=settled,
            is_refund=False,
        )
    )
    bundle.deliveries.append(
        Delivery(
            id=ids.next_delivery(),
            order_id=4521,
            status=DeliveryStatus.SCHEDULED.value,
            scheduled_date=(now + timedelta(days=3)).date(),
            slot="10:00-13:00",
            hub="Ahmedabad-Sarkhej",
            blocked_reason=None,
            completed_at=None,
        )
    )
    for event_type, source, offset, payload in [
        ("ORDER_CREATED", "ORDER_SVC", timedelta(0), {"channel": "APP"}),
        ("PAYMENT_INITIATED", "PAYMENT_GATEWAY", timedelta(hours=3), {"method": "NETBANKING"}),
        ("PAYMENT_CAPTURED", "PAYMENT_GATEWAY", timedelta(hours=3, minutes=6), {"amount": 690000}),
        ("PAYMENT_WEBHOOK_RECEIVED", "PAYMENT_GATEWAY", timedelta(hours=4), {"event": "payment.captured"}),
        ("ORDER_CONFIRMED", "ORDER_SVC", timedelta(hours=4, minutes=5), {}),
        ("DELIVERY_SCHEDULED", "LOGISTICS", timedelta(hours=9), {"slot": "10:00-13:00"}),
    ]:
        bundle.events.append(
            OrderEvent(
                id=ids.next_event(),
                order_id=4521,
                event_type=event_type,
                source_system=source,
                payload=payload,
                occurred_at=created + offset,
            )
        )


def _scenario_1289(bundle: ScenarioBundle, now: datetime, ids: _IdPool) -> None:
    customer_id = 9002
    created = now - timedelta(days=2)
    captured = now - timedelta(hours=3)

    bundle.customers.append(_actor(customer_id, "Priya Mehta", "10001289", "Pune", now))
    bundle.vehicles.append(
        _car(
            customer_id, "MH12JR1289", "Hyundai", "Creta", "SX Opt", 2021,
            FuelType.DIESEL, Transmission.AUTOMATIC, 41200, 1420000, "Pune-Wakad",
        )
    )
    bundle.orders.append(
        Order(
            id=1289,
            customer_id=customer_id,
            vehicle_id=customer_id,
            status=OrderStatus.PENDING_PAYMENT.value,
            total_amount=Decimal(1420000),
            booking_amount=Decimal(25000),
            created_at=created,
            updated_at=created + timedelta(minutes=20),
        )
    )
    bundle.payments.append(
        Payment(
            id=ids.next_payment(),
            order_id=1289,
            amount=Decimal(1420000),
            method=PaymentMethod.UPI.value,
            status=PaymentStatus.CAPTURED.value,
            gateway_ref="pay_Qm3v7Lp42c",
            bank_utr="UTR512700891134",
            initiated_at=captured - timedelta(minutes=4),
            settled_at=None,
            is_refund=False,
        )
    )
    bundle.deliveries.append(
        Delivery(
            id=ids.next_delivery(),
            order_id=1289,
            status=DeliveryStatus.NOT_SCHEDULED.value,
            scheduled_date=None,
            slot=None,
            hub="Pune-Wakad",
            blocked_reason=None,
            completed_at=None,
        )
    )
    bundle.events.append(
        OrderEvent(
            id=ids.next_event(),
            order_id=1289,
            event_type="ORDER_CREATED",
            source_system="ORDER_SVC",
            payload={"channel": "WEB"},
            occurred_at=created,
        )
    )
    bundle.events.append(
        OrderEvent(
            id=ids.next_event(),
            order_id=1289,
            event_type="PAYMENT_INITIATED",
            source_system="PAYMENT_GATEWAY",
            payload={"method": "UPI", "vpa": "priya@okhdfcbank"},
            occurred_at=captured - timedelta(minutes=4),
        )
    )
    bundle.events.append(
        OrderEvent(
            id=ids.next_event(),
            order_id=1289,
            event_type="PAYMENT_CAPTURED",
            source_system="PAYMENT_GATEWAY",
            payload={"amount": 1420000, "gateway_ref": "pay_Qm3v7Lp42c"},
            occurred_at=captured,
        )
    )
    bundle.events.append(
        OrderEvent(
            id=ids.next_event(),
            order_id=1289,
            event_type="CUSTOMER_COMPLAINT",
            source_system="CRM",
            payload={"note": "Customer states amount debited, delivery not scheduled"},
            occurred_at=now - timedelta(minutes=35),
        )
    )


def _scenario_2231(bundle: ScenarioBundle, now: datetime, ids: _IdPool) -> None:
    customer_id = 9003
    created = now - timedelta(days=18)

    bundle.customers.append(_actor(customer_id, "Vikram Desai", "10002231", "Bengaluru", now))
    bundle.vehicles.append(
        _car(
            customer_id, "KA05TM2231", "Tata", "Harrier", "XZA", 2022,
            FuelType.DIESEL, Transmission.AUTOMATIC, 33100, 1680000, "Bengaluru-Whitefield",
        )
    )
    bundle.orders.append(
        Order(
            id=2231,
            customer_id=customer_id,
            vehicle_id=customer_id,
            status=OrderStatus.READY_FOR_DELIVERY.value,
            total_amount=Decimal(1680000),
            booking_amount=Decimal(25000),
            created_at=created,
            updated_at=now - timedelta(days=2),
        )
    )
    bundle.payments.append(
        Payment(
            id=ids.next_payment(),
            order_id=2231,
            amount=Decimal(25000),
            method=PaymentMethod.UPI.value,
            status=PaymentStatus.SETTLED.value,
            gateway_ref="pay_Ht9k1Zb77d",
            bank_utr="UTR601233447781",
            initiated_at=created + timedelta(hours=1),
            settled_at=created + timedelta(hours=2),
            is_refund=False,
        )
    )
    bundle.payments.append(
        Payment(
            id=ids.next_payment(),
            order_id=2231,
            amount=Decimal(1655000),
            method=PaymentMethod.EMI.value,
            status=PaymentStatus.SETTLED.value,
            gateway_ref="pay_Ht9k1Zb912",
            bank_utr="UTR601233990112",
            initiated_at=created + timedelta(days=6),
            settled_at=created + timedelta(days=6, hours=5),
            is_refund=False,
        )
    )
    bundle.deliveries.append(
        Delivery(
            id=ids.next_delivery(),
            order_id=2231,
            status=DeliveryStatus.SCHEDULED.value,
            scheduled_date=(now + timedelta(days=2)).date(),
            slot="13:00-16:00",
            hub="Bengaluru-Whitefield",
            blocked_reason=None,
            completed_at=None,
        )
    )
    for event_type, source, offset, payload in [
        ("ORDER_CREATED", "ORDER_SVC", timedelta(0), {"channel": "HUB_WALKIN"}),
        ("PAYMENT_INITIATED", "PAYMENT_GATEWAY", timedelta(hours=1), {"amount": 25000, "kind": "booking_token"}),
        ("PAYMENT_CAPTURED", "PAYMENT_GATEWAY", timedelta(hours=1, minutes=3), {"amount": 25000}),
        ("PAYMENT_WEBHOOK_RECEIVED", "PAYMENT_GATEWAY", timedelta(hours=2), {"event": "payment.captured"}),
        ("PAYMENT_INITIATED", "PAYMENT_GATEWAY", timedelta(days=6), {"amount": 1655000, "kind": "balance", "lender": "HDFC"}),
        ("PAYMENT_CAPTURED", "PAYMENT_GATEWAY", timedelta(days=6, hours=4), {"amount": 1655000}),
        ("PAYMENT_WEBHOOK_RECEIVED", "PAYMENT_GATEWAY", timedelta(days=6, hours=5), {"event": "payment.captured"}),
        ("ORDER_CONFIRMED", "ORDER_SVC", timedelta(days=6, hours=6), {}),
        ("DELIVERY_SCHEDULED", "LOGISTICS", timedelta(days=7), {"slot": "10:00-13:00"}),
        ("DELIVERY_BLOCKED", "LOGISTICS", timedelta(days=12), {"reason": "Hub inspection recheck"}),
        ("DELIVERY_SCHEDULED", "LOGISTICS", timedelta(days=16), {"slot": "13:00-16:00", "rescheduled": True}),
    ]:
        bundle.events.append(
            OrderEvent(
                id=ids.next_event(),
                order_id=2231,
                event_type=event_type,
                source_system=source,
                payload=payload,
                occurred_at=created + offset,
            )
        )


def _scenario_3310(bundle: ScenarioBundle, now: datetime, ids: _IdPool) -> None:
    customer_id = 9004
    created = now - timedelta(days=11)
    settled = created + timedelta(hours=6)

    bundle.customers.append(_actor(customer_id, "Sneha Iyer", "10003310", "Hyderabad", now))
    bundle.vehicles.append(
        _car(
            customer_id, "TS09BW3310", "Honda", "City", "ZX CVT", 2023,
            FuelType.PETROL, Transmission.AUTOMATIC, 18700, 1150000, "Hyderabad-Gachibowli",
        )
    )
    bundle.orders.append(
        Order(
            id=3310,
            customer_id=customer_id,
            vehicle_id=customer_id,
            status=OrderStatus.READY_FOR_DELIVERY.value,
            total_amount=Decimal(1150000),
            booking_amount=Decimal(25000),
            created_at=created,
            updated_at=now - timedelta(days=4),
        )
    )
    bundle.payments.append(
        Payment(
            id=ids.next_payment(),
            order_id=3310,
            amount=Decimal(1150000),
            method=PaymentMethod.NETBANKING.value,
            status=PaymentStatus.SETTLED.value,
            gateway_ref="pay_Rd4w8Vn03e",
            bank_utr="UTR700988112233",
            initiated_at=created + timedelta(hours=5),
            settled_at=settled,
            is_refund=False,
        )
    )
    bundle.deliveries.append(
        Delivery(
            id=ids.next_delivery(),
            order_id=3310,
            status=DeliveryStatus.BLOCKED.value,
            scheduled_date=None,
            slot=None,
            hub="Hyderabad-Gachibowli",
            blocked_reason="RC transfer pending at RTO, awaiting Form 29/30 acknowledgement",
            completed_at=None,
        )
    )
    for event_type, source, offset, payload in [
        ("ORDER_CREATED", "ORDER_SVC", timedelta(0), {"channel": "APP"}),
        ("PAYMENT_CAPTURED", "PAYMENT_GATEWAY", timedelta(hours=5, minutes=10), {"amount": 1150000}),
        ("PAYMENT_WEBHOOK_RECEIVED", "PAYMENT_GATEWAY", timedelta(hours=6), {"event": "payment.captured"}),
        ("ORDER_CONFIRMED", "ORDER_SVC", timedelta(hours=7), {}),
        ("RC_TRANSFER_PENDING", "LOGISTICS", timedelta(days=3), {"rto": "TS-Hyderabad-Central"}),
        ("DELIVERY_BLOCKED", "LOGISTICS", timedelta(days=7), {"reason": "RC transfer pending at RTO"}),
    ]:
        bundle.events.append(
            OrderEvent(
                id=ids.next_event(),
                order_id=3310,
                event_type=event_type,
                source_system=source,
                payload=payload,
                occurred_at=created + offset,
            )
        )


def _scenario_7742(bundle: ScenarioBundle, now: datetime, ids: _IdPool) -> None:
    customer_id = 9005
    created = now - timedelta(days=5)

    bundle.customers.append(_actor(customer_id, "Karan Joshi", "10007742", "Surat", now))
    bundle.vehicles.append(
        _car(
            customer_id, "GJ05LD7742", "Kia", "Seltos", "HTK Plus", 2022,
            FuelType.PETROL, Transmission.MANUAL, 29800, 1240000, "Surat-Adajan",
        )
    )
    bundle.orders.append(
        Order(
            id=7742,
            customer_id=customer_id,
            vehicle_id=customer_id,
            status=OrderStatus.PARTIALLY_PAID.value,
            total_amount=Decimal(1240000),
            booking_amount=Decimal(25000),
            created_at=created,
            updated_at=created + timedelta(hours=3),
        )
    )
    bundle.payments.append(
        Payment(
            id=ids.next_payment(),
            order_id=7742,
            amount=Decimal(25000),
            method=PaymentMethod.UPI.value,
            status=PaymentStatus.SETTLED.value,
            gateway_ref="pay_Yb2n6Xs58f",
            bank_utr="UTR810455667788",
            initiated_at=created + timedelta(hours=1),
            settled_at=created + timedelta(hours=2),
            is_refund=False,
        )
    )
    bundle.deliveries.append(
        Delivery(
            id=ids.next_delivery(),
            order_id=7742,
            status=DeliveryStatus.NOT_SCHEDULED.value,
            scheduled_date=None,
            slot=None,
            hub="Surat-Adajan",
            blocked_reason=None,
            completed_at=None,
        )
    )
    for event_type, source, offset, payload in [
        ("ORDER_CREATED", "ORDER_SVC", timedelta(0), {"channel": "APP"}),
        ("PAYMENT_CAPTURED", "PAYMENT_GATEWAY", timedelta(hours=1, minutes=2), {"amount": 25000, "kind": "booking_token"}),
        ("PAYMENT_WEBHOOK_RECEIVED", "PAYMENT_GATEWAY", timedelta(hours=2), {"event": "payment.captured"}),
        ("CUSTOMER_COMPLAINT", "CRM", timedelta(days=4), {"note": "Customer believes full amount is paid"}),
    ]:
        bundle.events.append(
            OrderEvent(
                id=ids.next_event(),
                order_id=7742,
                event_type=event_type,
                source_system=source,
                payload=payload,
                occurred_at=created + offset,
            )
        )


def _scenario_5108(bundle: ScenarioBundle, now: datetime, ids: _IdPool) -> None:
    customer_id = 9006
    created = now - timedelta(days=3)
    first_charge = created + timedelta(hours=2)
    second_charge = first_charge + timedelta(seconds=68)

    bundle.customers.append(_actor(customer_id, "Ananya Rao", "10005108", "Mumbai", now))
    bundle.vehicles.append(
        _car(
            customer_id, "MH02QF5108", "Tata", "Nexon", "XZ Plus", 2023,
            FuelType.PETROL, Transmission.MANUAL, 15400, 895000, "Mumbai-Andheri",
        )
    )
    bundle.orders.append(
        Order(
            id=5108,
            customer_id=customer_id,
            vehicle_id=customer_id,
            status=OrderStatus.CONFIRMED.value,
            total_amount=Decimal(895000),
            booking_amount=Decimal(25000),
            created_at=created,
            updated_at=created + timedelta(hours=3),
        )
    )
    bundle.payments.append(
        Payment(
            id=ids.next_payment(),
            order_id=5108,
            amount=Decimal(895000),
            method=PaymentMethod.CARD.value,
            status=PaymentStatus.SETTLED.value,
            gateway_ref="pay_Zk7p3Cw21g",
            bank_utr="UTR902334556677",
            initiated_at=first_charge - timedelta(minutes=2),
            settled_at=first_charge + timedelta(hours=1),
            is_refund=False,
        )
    )
    bundle.payments.append(
        Payment(
            id=ids.next_payment(),
            order_id=5108,
            amount=Decimal(895000),
            method=PaymentMethod.CARD.value,
            status=PaymentStatus.CAPTURED.value,
            gateway_ref="pay_Zk7p3Cw21h",
            bank_utr="UTR902334556690",
            initiated_at=second_charge - timedelta(minutes=2),
            settled_at=None,
            is_refund=False,
        )
    )
    bundle.payments.append(
        Payment(
            id=ids.next_payment(),
            order_id=5108,
            amount=Decimal(895000),
            method=PaymentMethod.CARD.value,
            status=PaymentStatus.REFUND_PENDING.value,
            gateway_ref="rfnd_Zk7p3Cw21h",
            bank_utr=None,
            initiated_at=created + timedelta(hours=5),
            settled_at=None,
            is_refund=True,
        )
    )
    bundle.deliveries.append(
        Delivery(
            id=ids.next_delivery(),
            order_id=5108,
            status=DeliveryStatus.SCHEDULED.value,
            scheduled_date=(now + timedelta(days=4)).date(),
            slot="16:00-19:00",
            hub="Mumbai-Andheri",
            blocked_reason=None,
            completed_at=None,
        )
    )
    for event_type, source, offset, payload in [
        ("ORDER_CREATED", "ORDER_SVC", timedelta(0), {"channel": "WEB"}),
        ("PAYMENT_CAPTURED", "PAYMENT_GATEWAY", timedelta(hours=2), {"gateway_ref": "pay_Zk7p3Cw21g"}),
        ("PAYMENT_CAPTURED", "PAYMENT_GATEWAY", timedelta(hours=2, seconds=68), {"gateway_ref": "pay_Zk7p3Cw21h"}),
        ("PAYMENT_WEBHOOK_RECEIVED", "PAYMENT_GATEWAY", timedelta(hours=3), {"event": "payment.captured"}),
        ("ORDER_CONFIRMED", "ORDER_SVC", timedelta(hours=3, minutes=10), {}),
        ("REFUND_INITIATED", "PAYMENT_GATEWAY", timedelta(hours=5), {"reason": "duplicate_capture"}),
        ("DELIVERY_SCHEDULED", "LOGISTICS", timedelta(hours=8), {"slot": "16:00-19:00"}),
    ]:
        bundle.events.append(
            OrderEvent(
                id=ids.next_event(),
                order_id=5108,
                event_type=event_type,
                source_system=source,
                payload=payload,
                occurred_at=created + offset,
            )
        )


def _scenario_6003(bundle: ScenarioBundle, now: datetime, ids: _IdPool) -> None:
    customer_id = 9007
    created = now - timedelta(days=1)
    attempt = created + timedelta(hours=4)

    bundle.customers.append(_actor(customer_id, "Nikhil Bhatt", "10006003", "Jaipur", now))
    bundle.vehicles.append(
        _car(
            customer_id, "RJ14NC6003", "Maruti", "Ertiga", "VXi CNG", 2021,
            FuelType.CNG, Transmission.MANUAL, 52300, 880000, "Jaipur-Malviya",
        )
    )
    bundle.orders.append(
        Order(
            id=6003,
            customer_id=customer_id,
            vehicle_id=customer_id,
            status=OrderStatus.PENDING_PAYMENT.value,
            total_amount=Decimal(880000),
            booking_amount=Decimal(10000),
            created_at=created,
            updated_at=attempt,
        )
    )
    bundle.payments.append(
        Payment(
            id=ids.next_payment(),
            order_id=6003,
            amount=Decimal(880000),
            method=PaymentMethod.NETBANKING.value,
            status=PaymentStatus.FAILED.value,
            gateway_ref="pay_Vt5m9Jq64i",
            bank_utr="UTR113355779900",
            initiated_at=attempt,
            settled_at=None,
            failure_reason="Gateway declined after bank debit, auto-reversal expected in 5-7 working days",
            is_refund=False,
        )
    )
    bundle.deliveries.append(
        Delivery(
            id=ids.next_delivery(),
            order_id=6003,
            status=DeliveryStatus.NOT_SCHEDULED.value,
            scheduled_date=None,
            slot=None,
            hub="Jaipur-Malviya",
            blocked_reason=None,
            completed_at=None,
        )
    )
    for event_type, source, offset, payload in [
        ("ORDER_CREATED", "ORDER_SVC", timedelta(0), {"channel": "APP"}),
        ("PAYMENT_INITIATED", "PAYMENT_GATEWAY", timedelta(hours=4), {"method": "NETBANKING", "bank": "SBI"}),
        ("CUSTOMER_COMPLAINT", "CRM", timedelta(hours=20), {"note": "Customer shared UTR113355779900, claims debit"}),
    ]:
        bundle.events.append(
            OrderEvent(
                id=ids.next_event(),
                order_id=6003,
                event_type=event_type,
                source_system=source,
                payload=payload,
                occurred_at=created + offset,
            )
        )
