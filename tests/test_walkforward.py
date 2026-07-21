"""Tests for walk-forward optimisation."""

from __future__ import annotations

from datetime import date, timedelta

from nepse_trader.analysis.walkforward import WFResult, walk_forward
from nepse_trader.models import PriceBar, SourceName

START = date(2024, 1, 1)


def _bars(closes: list[float], symbol: str = "ABC") -> list[PriceBar]:
    return [
        PriceBar(
            symbol=symbol,
            business_date=START + timedelta(days=i),
            open=c,
            high=c * 1.02,
            low=c * 0.98,
            close=c,
            volume=10_000,
            source=SourceName.SHARESANSAR,
        )
        for i, c in enumerate(closes)
    ]


def test_walk_forward_returns_folds():
    prices = [100.0 + i * 0.5 for i in range(200)]
    bars = _bars(prices)
    result = walk_forward(bars, "sma_cross", train_pct=0.5, val_pct=0.2)
    assert result.num_folds >= 1
    assert result.folds[0].best_params != {}
    assert isinstance(result.avg_oos_return_pct, float)


def test_avg_oos_is_mean_of_folds():
    result = WFResult(strategy_name="test")
    assert result.avg_oos_return_pct == 0.0
    assert result.avg_is_return_pct == 0.0


def test_empty_bars_returns_empty():
    result = walk_forward([], "sma_cross")
    assert result.num_folds == 0


def test_walk_forward_donchian():
    prices = [100.0 + i * 0.3 for i in range(200)]
    bars = _bars(prices)
    result = walk_forward(bars, "donchian", train_pct=0.5, val_pct=0.2)
    assert result.num_folds >= 1
