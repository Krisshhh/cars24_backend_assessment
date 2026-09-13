from __future__ import annotations

import re
from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable

from sqlalchemy.orm import Session

from app import repository
from app.rules.engine import run_rules

ORDER_ID_PATTERN = re.compile(r"#?\b(\d{3,7})\b")


class ToolError(Exception):
    pass


TOOL_SCHEMAS: list[dict] = [
    {
        "name": "lookup_order",
        "description": (
            "Fetch the core order record: status, amounts, customer and vehicle. "
            "Use this first for any question about a specific order."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"order_id": {"type": "integer"}},
            "required": ["order_id"],
        },
    },
    {
        "name": "get_payment_history",
        "description": (
            "All payment and refund attempts for an order, with gateway references, "
            "bank UTRs, settlement timestamps and failure reasons."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"order_id": {"type": "integer"}},
            "required": ["order_id"],
        },
    },
    {
        "name": "get_delivery_status",
        "description": (
            "Delivery scheduling state for an order: hub, slot, scheduled date and any "
            "blocking reason."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"order_id": {"type": "integer"}},
            "required": ["order_id"],
        },
    },
    {
        "name": "get_order_timeline",
        "description": (
            "Chronological event log for an order across the order service, payment "
            "gateway, logistics and CRM. Use for full status summaries."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "integer"},
                "limit": {"type": "integer", "default": 50},
            },
            "required": ["order_id"],
        },
    },
    {
        "name": "run_discrepancy_check",
        "description": (
            "Run the deterministic reconciliation engine over an order. Call this "
            "whenever the customer reports a conflict between what they experienced and "
            "what the system shows, or asks why something is stuck. This is the only "
            "authority on whether a discrepancy exists."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"order_id": {"type": "integer"}},
            "required": ["order_id"],
        },
    },
    {
        "name": "find_orders_by_customer",
        "description": (
            "Resolve order ids when the user supplies a phone number or customer name "
            "instead of an order id."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string"},
                "name": {"type": "string"},
            },
        },
    },
]

TOOL_NAMES = {tool["name"] for tool in TOOL_SCHEMAS}


def jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return value


def extract_order_ids(text: str) -> list[int]:
    seen: list[int] = []
    for match in ORDER_ID_PATTERN.finditer(text):
        value = int(match.group(1))
        if value not in seen:
            seen.append(value)
    return seen


def _require_order_id(arguments: dict) -> int:
    if "order_id" not in arguments:
        raise ToolError("missing required argument: order_id")
    try:
        return int(arguments["order_id"])
    except (TypeError, ValueError):
        raise ToolError(
            f"order_id must be an integer, received {arguments['order_id']!r}"
        ) from None


def _lookup_order(db: Session, arguments: dict) -> dict:
    order_id = _require_order_id(arguments)
    snapshot = repository.get_order_snapshot(db, order_id)
    if snapshot is None:
        return {"found": False, "order_id": order_id}

    return jsonable(
        {
            "found": True,
            "order_id": snapshot.order_id,
            "status": snapshot.status,
            "total_amount": snapshot.total_amount,
            "booking_amount": snapshot.booking_amount,
            "created_at": snapshot.created_at,
            "updated_at": snapshot.updated_at,
            "customer": asdict(snapshot.customer),
            "vehicle": asdict(snapshot.vehicle),
        }
    )


def _get_payment_history(db: Session, arguments: dict) -> dict:
    order_id = _require_order_id(arguments)
    payments = repository.get_payment_history(db, order_id)
    if payments is None:
        return {"found": False, "order_id": order_id}
    return jsonable(
        {"found": True, "order_id": order_id, "payments": [asdict(p) for p in payments]}
    )


def _get_delivery_status(db: Session, arguments: dict) -> dict:
    order_id = _require_order_id(arguments)
    snapshot = repository.get_order_snapshot(db, order_id)
    if snapshot is None:
        return {"found": False, "order_id": order_id}
    return jsonable(
        {
            "found": True,
            "order_id": order_id,
            "delivery": asdict(snapshot.delivery) if snapshot.delivery else None,
        }
    )


def _get_order_timeline(db: Session, arguments: dict) -> dict:
    order_id = _require_order_id(arguments)
    limit = int(arguments.get("limit", 50))
    events = repository.get_order_timeline(db, order_id, limit=limit)
    if events is None:
        return {"found": False, "order_id": order_id}
    return jsonable(
        {"found": True, "order_id": order_id, "events": [asdict(e) for e in events]}
    )


def _run_discrepancy_check(db: Session, arguments: dict) -> dict:
    order_id = _require_order_id(arguments)
    snapshot = repository.get_order_snapshot(db, order_id)
    if snapshot is None:
        return {"found": False, "order_id": order_id}

    discrepancies = run_rules(snapshot)
    return jsonable(
        {
            "found": True,
            "order_id": order_id,
            "order_status": snapshot.status,
            "evaluated_at": snapshot.as_of,
            "clean": not discrepancies,
            "discrepancies": [
                {
                    "code": d.code,
                    "severity": d.severity.value,
                    "title": d.title,
                    "detail": d.detail,
                    "evidence": [asdict(e) for e in d.evidence],
                    "suggested_action": d.suggested_action,
                }
                for d in discrepancies
            ],
        }
    )


def _find_orders_by_customer(db: Session, arguments: dict) -> dict:
    phone = arguments.get("phone")
    name = arguments.get("name")
    if not phone and not name:
        raise ToolError("provide at least one of: phone, name")
    return {"order_ids": repository.find_orders_by_customer(db, phone=phone, name=name)}


DISPATCH: dict[str, Callable[[Session, dict], dict]] = {
    "lookup_order": _lookup_order,
    "get_payment_history": _get_payment_history,
    "get_delivery_status": _get_delivery_status,
    "get_order_timeline": _get_order_timeline,
    "run_discrepancy_check": _run_discrepancy_check,
    "find_orders_by_customer": _find_orders_by_customer,
}


def execute_tool(db: Session, name: str, arguments: dict) -> dict:
    handler = DISPATCH.get(name)
    if handler is None:
        raise ToolError(f"unknown tool: {name}")
    return handler(db, arguments)


def facts_from_result(name: str, result: dict) -> list[str]:
    facts: list[str] = []
    order_id = result.get("order_id")

    if not result.get("found", True):
        return [f"orders.id={order_id}.exists=False"]

    if name == "lookup_order":
        facts.append(f"orders.id={order_id}.status={result['status']}")
        facts.append(f"orders.id={order_id}.total_amount={result['total_amount']}")
    elif name == "get_payment_history":
        for payment in result.get("payments", []):
            facts.append(f"payments.id={payment['id']}.status={payment['status']}")
    elif name == "get_delivery_status":
        delivery = result.get("delivery")
        if delivery:
            facts.append(f"deliveries.id={delivery['id']}.status={delivery['status']}")
    elif name == "run_discrepancy_check":
        for discrepancy in result.get("discrepancies", []):
            for evidence in discrepancy.get("evidence", []):
                facts.append(
                    f"{evidence['source']}.{evidence['field']}={evidence['value']}"
                )
    elif name == "get_order_timeline":
        for event in result.get("events", []):
            facts.append(f"order_events.id={event['id']}.type={event['event_type']}")

    return facts
