"""Decision board and manual execution records for the simple workspace."""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from nepse_trader.advisor.decision_state import decision_state
from nepse_trader.advisor.decisions import publish_decisions
from nepse_trader.advisor.positions import record_trade, set_cash

router = APIRouter(prefix="/api/decisions", tags=["decisions"])


@router.get("")
def decision_board():
    from nepse_trader.web.api import _pipeline
    pipe = _pipeline()
    row = pipe.storage._conn.execute("SELECT payload FROM decision_runs ORDER BY generated_at DESC LIMIT 1").fetchone()
    board = json.loads(row[0]) if row else None
    if board and board.get("state_key") == decision_state(pipe, date.today()):
        return board
    return publish_decisions(pipe)


class CashRequest(BaseModel):
    cash: Decimal = Field(ge=0, le=10**12, allow_inf_nan=False)


@router.put("/cash")
def update_cash(body: CashRequest):
    from nepse_trader.web.api import _pipeline
    pipe = _pipeline()
    set_cash(pipe.storage, body.cash)
    return publish_decisions(pipe)


class TradeRecordRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=25)
    side: Literal["buy", "sell"]
    quantity: int = Field(gt=0, le=10**8)
    price: Decimal = Field(gt=0, le=10**8, allow_inf_nan=False)
    business_date: date
    record_id: str | None = Field(None, min_length=32, max_length=36)
    stop: float | None = Field(None, gt=0, allow_inf_nan=False)
    target: float | None = Field(None, gt=0, allow_inf_nan=False)
    horizon_days: int = Field(22, ge=3, le=252)


@router.post("/trades")
def record_execution(body: TradeRecordRequest):
    from nepse_trader.web.api import _pipeline
    pipe = _pipeline()
    try:
        record = record_trade(pipe, symbol=body.symbol, side=body.side, quantity=body.quantity,
                              price=body.price, bought_on=body.business_date, stop=body.stop,
                              target=body.target, horizon_days=body.horizon_days, record_id=body.record_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    # The execution is already committed. Invalidate before analysis so a
    # later failure cannot leave a cached board claiming the old holdings.
    with pipe.storage._tx() as conn:
        conn.execute("DELETE FROM decision_runs")
    return {"record": record, "board": publish_decisions(pipe)}


class PositionPlanRequest(BaseModel):
    quantity: int = Field(gt=0, le=10**8)
    stop: float = Field(gt=0, allow_inf_nan=False)
    target: float = Field(gt=0, allow_inf_nan=False)
    average_cost: Decimal | None = Field(None, gt=0, le=10**8, allow_inf_nan=False)
    bought_on: date | None = None


@router.put('/holdings/{symbol}/plan')
def update_position_plan(symbol: str, body: PositionPlanRequest):
    from nepse_trader.advisor.positions import set_position_plan
    from nepse_trader.web.api import _pipeline
    pipe = _pipeline()
    try:
        set_position_plan(pipe, symbol=symbol, **body.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return publish_decisions(pipe)
