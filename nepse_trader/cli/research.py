"""History and research commands, registered on the existing Typer app."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
from functools import wraps
from typing import Annotated

import typer
from rich.console import Console

from nepse_trader.analysis.portfolio import PortfolioBacktester
from nepse_trader.analysis.shared_portfolio import SharedPortfolioBacktester
from nepse_trader.analysis.strategies import build_strategy
from nepse_trader.analysis.walkforward import walk_forward
from nepse_trader.ingest.history import backfill_history
from nepse_trader.pipeline import DailyPipeline

console = Console()


def _date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError as exc:
        raise typer.BadParameter("Use YYYY-MM-DD.") from exc


def register(app: typer.Typer) -> None:
    for name, command in [("backfill", backfill), ("optimize", optimize),
                          ("portfolio-backtest", portfolio_backtest), ("adjust-prices", adjust_prices)]:
        app.command(name)(_validated(command))


def _validated(command):
    @wraps(command)
    def run(*args, **kwargs):
        try:
            return command(*args, **kwargs)
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc
    return run


def backfill(
    symbols: Annotated[str, typer.Argument(help="Comma-separated tickers, or 'all' for stored symbols")],
    since: Annotated[str | None, typer.Option(help="First published session to keep (YYYY-MM-DD)")] = None,
    until: Annotated[str | None, typer.Option(help="Last session to keep (default: today)")] = None,
    source: Annotated[str, typer.Option(help="Verified history source: sharesansar or chukul")] = "sharesansar",
) -> None:
    """Download published history, cross-check sources, and adjust stored prices."""
    pipe = DailyPipeline(clients=[])
    try:
        names = pipe.storage.symbols() if symbols.lower() == "all" else symbols.split(",")
        result = backfill_history(pipe, names, since=_date(since), until=_date(until), source=source,
                                  on_progress=lambda i, total, symbol: console.print(f"[{i}/{total}] {symbol}"))
        console.print_json(data=result.as_dict())
        if not result.bars:
            raise typer.Exit(1)
    finally:
        pipe.storage.close()


def optimize(
    symbol: str,
    strategy: str = "sma_cross",
    train_pct: float = 0.6,
    val_pct: float = 0.2,
    rolling: bool = False,
) -> None:
    """Optimise on training folds and report the untouched validation folds."""
    pipe = DailyPipeline(clients=[])
    try:
        result = walk_forward(pipe.reconciled_bars(symbol), strategy, train_pct, val_pct, not rolling)
        console.print_json(data={**asdict(result), "folds": [
            {**asdict(f), "train_start": f.train_start.isoformat(), "train_end": f.train_end.isoformat(),
             "val_start": f.val_start.isoformat(), "val_end": f.val_end.isoformat()}
            for f in result.folds], "avg_oos_return_pct": result.avg_oos_return_pct,
            "avg_is_return_pct": result.avg_is_return_pct})
    finally:
        pipe.storage.close()


def portfolio_backtest(symbols: str, strategy: str = "sma_cross", cash: float = 1_000_000,
                       shared: bool = True, rebalance_every: int = 0) -> None:
    """Backtest a symbol basket with Nepal costs and a portfolio equity curve."""
    if cash <= 0:
        raise typer.BadParameter("Cash must be positive.")
    pipe = DailyPipeline(clients=[])
    try:
        names = sorted({s.strip().upper() for s in symbols.split(",") if s.strip()})
        engine = SharedPortfolioBacktester(cash, rebalance_every=rebalance_every) if shared else PortfolioBacktester(initial_cash=cash)
        result = engine.run(build_strategy(strategy), {
            symbol: pipe.reconciled_bars(symbol) for symbol in names})
        console.print_json(data=result.summary())
    finally:
        pipe.storage.close()


def adjust_prices(symbol: str | None = None) -> None:
    """Rebuild adjusted closes from published closes and stored events."""
    pipe = DailyPipeline(clients=[])
    try:
        count = pipe.refresh_adjustments({symbol.upper()} if symbol else None)
        console.print(f"Updated {count} adjusted prices.")
    finally:
        pipe.storage.close()
