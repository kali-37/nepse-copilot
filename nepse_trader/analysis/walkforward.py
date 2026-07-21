"""Walk-forward optimisation with expanding or rolling windows.

Splits price history into sequential training/validation windows, optimises
strategy parameters on each training fold, evaluates on the validation fold,
and reports aggregate out-of-sample metrics.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from nepse_trader.analysis.backtest import Backtester
from nepse_trader.analysis.strategies import build_strategy
from nepse_trader.models import PriceBar


@dataclass
class WFOFold:
    train_start: date
    train_end: date
    val_start: date
    val_end: date
    best_params: dict[str, Any]
    in_sample_return_pct: float
    out_of_sample_return_pct: float
    num_train_bars: int
    num_val_bars: int


@dataclass
class WFResult:
    strategy_name: str
    folds: list[WFOFold] = field(default_factory=list)
    symbol: str = ""

    @property
    def avg_oos_return_pct(self) -> float:
        if not self.folds:
            return 0.0
        return sum(f.out_of_sample_return_pct for f in self.folds) / len(self.folds)

    @property
    def avg_is_return_pct(self) -> float:
        if not self.folds:
            return 0.0
        return sum(f.in_sample_return_pct for f in self.folds) / len(self.folds)

    @property
    def num_folds(self) -> int:
        return len(self.folds)


def _param_grid(strategy_name: str) -> list[dict[str, Any]]:
    grids: dict[str, list[dict[str, Any]]] = {
        "sma_cross": [
            {"fast": f, "slow": s}
            for f, s in itertools.product([5, 10, 20], [30, 50, 100])
            if f < s
        ],
        "rsi": [
            {"rsi_period": p, "oversold": os, "overbought": ob}
            for p in [7, 14, 21]
            for os in [25, 30]
            for ob in [70, 75]
        ],
        "macd": [
            {"fast": f, "slow": s, "signal": sg}
            for f in [8, 12]
            for s in [21, 26]
            for sg in [7, 9]
            if f < s
        ],
        "bollinger": [
            {"period": p, "num_std": ns}
            for p in [15, 20, 25]
            for ns in [1.5, 2.0, 2.5]
        ],
        "supertrend": [
            {"period": p, "multiplier": m}
            for p in [7, 10, 14]
            for m in [2.0, 2.5, 3.0]
        ],
        "donchian": [
            {"period": p}
            for p in [10, 20, 30]
        ],
        "mean_reversion": [
            {"rsi_period": p, "oversold": os, "overbought": ob}
            for p in [7, 14, 21]
            for os in [25, 30, 35]
            for ob in [65, 70, 75]
        ],
    }
    return grids.get(strategy_name, [{}])


def walk_forward(
    bars: list[PriceBar],
    strategy_name: str,
    train_pct: float = 0.6,
    val_pct: float = 0.2,
    expanding: bool = True,
    backtester_kwargs: dict[str, Any] | None = None,
) -> WFResult:
    if not bars:
        return WFResult(strategy_name=strategy_name)

    bars = sorted(bars, key=lambda b: b.business_date)
    n = len(bars)
    window_size = int(n * (train_pct + val_pct))
    step = int(n * val_pct)
    if window_size >= n or step < 1:
        window_size = n
        step = max(1, n // 4)

    bt_kw = dict(backtester_kwargs or {})
    folds: list[WFOFold] = []
    start = 0

    while start + window_size <= n:
        train_end = start + int(window_size * train_pct / (train_pct + val_pct))
        if expanding:
            train_slice = bars[:train_end]
        else:
            train_slice = bars[start:train_end]
        val_slice = bars[train_end : start + window_size]

        if len(train_slice) < 30 or len(val_slice) < 5:
            start += step
            continue

        best_params: dict[str, Any] = {}
        best_return = -float("inf")

        for params in _param_grid(strategy_name):
            try:
                strat = build_strategy(strategy_name, **params)
            except TypeError:
                continue
            bt = Backtester(**bt_kw)
            r = bt.run(strat, train_slice)
            if r.total_return_pct > best_return:
                best_return = r.total_return_pct
                best_params = dict(params)

        if best_params:
            val_strat = build_strategy(strategy_name, **best_params)
            oos_bt = Backtester(**bt_kw)
            oos_result = oos_bt.run(val_strat, val_slice)
            oos_return = oos_result.total_return_pct
        else:
            oos_return = 0.0

        folds.append(
            WFOFold(
                train_start=train_slice[0].business_date if train_slice else bars[0].business_date,
                train_end=train_slice[-1].business_date if train_slice else bars[0].business_date,
                val_start=val_slice[0].business_date if val_slice else bars[0].business_date,
                val_end=val_slice[-1].business_date if val_slice else bars[0].business_date,
                best_params=best_params,
                in_sample_return_pct=best_return,
                out_of_sample_return_pct=oos_return,
                num_train_bars=len(train_slice),
                num_val_bars=len(val_slice),
            )
        )
        start += step

    sym = bars[0].symbol if bars else ""
    return WFResult(strategy_name=strategy_name, folds=folds, symbol=sym)
