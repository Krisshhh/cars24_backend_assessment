from __future__ import annotations

import time
from dataclasses import asdict

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.llm.orchestrator import answer_query
from app.llm.provider import LLMProvider, ProviderError, get_provider
from app.schemas import QueryRequest, QueryResponse

router = APIRouter(tags=["query"])


def provider_dependency() -> LLMProvider | None:
    try:
        return get_provider()
    except ProviderError:
        return None


class _UnavailableProvider:
    def complete(self, messages, tools=None, system=None):
        raise ProviderError("LLM provider is not configured")


@router.post("/query", response_model=QueryResponse)
def post_query(
    payload: QueryRequest,
    request: Request,
    db: Session = Depends(get_db),
    provider: LLMProvider | None = Depends(provider_dependency),
) -> QueryResponse:
    started = time.perf_counter()
    result = answer_query(db, provider or _UnavailableProvider(), payload.query)
    elapsed = int((time.perf_counter() - started) * 1000)

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
