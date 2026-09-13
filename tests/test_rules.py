from __future__ import annotations

from datetime import timedelta

from conftest import delivery, event, payment, snapshot

from app.rules.definitions import (
    delivery_blocked_with_reason,
    delivery_not_scheduled_post_confirm,
    duplicate_payment_detected,
    orphan_utr,
    partial_payment_outstanding,
    payment_reconciliation_lag,
    refund_in_flight,
    refund_on_delivered_order,
    webhook_missing,
)
from app.rules.engine import run_rules
from app.rules.types import Severity


def codes(snap) -> list[str]:
    return [d.code for d in run_rules(snap)]


class TestPaymentReconciliationLag:
    def test_fires_when_captured_total_sits_on_pending_order(self):
        snap = snapshot(
            status="PENDING_PAYMENT",
            payments=(payment(status="CAPTURED", settled_offset=None, initiated_offset=timedelta(hours=-3)),),
            delivery_view=delivery("NOT_SCHEDULED"),
        )
        result = payment_reconciliation_lag(snap)
        assert result is not None
        assert result.code == "PAYMENT_RECONCILIATION_LAG"
        assert result.severity is Severity.CRITICAL
        assert any(e.field == "gateway_ref" for e in result.evidence)

    def test_silent_within_grace_window(self):
        snap = snapshot(
            status="PENDING_PAYMENT",
            payments=(payment(status="CAPTURED", settled_offset=None, initiated_offset=timedelta(minutes=-10)),),
        )
        assert payment_reconciliation_lag(snap) is None

    def test_silent_when_order_already_advanced(self):
        snap = snapshot(status="CONFIRMED", payments=(payment(status="SETTLED"),))
        assert payment_reconciliation_lag(snap) is None

    def test_silent_when_cleared_amount_is_short(self):
        snap = snapshot(
            status="PENDING_PAYMENT",
            payments=(payment(amount="25000", status="CAPTURED", settled_offset=None),),
        )
        assert payment_reconciliation_lag(snap) is None


class TestWebhookMissing:
    def test_fires_when_capture_has_no_callback(self):
        snap = snapshot(
            status="PENDING_PAYMENT",
            payments=(payment(status="CAPTURED", settled_offset=None),),
            events=(event("PAYMENT_CAPTURED", timedelta(hours=-3)),),
        )
        result = webhook_missing(snap)
        assert result is not None
        assert result.severity is Severity.WARNING

    def test_fires_when_second_capture_has_no_callback(self):
        snap = snapshot(
            payments=(
                payment(payment_id=1, status="SETTLED"),
                payment(payment_id=2, status="CAPTURED", settled_offset=None, gateway_ref="pay_test_0002"),
            ),
            events=(event("PAYMENT_WEBHOOK_RECEIVED", timedelta(hours=-4)),),
        )
        assert webhook_missing(snap) is not None

    def test_silent_when_callbacks_match_captures(self):
        snap = snapshot(
            payments=(payment(status="SETTLED"),),
            events=(event("PAYMENT_WEBHOOK_RECEIVED", timedelta(hours=-4)),),
        )
        assert webhook_missing(snap) is None

    def test_silent_when_no_payment_cleared(self):
        snap = snapshot(status="PENDING_PAYMENT", payments=(payment(status="FAILED", settled_offset=None, bank_utr=None),))
        assert webhook_missing(snap) is None


class TestPartialPaymentOutstanding:
    def test_fires_on_token_only(self):
        snap = snapshot(status="PARTIALLY_PAID", payments=(payment(amount="25000", status="SETTLED"),))
        result = partial_payment_outstanding(snap)
        assert result is not None
        assert "975,000.00" in result.detail

    def test_silent_when_fully_settled(self):
        snap = snapshot(payments=(payment(amount="1000000", status="SETTLED"),))
        assert partial_payment_outstanding(snap) is None

    def test_silent_when_nothing_settled(self):
        snap = snapshot(status="PENDING_PAYMENT", payments=())
        assert partial_payment_outstanding(snap) is None


class TestDeliveryNotScheduledPostConfirm:
    def test_fires_past_scheduling_window(self):
        snap = snapshot(
            status="CONFIRMED",
            delivery_view=delivery("NOT_SCHEDULED"),
            events=(event("ORDER_CONFIRMED", timedelta(days=-3), source_system="ORDER_SVC"),),
        )
        result = delivery_not_scheduled_post_confirm(snap)
        assert result is not None
        assert result.severity is Severity.CRITICAL

    def test_silent_inside_scheduling_window(self):
        snap = snapshot(
            status="CONFIRMED",
            delivery_view=delivery("NOT_SCHEDULED"),
            events=(event("ORDER_CONFIRMED", timedelta(hours=-2), source_system="ORDER_SVC"),),
        )
        assert delivery_not_scheduled_post_confirm(snap) is None

    def test_silent_when_delivery_already_scheduled(self):
        snap = snapshot(status="CONFIRMED", delivery_view=delivery("SCHEDULED"))
        assert delivery_not_scheduled_post_confirm(snap) is None


class TestDeliveryBlocked:
    def test_fires_and_carries_reason(self):
        snap = snapshot(
            status="READY_FOR_DELIVERY",
            delivery_view=delivery("BLOCKED", blocked_reason="RC transfer pending at RTO"),
        )
        result = delivery_blocked_with_reason(snap)
        assert result is not None
        assert "RC transfer" in result.detail

    def test_silent_when_not_blocked(self):
        assert delivery_blocked_with_reason(snapshot(delivery_view=delivery("SCHEDULED"))) is None

    def test_silent_when_no_delivery_row(self):
        assert delivery_blocked_with_reason(snapshot(delivery_view=None)) is None


