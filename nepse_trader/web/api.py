from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from nepse_trader.analysis.backtest import Backtester
from nepse_trader.analysis.costs import CostEngine
from nepse_trader.analysis.strategies import STRATEGIES, build_strategy
from nepse_trader.config import get_settings
from nepse_trader.ingest.fundamentals import MeroLaganiFundamentalsClient
from nepse_trader.pipeline import DailyPipeline
from nepse_trader.storage import Storage

log = logging.getLogger("nepse_trader.web")

# ---------------------------------------------------------------------------
# App lifespan — single Storage instance for all requests
# ---------------------------------------------------------------------------
_state: dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    if "storage" not in _state:
        settings = get_settings()
        storage = Storage(settings.db_path)
        _state["storage"] = storage
        log.info("web API started — db_path=%s", settings.db_path)
    yield
    if "storage" in _state:
        _state["storage"].close()
        _state.clear()


app = FastAPI(
    title="NEPSE Trader API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _storage() -> Storage:
    return _state["storage"]


def _parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    return date.fromisoformat(value)


def _pipeline() -> DailyPipeline:
    return DailyPipeline(storage=_storage())


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@app.get("/api/dashboard")
def dashboard():
    return _storage().db_stats()


@app.get("/api/market-breadth")
def market_breadth(business_date: str | None = Query(None)):
    bd = _parse_date(business_date) or date.today()
    return _pipeline().market_breadth(bd)


@app.get("/api/movers")
def movers(business_date: str | None = Query(None), top: int = Query(5)):
    bd = _parse_date(business_date) or date.today()
    gainers, losers = _pipeline().top_movers(bd, top=top)
    return {"gainers": gainers, "losers": losers}


# ---------------------------------------------------------------------------
# Symbols
# ---------------------------------------------------------------------------
@app.get("/api/symbols")
def list_symbols():
    return _storage().symbols()


@app.get("/api/symbols/{symbol}/prices")
def symbol_prices(
    symbol: str,
    start: str | None = Query(None),
    end: str | None = Query(None),
    limit: int = Query(500),
):
    storage = _storage()
    prices = storage.reconciled_history(symbol.upper())
    if start:
        sd = date.fromisoformat(start)
        prices = [p for p in prices if p.business_date >= sd]
    if end:
        ed = date.fromisoformat(end)
        prices = [p for p in prices if p.business_date <= ed]
    if limit:
        prices = prices[-limit:]
    return [
        {
            "business_date": p.business_date.isoformat(),
            "open": p.open,
            "high": p.high,
            "low": p.low,
            "close": p.close,
            "volume": p.volume,
            "turnover": p.turnover,
            "confidence": p.confidence,
        }
        for p in prices
    ]


@app.get("/api/symbols/{symbol}/signals")
def symbol_signals(
    symbol: str,
    strategy: str = Query("sma_cross"),
):
    pipe = _pipeline()
    try:
        sigs = pipe.signals_for(symbol.upper(), strategy)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return [
        {
            "business_date": s.business_date.isoformat(),
            "strategy": s.strategy,
            "action": s.action.value,
            "strength": s.strength,
            "reason": s.reason,
            "price": s.price,
        }
        for s in sigs
    ]


@app.get("/api/symbols/{symbol}/quant")
def symbol_quant(symbol: str):
    pipe = _pipeline()
    rows = pipe.quant_stats([symbol.upper()])
    if not rows:
        raise HTTPException(404, f"No quant data for {symbol.upper()}")
    return rows[0]


@app.get("/api/symbols/{symbol}/fundamentals")
def symbol_fundamentals(symbol: str):
    client = MeroLaganiFundamentalsClient()
    try:
        data = client.fetch_fundamentals(symbol.upper())
    except Exception as e:
        raise HTTPException(502, f"Fundamentals fetch failed: {e}") from e
    if data is None or (data.market_price is None and data.eps is None):
        raise HTTPException(404, f"No fundamentals for {symbol.upper()}")
    return {
        "company_name": data.company_name,
        "sector": data.sector,
        "market_price": data.market_price,
        "eps": data.eps,
        "pe_ratio": data.pe_ratio,
        "book_value": data.book_value,
        "pbv": data.pbv,
        "dividend_pct": data.dividend_pct,
        "market_cap": data.market_cap,
        "shares_outstanding": data.shares_outstanding,
        "high_52w": data.high_52w,
        "low_52w": data.low_52w,
        "avg_volume_30d": data.avg_volume_30d,
    }


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------
@app.get("/api/portfolio")
def portfolio(cash: float = Query(100_000.0)):
    pipe = _pipeline()
    pf = pipe.replay_portfolio(cash)
    return pf.to_dict()


# ---------------------------------------------------------------------------
# Backtest
# ---------------------------------------------------------------------------
@app.get("/api/backtest/screen")
def backtest_screen(
    strategies: str = Query("all", description="Comma list or 'all'"),
    cash: float = Query(100_000.0),
    min_bars: int = Query(60),
    rank_by: str = Query("sharpe"),
    top: int = Query(30),
):
    pipe = _pipeline()
    strat_list = (
        list(STRATEGIES)
        if strategies.strip().lower() == "all"
        else [s.strip() for s in strategies.split(",") if s.strip()]
    )
    rows = pipe.screen_strategies(
        strategy_names=strat_list,
        cash=cash,
        min_bars=min_bars,
        rank_by=rank_by,
    )
    return [r.as_dict() for r in rows[:top]]


@app.get("/api/backtest/run")
def backtest_run(
    symbol: str,
    strategy: str = Query("sma_cross"),
    cash: float = Query(100_000.0),
    fraction: float = Query(1.0),
    fast: int | None = Query(None),
    slow: int | None = Query(None),
    period: int | None = Query(None),
    signal_period: int | None = Query(None, alias="signal"),
):
    pipe = _pipeline()
    bars = pipe.reconciled_bars(symbol.upper())
    if len(bars) < 2:
        raise HTTPException(400, f"Not enough history for {symbol.upper()}")
    kwargs: dict[str, int] = {}
    if fast is not None:
        kwargs["fast"] = fast
    if slow is not None:
        kwargs["slow"] = slow
    if period is not None:
        kwargs["period"] = period
    if signal_period is not None:
        kwargs["signal"] = signal_period
    strat = build_strategy(strategy, **kwargs)
    bt = Backtester(cost_engine=CostEngine(), initial_cash=cash, position_fraction=fraction)
    result = bt.run(strat, bars)
    return {
        "summary": result.summary(),
        "equity_curve": [(d.isoformat(), e) for d, e in result.equity_curve],
        "trades": result.trades,
    }


# ---------------------------------------------------------------------------
# Ingest trigger
# ---------------------------------------------------------------------------
@app.post("/api/ingest")
def trigger_ingest(
    business_date: str | None = Query(None),
    all_sources: bool = Query(True),
    async_: bool = Query(False, alias="async"),
):
    import asyncio

    bd = _parse_date(business_date)
    pipe = _pipeline()
    if async_:
        rep = asyncio.run(pipe.async_ingest(bd))
    else:
        rep = pipe.ingest(bd)
    return rep.as_dict()


# ---------------------------------------------------------------------------
# Serve built frontend (production)
# ---------------------------------------------------------------------------
_static = Path(__file__).resolve().parent.parent.parent / "web" / "dist"
if _static.is_dir():
    app.mount("/", StaticFiles(directory=str(_static), html=True), name="frontend")
    log.info("serving frontend from %s", _static)
else:
    log.info("no built frontend found at %s — API-only mode", _static)
