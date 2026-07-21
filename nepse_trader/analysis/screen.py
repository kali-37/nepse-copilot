"""Backtest screening: rank strategies across symbols.

Runs a panel of strategies over each symbol's reconciled history and produces a
sorted leaderboard. This is the "finalize with a backtest" step — instead of
trusting one strategy on one symbol, you sweep the whole universe and let the
risk-adjusted numbers (with Nepal costs already baked in) pick the winners.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from nepse_trader.analysis.backtest import Backtester
from nepse_trader.analysis.costs import CostEngine
from nepse_trader.analysis.strategies import STRATEGIES, Strategy, build_strategy
from nepse_trader.models import PriceBar

# Metrics we rank by, with the direction that is "better".
RANKABLE = {
    "sharpe": True,
    "total_return_pct": True,
    "cagr_pct": True,
    "max_drawdown_pct": False,  # lower is better
    "win_rate_pct": True,
}


@dataclass
class ScreenRow:
    symbol: str
    strategy: str
    total_return_pct: float
    cagr_pct: float
    sharpe: float
    max_drawdown_pct: float
    win_rate_pct: float
    num_trades: int
    exposure_pct: float
    final_equity: float
    bars: int

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def _strategies(names: Sequence[str] | None) -> list[Strategy]:
    names = names or list(STRATEGIES)
    return [build_strategy(n) for n in names]


def screen(
    get_bars: Callable[[str], list[PriceBar]],
    symbols: Sequence[str],
    strategy_names: Sequence[str] | None = None,
    *,
    cash: float = 100_000.0,
    min_bars: int = 60,
    cost_engine: CostEngine | None = None,
    rank_by: str = "sharpe",
) -> list[ScreenRow]:
    """Backtest every (symbol, strategy) pair and return a ranked leaderboard.

    `get_bars(symbol)` returns that symbol's chronological PriceBars (typically
    `DailyPipeline.reconciled_bars`). Symbols with fewer than `min_bars` bars are
    skipped. Rows are sorted best-first by `rank_by` (see RANKABLE).
    """
    if rank_by not in RANKABLE:
        raise ValueError(f"rank_by must be one of {sorted(RANKABLE)}")
    bt = Backtester(cost_engine=cost_engine or CostEngine(), initial_cash=cash)
    strategies = _strategies(strategy_names)
    rows: list[ScreenRow] = []
    for symbol in symbols:
        bars = get_bars(symbol)
        if len(bars) < min_bars:
            continue
        for strat in strategies:
            result = bt.run(strat, bars)
            rows.append(
                ScreenRow(
                    symbol=symbol,
                    strategy=strat.name,
                    total_return_pct=round(result.total_return_pct, 2),
                    cagr_pct=round(result.cagr_pct, 2),
                    sharpe=round(result.sharpe, 3),
                    max_drawdown_pct=round(result.max_drawdown_pct, 2),
                    win_rate_pct=round(result.win_rate_pct, 2),
                    num_trades=result.num_trades,
                    exposure_pct=round(result.exposure_pct, 2),
                    final_equity=round(result.final_equity, 2),
                    bars=len(bars),
                )
            )
    higher_is_better = RANKABLE[rank_by]
    rows.sort(key=lambda r: getattr(r, rank_by), reverse=higher_is_better)
    return rows


def best_per_symbol(rows: Sequence[ScreenRow], rank_by: str = "sharpe") -> list[ScreenRow]:
    """Collapse a leaderboard to the single best strategy per symbol."""
    higher_is_better = RANKABLE.get(rank_by, True)
    best: dict[str, ScreenRow] = {}
    for r in rows:
        cur = best.get(r.symbol)
        if cur is None or (
            getattr(r, rank_by) > getattr(cur, rank_by)
            if higher_is_better
            else getattr(r, rank_by) < getattr(cur, rank_by)
        ):
            best[r.symbol] = r
    out = list(best.values())
    out.sort(key=lambda r: getattr(r, rank_by), reverse=higher_is_better)
    return out
