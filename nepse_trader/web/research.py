"""Offline research routes kept separate from the dashboard's main API."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from nepse_trader.analysis.market import broker_flows, sector_breadth
from nepse_trader.analysis.portfolio import PortfolioBacktester
from nepse_trader.analysis.shared_portfolio import SharedPortfolioBacktester
from nepse_trader.analysis.strategies import build_strategy
from nepse_trader.analysis.walkforward import walk_forward

router = APIRouter(prefix="/api/research", tags=["research"])


@router.get("/walk-forward")
def walk_forward_endpoint(symbol: str, strategy: str = "sma_cross",
                          train_pct: float = Query(0.6, gt=0, lt=1),
                          val_pct: float = Query(0.2, gt=0, lt=1), rolling: bool = False):
    from nepse_trader.web.api import _pipeline

    bars = _pipeline().reconciled_bars(symbol.upper())[-5000:]
    if len(bars) < 40:
        raise HTTPException(400, "At least 40 price sessions are needed; download history in Operations.")
    try:
        result = walk_forward(bars, strategy, train_pct, val_pct, expanding=not rolling)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {**asdict(result), "avg_is_return_pct": result.avg_is_return_pct,
            "avg_oos_return_pct": result.avg_oos_return_pct}


@router.get("/portfolio")
def portfolio_endpoint(symbols: str, strategy: str = "sma_cross", cash: float = Query(1_000_000, gt=0, allow_inf_nan=False),
                       mode: Literal["shared", "equal"] = "shared",
                       rebalance_every: int = Query(0, ge=0, le=252)):
    from nepse_trader.web.api import _pipeline

    names = sorted({s.strip().upper() for s in symbols.split(",") if s.strip()})
    if not 1 <= len(names) <= 50:
        raise HTTPException(400, "Provide 1–50 ticker symbols.")
    pipe = _pipeline()
    histories = {symbol: pipe.reconciled_bars(symbol)[-5000:] for symbol in names}
    if any(len(bars) < 2 for bars in histories.values()):
        raise HTTPException(400, "Every symbol needs at least two price sessions; download history in Operations.")
    try:
        engine = SharedPortfolioBacktester(cash, rebalance_every=rebalance_every) if mode == "shared" else PortfolioBacktester(initial_cash=cash)
        result = engine.run(build_strategy(strategy), histories)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"summary": result.summary(), "equity_curve": result.equity_curve,
            "trades": result.trades, "per_symbol": result.per_symbol, "mode": mode}


@router.get("/market")
def market_endpoint(business_date: date | None = None, symbol: str | None = None):
    from nepse_trader.web.api import _latest_market_date, _storage

    storage = _storage()
    bd = business_date or _latest_market_date()
    sectors = sector_breadth(storage.reconciled_history_for_date(bd), storage.fundamentals(as_of=bd))
    flows = broker_flows(storage.floorsheet_entries(bd, symbol.upper() if symbol else None))
    displayed = flows if len(flows) <= 200 else flows[:100] + flows[-100:]
    indices = [dict(row) for row in storage._conn.execute(
        "SELECT name,value,change,change_percent,source FROM index_values WHERE business_date=? ORDER BY name,source", (bd.isoformat(),))]
    return {"business_date": bd, "sectors": sectors, "broker_flows": displayed,
            "broker_rows": len(flows), "indices": indices}
