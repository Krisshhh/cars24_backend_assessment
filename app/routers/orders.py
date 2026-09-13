from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import repository
from app.db import get_db
from app.rules.engine import run_rules
from app.schemas import DiagnosisOut, EventOut, OrderOut

router = APIRouter(prefix="/orders", tags=["orders"])


def _require_snapshot(db: Session, order_id: int):
    snapshot = repository.get_order_snapshot(db, order_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    return snapshot


@router.get("/{order_id}", response_model=OrderOut)
def read_order(order_id: int, db: Session = Depends(get_db)) -> OrderOut:
    snapshot = _require_snapshot(db, order_id)
    payload = asdict(snapshot)
    payload.pop("as_of")
    return OrderOut(**payload)


@router.get("/{order_id}/timeline", response_model=list[EventOut])
def read_timeline(
    order_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[EventOut]:
    snapshot = _require_snapshot(db, order_id)
    return [EventOut(**asdict(e)) for e in snapshot.events[:limit]]


@router.get("/{order_id}/diagnose", response_model=DiagnosisOut)
def diagnose_order(order_id: int, db: Session = Depends(get_db)) -> DiagnosisOut:
    snapshot = _require_snapshot(db, order_id)
    discrepancies = run_rules(snapshot)

    return DiagnosisOut(
        order_id=snapshot.order_id,
        order_status=snapshot.status,
        evaluated_at=snapshot.as_of,
        clean=not discrepancies,
        discrepancies=[
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
    )