class TestDuplicatePayment:
    def test_fires_on_same_amount_inside_window(self):
        snap = snapshot(
            payments=(
                payment(payment_id=1, status="SETTLED", initiated_offset=timedelta(hours=-5)),
                payment(
                    payment_id=2,
                    status="CAPTURED",
                    settled_offset=None,
                    gateway_ref="pay_test_0002",
                    initiated_offset=timedelta(hours=-5, seconds=68),
                ),
            )
        )
        result = duplicate_payment_detected(snap)
        assert result is not None
        assert result.severity is Severity.CRITICAL

    def test_silent_outside_window(self):
        snap = snapshot(
            payments=(
                payment(payment_id=1, status="SETTLED", initiated_offset=timedelta(hours=-5)),
                payment(
                    payment_id=2,
                    status="SETTLED",
                    gateway_ref="pay_test_0002",
                    initiated_offset=timedelta(hours=-2),
                ),
            )
        )
        assert duplicate_payment_detected(snap) is None

    def test_silent_on_different_amounts(self):
        snap = snapshot(
            payments=(
                payment(payment_id=1, amount="25000", status="SETTLED", initiated_offset=timedelta(hours=-5)),
                payment(
                    payment_id=2,
                    amount="975000",
                    status="SETTLED",
                    gateway_ref="pay_test_0002",
                    initiated_offset=timedelta(hours=-5, seconds=30),
                ),
            )
        )
        assert duplicate_payment_detected(snap) is None


class TestRefundInFlight:
    def test_fires_on_pending_refund(self):
        snap = snapshot(
            payments=(payment(payment_id=3, status="REFUND_PENDING", is_refund=True, settled_offset=None),)
        )
        result = refund_in_flight(snap)
        assert result is not None
        assert result.severity is Severity.INFO

    def test_silent_when_refund_settled(self):
        snap = snapshot(
            payments=(payment(payment_id=3, status="REFUNDED", is_refund=True),)
        )
        assert refund_in_flight(snap) is None


class TestOrphanUtr:
    def test_fires_on_failed_payment_carrying_utr(self):
        snap = snapshot(
            status="PENDING_PAYMENT",
            payments=(
                payment(
                    status="FAILED",
                    settled_offset=None,
                    bank_utr="UTR113355779900",
                    failure_reason="Gateway declined after bank debit",
                ),
            ),
        )
        result = orphan_utr(snap)
        assert result is not None
        assert "UTR113355779900" in result.detail

    def test_silent_when_failed_payment_has_no_utr(self):
        snap = snapshot(
            status="PENDING_PAYMENT",
            payments=(payment(status="FAILED", settled_offset=None, bank_utr=None),),
        )
        assert orphan_utr(snap) is None


class TestRefundOnDeliveredOrder:
    def test_fires_on_delivered_with_refund(self):
        snap = snapshot(
            status="DELIVERED",
            payments=(
                payment(payment_id=1, status="SETTLED"),
                payment(payment_id=2, status="REFUND_PENDING", is_refund=True, settled_offset=None),
            ),
        )
        assert refund_on_delivered_order(snap) is not None

    def test_silent_on_delivered_without_refund(self):
        snap = snapshot(status="DELIVERED", payments=(payment(status="SETTLED"),))
        assert refund_on_delivered_order(snap) is None


class TestEngine:
    def test_clean_order_produces_nothing(self):
        snap = snapshot(
            status="CONFIRMED",
            payments=(payment(status="SETTLED"),),
            delivery_view=delivery("SCHEDULED"),
            events=(event("PAYMENT_WEBHOOK_RECEIVED", timedelta(hours=-4)),),
        )
        assert run_rules(snap) == []

    def test_webhook_case_yields_both_codes_critical_first(self):
        snap = snapshot(
            status="PENDING_PAYMENT",
            payments=(payment(status="CAPTURED", settled_offset=None, initiated_offset=timedelta(hours=-3)),),
            delivery_view=delivery("NOT_SCHEDULED"),
            events=(event("PAYMENT_CAPTURED", timedelta(hours=-3)),),
        )
        result = codes(snap)
        assert "PAYMENT_RECONCILIATION_LAG" in result
        assert "WEBHOOK_MISSING" in result
        assert result[0] == "PAYMENT_RECONCILIATION_LAG"

    def test_severity_ordering_is_stable(self):
        snap = snapshot(
            status="PENDING_PAYMENT",
            payments=(
                payment(status="CAPTURED", settled_offset=None, initiated_offset=timedelta(hours=-3)),
                payment(payment_id=2, status="REFUND_PENDING", is_refund=True, settled_offset=None),
            ),
            delivery_view=delivery("BLOCKED", blocked_reason="RC transfer pending"),
            events=(event("PAYMENT_CAPTURED", timedelta(hours=-3)),),
        )
        severities = [d.severity for d in run_rules(snap)]
        assert severities == sorted(severities, key=lambda s: {"CRITICAL": 0, "WARNING": 1, "INFO": 2}[s.value])

    def test_rules_perform_no_io(self):
        snap = snapshot(payments=(payment(status="SETTLED"),))
        for rule in __import__("app.rules.definitions", fromlist=["REGISTRY"]).REGISTRY:
            rule(snap)
