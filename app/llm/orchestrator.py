from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.config import get_settings
from app.llm.prompts import DEGRADED_NOTE, NO_ORDER_NOTE, SYSTEM_PROMPT
from app.llm.provider import LLMProvider, ProviderError
from app.llm.tools import (
    TOOL_SCHEMAS,
    ToolError,
    execute_tool,
    extract_order_ids,
    facts_from_result,
)


@dataclass
class ToolInvocation:
    name: str
    arguments: dict
    latency_ms: int
    ok: bool
    error: str | None = None


@dataclass
class QueryResult:
    answer: str
    order_ids_resolved: list[int] = field(default_factory=list)
    tools_called: list[ToolInvocation] = field(default_factory=list)
    discrepancies: list[dict] = field(default_factory=list)
    facts_used: list[str] = field(default_factory=list)
    degraded: bool = False
    iterations: int = 0


def _dedupe(values: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for value in values:
        seen.setdefault(value, None)
    return list(seen)


def _degraded_answer(db: Session, query: str, reason: str) -> QueryResult:
    from app.llm.tools import _run_discrepancy_check

    order_ids = extract_order_ids(query)
    if not order_ids:
        return QueryResult(answer=f"{DEGRADED_NOTE} {NO_ORDER_NOTE}", degraded=True)

    lines = [DEGRADED_NOTE]
    discrepancies: list[dict] = []
    facts: list[str] = []
    resolved: list[int] = []

    for order_id in order_ids:
        result = _run_discrepancy_check(db, {"order_id": order_id})
        if not result.get("found"):
            lines.append(f"Order {order_id} was not found.")
            continue

        resolved.append(order_id)
        facts.extend(facts_from_result("run_discrepancy_check", result))

        if result["clean"]:
            lines.append(
                f"Order {order_id} is {result['order_status']} with no discrepancies "
                "detected."
            )
            continue

        lines.append(f"Order {order_id} is {result['order_status']}.")
        for discrepancy in result["discrepancies"]:
            discrepancies.append(discrepancy)
            lines.append(
                f"[{discrepancy['severity']}] {discrepancy['code']}: "
                f"{discrepancy['detail']} Action: {discrepancy['suggested_action']}"
            )

    return QueryResult(
        answer=" ".join(lines),
        order_ids_resolved=resolved,
        discrepancies=discrepancies,
        facts_used=_dedupe(facts),
        degraded=True,
    )


def answer_query(
    db: Session,
    provider: LLMProvider,
    query: str,
    history: list[dict] | None = None,
) -> QueryResult:
    settings = get_settings()
    max_iterations = settings.max_tool_iterations

    messages: list[dict] = list(history or [])
    messages.append({"role": "user", "content": query})

    invocations: list[ToolInvocation] = []
    discrepancies: list[dict] = []
    facts: list[str] = []
    resolved: list[int] = []

    for iteration in range(1, max_iterations + 1):
        try:
            response = provider.complete(
                messages=messages, tools=TOOL_SCHEMAS, system=SYSTEM_PROMPT
            )
        except ProviderError as exc:
            fallback = _degraded_answer(db, query, str(exc))
            fallback.tools_called = invocations
            fallback.iterations = iteration - 1
            return fallback

        if not response.tool_calls:
            return QueryResult(
                answer=response.text.strip(),
                order_ids_resolved=resolved,
                tools_called=invocations,
                discrepancies=discrepancies,
                facts_used=_dedupe(facts),
                degraded=False,
                iterations=iteration,
            )

        assistant_blocks: list[dict] = []
        if response.text:
            assistant_blocks.append({"type": "text", "text": response.text})
        for call in response.tool_calls:
            assistant_blocks.append(
                {
                    "type": "tool_use",
                    "id": call.id,
                    "name": call.name,
                    "input": call.arguments,
                }
            )
        messages.append({"role": "assistant", "content": assistant_blocks})

        result_blocks: list[dict] = []
        for call in response.tool_calls:
            started = time.perf_counter()
            try:
                result = execute_tool(db, call.name, call.arguments)
                elapsed = int((time.perf_counter() - started) * 1000)
                invocations.append(
                    ToolInvocation(
                        name=call.name,
                        arguments=call.arguments,
                        latency_ms=elapsed,
                        ok=True,
                    )
                )
                facts.extend(facts_from_result(call.name, result))

                if call.name == "run_discrepancy_check" and result.get("found"):
                    discrepancies.extend(result.get("discrepancies", []))
                order_id = result.get("order_id")
                if result.get("found") and isinstance(order_id, int):
                    if order_id not in resolved:
                        resolved.append(order_id)

                result_blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": call.id,
                        "content": json.dumps(result),
                    }
                )
            except ToolError as exc:
                elapsed = int((time.perf_counter() - started) * 1000)
                invocations.append(
                    ToolInvocation(
                        name=call.name,
                        arguments=call.arguments,
                        latency_ms=elapsed,
                        ok=False,
                        error=str(exc),
                    )
                )
                result_blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": call.id,
                        "is_error": True,
                        "content": json.dumps({"error": str(exc)}),
                    }
                )

        messages.append({"role": "user", "content": result_blocks})

    fallback = _degraded_answer(db, query, "tool iteration cap reached")
    fallback.tools_called = invocations
    fallback.discrepancies = fallback.discrepancies or discrepancies
    fallback.iterations = max_iterations
    return fallback
