from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from app.rules.types import Discrepancy, Evidence, OrderSnapshot, Severity

RECONCILIATION_GRACE = timedelta(minutes=30)
SCHEDULING_GRACE = timedelta(hours=24)
DUPLICATE_WINDOW = timedelta(seconds=120)

SETTLED_STATES = {"SETTLED"}
CLEARED_STATES = {"CAPTURED", "SETTLED"}
UNRECONCILED_ORDER_STATES = {"CREATED", "PENDING_PAYMENT"}
POST_CONFIRM_STATES = {"CONFIRMED", "READY_FOR_DELIVERY"}


def _rupees(amount: Decimal) -> str:
    return f"Rs {amount:,.2f}"


def payment_reconciliation_lag(snapshot: OrderSnapshot) -> Discrepancy | None:
    if snapshot.status not in UNRECONCILED_ORDER_STATES:
        return None

    cleared = snapshot.amount_in_states(CLEARED_STATES)
    if cleared < snapshot.total_amount:
        return None

    candidates = [
        p for p in snapshot.inbound_payments() if p.status in CLEARED_STATES
    ]
    latest = max(candidates, key=lambda p: p.initiated_at)
    if snapshot.as_of - latest.initiated_at <= RECONCILIATION_GRACE:
        return None

    age = snapshot.as_of - latest.initiated_at
    hours = age.total_seconds() / 3600

    return Discrepancy(
        code="PAYMENT_RECONCILIATION_LAG",
        severity=Severity.CRITICAL,
        title="Payment cleared at the gateway but the order was never moved off pending",
        detail=(
            f"{_rupees(cleared)} has cleared against a total of "
            f"{_rupees(snapshot.total_amount)}, but order {snapshot.order_id} is still "
            f"{snapshot.status}. The last clearing payment was initiated "
            f"{hours:.1f} hours ago. The customer's money has left their account."
        ),
        evidence=(
            Evidence(
                source=f"payments.id={latest.id}",
                field="status",
                value=latest.status,
                observed_at=latest.initiated_at,
            ),
            Evidence(
                source=f"payments.id={latest.id}",
                field="gateway_ref",
                value=latest.gateway_ref,
                observed_at=latest.initiated_at,
            ),
            Evidence(
                source=f"orders.id={snapshot.order_id}",
                field="status",
                value=snapshot.status,
                observed_at=snapshot.updated_at,
            ),
        ),
        suggested_action=(
            "Replay the gateway webhook for "
            f"{latest.gateway_ref} or reconcile the payment manually, then advance the "
            "order so downstream scheduling can run."
        ),
    )


def webhook_missing(snapshot: OrderSnapshot) -> Discrepancy | None:
    cleared = [p for p in snapshot.inbound_payments() if p.status in CLEARED_STATES]
    if not cleared:
        return None

    webhooks = snapshot.events_of_type("PAYMENT_WEBHOOK_RECEIVED")
    if len(webhooks) >= len(cleared):
        return None

    missing = len(cleared) - len(webhooks)

    return Discrepancy(
        code="WEBHOOK_MISSING",
        severity=Severity.WARNING,
        title="Gateway callback never reached the order service",
        detail=(
            f"{len(cleared)} payment(s) cleared at the gateway but only "
            f"{len(webhooks)} webhook event(s) were recorded, leaving {missing} "
            "unprocessed. This is the mechanical cause of the state mismatch, not a "
            "separate fault."
        ),
        evidence=tuple(
            Evidence(
                source=f"payments.id={p.id}",
                field="gateway_ref",
                value=p.gateway_ref,
                observed_at=p.initiated_at,
            )
            for p in cleared
        ),
        suggested_action=(
            "Check the gateway webhook delivery log for these references and replay the "
            "missing callbacks."
        ),
    )


