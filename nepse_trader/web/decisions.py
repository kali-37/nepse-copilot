"""Decision board and manual execution records for the simple workspace."""
from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from nepse_trader.advisor.decision_state import decision_state
from nepse_trader.advisor.decisions import DecisionsChanged, publish_decisions
from nepse_trader.advisor.positions import record_trade, set_cash

router = APIRouter(prefix="/api/decisions", tags=["decisions"])


def _publish_advice(pipe, saved_message: str = ""):
    try:
        return publish_decisions(pipe)
    except DecisionsChanged as exc:
        raise HTTPException(
            409,
            (saved_message + " " if saved_message else "")
            + "Market data is still changing. Wait for the refresh to finish, then retry advice.",
        ) from exc


@router.get("")
def decision_board():
    from nepse_trader.web.api import _pipeline
    pipe = _pipeline()
    row = pipe.storage._conn.execute("SELECT payload FROM decision_runs ORDER BY generated_at DESC LIMIT 1").fetchone()
    board = json.loads(row[0]) if row else None
    if board and board.get("state_key") == decision_state(pipe, date.today()):
        return board
    return _publish_advice(pipe)


@router.get("/performance")
def recommendation_performance():
    from nepse_trader.advisor.track_record import performance_report
    from nepse_trader.web.api import _storage
    return performance_report(_storage())


@router.post("/performance/score")
def update_recommendation_performance():
    from datetime import timedelta

    from nepse_trader.advisor.decision_state import session_dates
    from nepse_trader.advisor.track_record import performance_report, score_recommendations
    from nepse_trader.calendar import previous_trading_day
    from nepse_trader.web.api import _pipeline
    pipe = _pipeline()
    today = date.today()
    completed = today if session_dates(today)[2] == "after_close" else previous_trading_day(today-timedelta(days=1))
    scored = score_recommendations(pipe, completed=completed)
    return {"scored": scored, "performance": performance_report(pipe.storage)}


class CashRequest(BaseModel):
    cash: Decimal = Field(ge=0, le=10**12, allow_inf_nan=False)


@router.put("/cash")
def update_cash(body: CashRequest):
    from nepse_trader.web.api import _pipeline
    pipe = _pipeline()
    set_cash(pipe.storage, body.cash)
    return _publish_advice(pipe, "Your available cash was saved.")


class TradeRecordRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=25)
    side: Literal["buy", "sell"]
    quantity: int = Field(gt=0, le=10**8)
    price: Decimal = Field(gt=0, le=10**8, allow_inf_nan=False)
    business_date: date
    origin_decision_id: str | None = Field(None,max_length=64)
    origin_horizon: Literal["day","month","investment"] | None = None
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
                              target=body.target, horizon_days=body.horizon_days, record_id=body.record_id,origin_decision_id=body.origin_decision_id,origin_horizon=body.origin_horizon)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    # The execution is already committed. Invalidate before analysis so a
    # later failure cannot leave a cached board claiming the old holdings.
    with pipe.storage._tx() as conn:
        conn.execute("DELETE FROM decision_runs")
    return {"record": record, "board": _publish_advice(
        pipe, "Your trade was recorded successfully. Do not record it again as a new trade."
    )}


class PositionPlanRequest(BaseModel):
    quantity: int = Field(gt=0, le=10**8)
    stop: float = Field(gt=0, allow_inf_nan=False)
    target: float = Field(gt=0, allow_inf_nan=False)
    average_cost: Decimal | None = Field(None, gt=0, le=10**8, allow_inf_nan=False)
    bought_on: date | None = None
    horizon_days: int | None = Field(None,ge=3,le=252)


@router.put('/holdings/{symbol}/plan')
def update_position_plan(symbol: str, body: PositionPlanRequest):
    from nepse_trader.advisor.positions import set_position_plan
    from nepse_trader.web.api import _pipeline
    pipe = _pipeline()
    try:
        set_position_plan(pipe, symbol=symbol, **body.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return _publish_advice(pipe, "Your exit plan was saved.")


@router.get('/fundamentals/{symbol}')
def fundamental_analysis(symbol: str):
    from nepse_trader.advisor.fundamentals import assess_fundamentals
    from nepse_trader.storage.research import evidence_by_symbol
    from nepse_trader.web.api import _pipeline
    pipe=_pipeline()
    today=date.today()
    symbol=symbol.strip().upper()
    snapshot=pipe.storage.fundamentals(as_of=today).get(symbol)
    row=pipe.storage._conn.execute('SELECT MAX(business_date) FROM fundamentals WHERE symbol=? AND business_date<=?', (symbol,today.isoformat())).fetchone()
    snapshot_date=date.fromisoformat(row[0]) if row and row[0] else None
    quote_row=pipe.storage._conn.execute('SELECT close,business_date FROM reconciled_prices WHERE symbol=? AND business_date<=? ORDER BY business_date DESC LIMIT 1', (symbol,today.isoformat())).fetchone()
    from nepse_trader.advisor.decision_state import session_dates
    expected=session_dates(today)[0]
    quote=quote_row[0] if quote_row and date.fromisoformat(quote_row[1])>=expected else None
    now = datetime.now(UTC)
    evidence = evidence_by_symbol(pipe.storage, as_of=now, symbol=symbol)
    return {'symbol':symbol,'quote':quote,'quote_date':quote_row[1] if quote_row else None,
            **assess_fundamentals(snapshot,quote=quote,snapshot_date=snapshot_date,today=today,
                                  evidence=evidence.get(symbol, ()),symbol=symbol,as_of=now)}


@router.get('/history/{symbol}')
def stock_advice_history(symbol: str):
    from nepse_trader.web.api import _storage
    storage=_storage()
    symbol=symbol.strip().upper()
    trades=[]
    for row in storage._conn.execute('SELECT side,quantity,price,business_date,entry_thesis FROM position_records WHERE symbol=? ORDER BY recorded_at DESC LIMIT 20',(symbol,)):
        trade=dict(row)
        trade['entry_plan']=json.loads(trade.pop('entry_thesis')) if trade['entry_thesis'] else None
        trades.append(trade)
    events=[dict(row) for row in storage._conn.execute('SELECT market_date,previous_action,action,reason,evaluated_at FROM holding_advice_events WHERE symbol=? ORDER BY id DESC LIMIT 20',(symbol,))]
    return {'symbol':symbol,'trades':trades,'events':events}
