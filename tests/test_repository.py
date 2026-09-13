from __future__ import annotations

import os

import pytest
from sqlalchemy import text

from app.db import SessionLocal
from app.repository import find_orders_by_customer, get_order_snapshot
from app.rules.engine import run_rules


def _db_available() -> bool:
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _db_available(), reason="database not reachable, run docker compose up first"
)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_snapshot_loads_all_relations(db):
    snapshot = get_order_snapshot(db, 2231)
    assert snapshot is not None
    assert snapshot.customer.name
    assert snapshot.vehicle.registration_no
    assert len(snapshot.payments) == 2
    assert snapshot.delivery is not None
    assert len(snapshot.events) == 11


def test_unknown_order_returns_none(db):
    assert get_order_snapshot(db, 999999) is None


def test_events_are_chronological(db):
    snapshot = get_order_snapshot(db, 2231)
    timestamps = [e.occurred_at for e in snapshot.events]
    assert timestamps == sorted(timestamps)


@pytest.mark.parametrize(
    "order_id,expected",
    [
        (4521, set()),
        (1289, {"PAYMENT_RECONCILIATION_LAG", "WEBHOOK_MISSING"}),
        (2231, set()),
        (3310, {"DELIVERY_BLOCKED_WITH_REASON"}),
        (7742, {"PARTIAL_PAYMENT_OUTSTANDING"}),
        (5108, {"DUPLICATE_PAYMENT_DETECTED", "WEBHOOK_MISSING", "REFUND_IN_FLIGHT"}),
        (6003, {"ORPHAN_UTR"}),
    ],
)
def test_scenario_produces_expected_codes(db, order_id, expected):
    snapshot = get_order_snapshot(db, order_id)
    assert snapshot is not None
    assert {d.code for d in run_rules(snapshot)} == expected


def test_1289_evidence_names_the_capture(db):
    snapshot = get_order_snapshot(db, 1289)
    lag = next(d for d in run_rules(snapshot) if d.code == "PAYMENT_RECONCILIATION_LAG")
    refs = {e.value for e in lag.evidence}
    assert "pay_Qm3v7Lp42c" in refs
    assert "PENDING_PAYMENT" in refs


def test_find_orders_by_customer_phone(db):
    snapshot = get_order_snapshot(db, 1289)
    assert 1289 in find_orders_by_customer(db, phone=snapshot.customer.phone)


def test_find_orders_requires_an_argument(db):
    assert find_orders_by_customer(db) == []