def partial_payment_outstanding(snapshot: OrderSnapshot) -> Discrepancy | None:
    settled = snapshot.amount_in_states(SETTLED_STATES)
    if settled <= Decimal("0") or settled >= snapshot.total_amount:
        return None

    outstanding = snapshot.total_amount - settled

    return Discrepancy(
        code="PARTIAL_PAYMENT_OUTSTANDING",
        severity=Severity.WARNING,
        title="Only the booking amount has been received",
        detail=(
            f"{_rupees(settled)} of {_rupees(snapshot.total_amount)} has settled. "
            f"{_rupees(outstanding)} is still outstanding, which is why the order has "
            "not progressed."
        ),
        evidence=tuple(
            Evidence(
                source=f"payments.id={p.id}",
                field="amount",
                value=str(p.amount),
                observed_at=p.settled_at or p.initiated_at,
            )
            for p in snapshot.inbound_payments()
            if p.status in SETTLED_STATES
        )
        + (
            Evidence(
                source=f"orders.id={snapshot.order_id}",
                field="total_amount",
                value=str(snapshot.total_amount),
                observed_at=snapshot.created_at,
            ),
        ),
        suggested_action=(
            f"Confirm with the customer that {_rupees(outstanding)} is still due and share "
            "a fresh payment link for the balance."
        ),
    )


def delivery_not_scheduled_post_confirm(snapshot: OrderSnapshot) -> Discrepancy | None:
    if snapshot.status not in POST_CONFIRM_STATES:
        return None
    if snapshot.delivery is None or snapshot.delivery.status != "NOT_SCHEDULED":
        return None

    confirmed_at = snapshot.first_event_at("ORDER_CONFIRMED") or snapshot.updated_at
    if snapshot.as_of - confirmed_at <= SCHEDULING_GRACE:
        return None

    hours = (snapshot.as_of - confirmed_at).total_seconds() / 3600

    return Discrepancy(
        code="DELIVERY_NOT_SCHEDULED_POST_CONFIRM",
        severity=Severity.CRITICAL,
        title="Order confirmed but logistics never picked it up",
        detail=(
            f"Order {snapshot.order_id} was confirmed {hours:.1f} hours ago and delivery "
            "is still unscheduled, past the 24 hour scheduling window."
        ),
        evidence=(
            Evidence(
                source=f"orders.id={snapshot.order_id}",
                field="status",
                value=snapshot.status,
                observed_at=confirmed_at,
            ),
            Evidence(
                source=f"deliveries.id={snapshot.delivery.id}",
                field="status",
                value=snapshot.delivery.status,
                observed_at=None,
            ),
        ),
        suggested_action=(
            f"Escalate to the {snapshot.delivery.hub} hub to allocate a delivery slot."
        ),
    )


def delivery_blocked_with_reason(snapshot: OrderSnapshot) -> Discrepancy | None:
    if snapshot.delivery is None or snapshot.delivery.status != "BLOCKED":
        return None

    reason = snapshot.delivery.blocked_reason or "no reason recorded"
    blocked_at = snapshot.first_event_at("DELIVERY_BLOCKED")

    return Discrepancy(
        code="DELIVERY_BLOCKED_WITH_REASON",
        severity=Severity.WARNING,
        title="Delivery is blocked on a non-payment dependency",
        detail=(
            f"Delivery for order {snapshot.order_id} is blocked: {reason}. Payment state "
            "is not the cause here."
        ),
        evidence=(
            Evidence(
                source=f"deliveries.id={snapshot.delivery.id}",
                field="blocked_reason",
                value=reason,
                observed_at=blocked_at,
            ),
        ),
        suggested_action=(
            "Give the customer the documentation timeline rather than a payment "
            "explanation, and chase the blocking dependency."
        ),
    )


def duplicate_payment_detected(snapshot: OrderSnapshot) -> Discrepancy | None:
    cleared = sorted(
        (p for p in snapshot.inbound_payments() if p.status in CLEARED_STATES),
        key=lambda p: p.initiated_at,
    )

    for earlier, later in zip(cleared, cleared[1:]):
        if earlier.amount != later.amount:
            continue
        if later.initiated_at - earlier.initiated_at > DUPLICATE_WINDOW:
            continue

        gap = (later.initiated_at - earlier.initiated_at).total_seconds()

        return Discrepancy(
            code="DUPLICATE_PAYMENT_DETECTED",
            severity=Severity.CRITICAL,
            title="Customer was charged twice for the same amount",
            detail=(
                f"Two separate payments of {_rupees(later.amount)} cleared {gap:.0f} "
                "seconds apart. Only one is owed."
            ),
            evidence=(
                Evidence(
                    source=f"payments.id={earlier.id}",
                    field="gateway_ref",
                    value=earlier.gateway_ref,
                    observed_at=earlier.initiated_at,
                ),
                Evidence(
                    source=f"payments.id={later.id}",
                    field="gateway_ref",
                    value=later.gateway_ref,
                    observed_at=later.initiated_at,
                ),
            ),
            suggested_action=(
                f"Confirm a refund is in flight for {later.gateway_ref} and give the "
                "customer the expected credit date."
            ),
        )

    return None


