from __future__ import annotations

import sys
from datetime import datetime, timezone

from sqlalchemy import text

from app.db import SessionLocal, engine
from app.models import Base
from seed.generators import build_bulk
from seed.scenarios import SCENARIO_ORDER_IDS, _IdPool, build_scenarios

BULK_COUNT = 220

TRUNCATE = text(
    "TRUNCATE TABLE order_events, payments, deliveries, orders, vehicles, customers "
    "RESTART IDENTITY CASCADE"
)

SEQUENCES = [
    ("customers_id_seq", "customers"),
    ("vehicles_id_seq", "vehicles"),
    ("orders_id_seq", "orders"),
    ("payments_id_seq", "payments"),
    ("deliveries_id_seq", "deliveries"),
    ("order_events_id_seq", "order_events"),
]


def run() -> None:
    Base.metadata.create_all(bind=engine)
    now = datetime.now(timezone.utc)

    with SessionLocal() as session:
        session.execute(TRUNCATE)
        session.commit()

        bulk = build_bulk(BULK_COUNT, now)

        session.add_all(bulk["customers"])
        session.add_all(bulk["vehicles"])
        session.flush()
        session.add_all(bulk["orders"])
        session.flush()
        session.add_all(bulk["payments"])
        session.add_all(bulk["deliveries"])
        session.add_all(bulk["events"])
        session.flush()

        ids = _IdPool(
            payment_start=bulk["next_payment_id"],
            delivery_start=bulk["next_delivery_id"],
            event_start=bulk["next_event_id"],
        )
        scenarios = build_scenarios(now, ids)

        session.add_all(scenarios.customers)
        session.add_all(scenarios.vehicles)
        session.flush()
        session.add_all(scenarios.orders)
        session.flush()
        session.add_all(scenarios.payments)
        session.add_all(scenarios.deliveries)
        session.add_all(scenarios.events)

        session.commit()

        for sequence, table in SEQUENCES:
            session.execute(
                text(
                    f"SELECT setval('{sequence}', "
                    f"COALESCE((SELECT MAX(id) FROM {table}), 1), true)"
                )
            )
        session.commit()

        order_count = session.execute(text("SELECT COUNT(*) FROM orders")).scalar_one()
        payment_count = session.execute(text("SELECT COUNT(*) FROM payments")).scalar_one()
        event_count = session.execute(text("SELECT COUNT(*) FROM order_events")).scalar_one()

        missing = session.execute(
            text("SELECT id FROM orders WHERE id = ANY(:ids)"),
            {"ids": SCENARIO_ORDER_IDS},
        ).scalars().all()

    print(f"orders={order_count} payments={payment_count} events={event_count}")
    print(f"scenario_orders_present={sorted(missing)}")

    if sorted(missing) != sorted(SCENARIO_ORDER_IDS):
        print("SEED FAILED: scenario orders missing", file=sys.stderr)
        raise SystemExit(1)

    print("seed ok")


if __name__ == "__main__":
    run()
