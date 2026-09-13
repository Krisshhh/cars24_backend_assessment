from __future__ import annotations

import time
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.llm.history import ConversationStore
from app.llm.orchestrator import answer_query
from app.llm.provider import LLMProvider, ProviderError, get_provider
from app.ratelimit import FixedWindowRateLimiter
from app.schemas import QueryRequest, QueryResponse

router = APIRouter(tags=["query"])
settings = get_settings()

limiter = FixedWindowRateLimiter(
    limit=settings.rate_limit_per_window,
    window_seconds=settings.rate_limit_window_seconds,
)

conversations = ConversationStore(
    max_messages=settings.conversation_max_messages,
    ttl_seconds=settings.conversation_ttl_seconds,
)


def client_key(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def provider_dependency() -> LLMProvider | None:
    try:
        return get_provider()
    except Exception:
        return None


class _UnavailableProvider:
    def complete(self, messages, tools=None, system=None):
        raise ProviderError("LLM provider is not configured")


@router.post("/query", response_model=QueryResponse)
def post_query(
    payload: QueryRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    provider: LLMProvider | None = Depends(provider_dependency),
) -> QueryResponse:
    verdict = limiter.check(client_key(request))
    response.headers["x-ratelimit-limit"] = str(verdict.limit)
    response.headers["x-ratelimit-remaining"] = str(verdict.remaining)

    if not verdict.allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={
                "Retry-After": str(verdict.retry_after),
                "x-ratelimit-limit": str(verdict.limit),
                "x-ratelimit-remaining": "0",
            },
        )

    history = conversations.get(payload.conversation_id)

    started = time.perf_counter()
    result = answer_query(
        db, provider or _UnavailableProvider(), payload.query, history=history
    )
    elapsed = int((time.perf_counter() - started) * 1000)

    conversations.append(payload.conversation_id, payload.query, result.answer)

    return QueryResponse(
        answer=result.answer,
        order_ids_resolved=result.order_ids_resolved,
        tools_called=[asdict(t) for t in result.tools_called],
        discrepancies=result.discrepancies,
        facts_used=result.facts_used,
        degraded=result.degraded,
        iterations=result.iterations,
        request_id=getattr(request.state, "request_id", "-"),
        latency_ms=elapsed,
    )