def refund_in_flight(snapshot: OrderSnapshot) -> Discrepancy | None:
    pending = [p for p in snapshot.refunds() if p.status == "REFUND_PENDING"]
    if not pending:
        return None

    total = sum((p.amount for p in pending), Decimal("0"))

    return Discrepancy(
        code="REFUND_IN_FLIGHT",
        severity=Severity.INFO,
        title="A refund has been initiated but not settled",
        detail=(
            f"{_rupees(total)} across {len(pending)} refund(s) is initiated and awaiting "
            "settlement, so the customer will not see the credit yet."
        ),
        evidence=tuple(
            Evidence(
                source=f"payments.id={p.id}",
                field="status",
                value=p.status,
                observed_at=p.initiated_at,
            )
            for p in pending
        ),
        suggested_action=(
            "Tell the customer the refund is processing and quote the standard 5 to 7 "
            "working day settlement window."
        ),
    )


def orphan_utr(snapshot: OrderSnapshot) -> Discrepancy | None:
    orphans = [
        p
        for p in snapshot.inbound_payments()
        if p.status == "FAILED" and p.bank_utr is not None
    ]
    if not orphans:
        return None

    payment = orphans[0]

    return Discrepancy(
        code="ORPHAN_UTR",
        severity=Severity.CRITICAL,
        title="Bank reference exists on a payment the gateway declined",
        detail=(
            f"Payment {payment.id} carries bank reference {payment.bank_utr} but the "
            f"gateway marked it FAILED: {payment.failure_reason or 'no reason recorded'}. "
            "The customer's bank debited them while our ledger has no credit."
        ),
        evidence=(
            Evidence(
                source=f"payments.id={payment.id}",
                field="bank_utr",
                value=payment.bank_utr or "",
                observed_at=payment.initiated_at,
            ),
            Evidence(
                source=f"payments.id={payment.id}",
                field="status",
                value=payment.status,
                observed_at=payment.initiated_at,
            ),
        ),
        suggested_action=(
            f"Raise a gateway dispute with {payment.bank_utr} and tell the customer an "
            "auto-reversal is expected within 5 to 7 working days."
        ),
    )


def refund_on_delivered_order(snapshot: OrderSnapshot) -> Discrepancy | None:
    if snapshot.status != "DELIVERED":
        return None
    if not snapshot.refunds():
        return None

    refund = snapshot.refunds()[0]

    return Discrepancy(
        code="REFUND_ON_DELIVERED_ORDER",
        severity=Severity.CRITICAL,
        title="Refund movement on an order already marked delivered",
        detail=(
            f"Order {snapshot.order_id} is DELIVERED but carries refund payment "
            f"{refund.id} for {_rupees(refund.amount)}. Either the delivery or the refund "
            "is wrong."
        ),
        evidence=(
            Evidence(
                source=f"orders.id={snapshot.order_id}",
                field="status",
                value=snapshot.status,
                observed_at=snapshot.updated_at,
            ),
            Evidence(
                source=f"payments.id={refund.id}",
                field="is_refund",
                value="True",
                observed_at=refund.initiated_at,
            ),
        ),
        suggested_action=(
            "Hold the refund and confirm physical handover with the hub before releasing "
            "any credit."
        ),
    )


REGISTRY = (
    payment_reconciliation_lag,
    duplicate_payment_detected,
    orphan_utr,
    refund_on_delivered_order,
    delivery_not_scheduled_post_confirm,
    webhook_missing,
    partial_payment_outstanding,
    delivery_blocked_with_reason,
    refund_in_flight,
)
