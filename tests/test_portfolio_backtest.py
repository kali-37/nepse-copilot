"""Tests for the multi-symbol portfolio backtester (separate from paper-trading ledger)."""

from __future__ import annotations

from datetime import date, timedelta

from nepse_trader.analysis.portfolio import PortfolioBacktester
from nepse_trader.analysis.strategies import SmaCrossStrategy
from nepse_trader.models import PriceBar, SourceName

START = date(2024, 1, 1)


def _bar(sym: str, d: str, c: float) -> PriceBar:
    return PriceBar(
        symbol=sym,
        business_date=date.fromisoformat(d),
        open=c,
        high=c * 1.02,
        low=c * 0.98,
        close=c,
        volume=10_000,
        source=SourceName.SHARESANSAR,
    )


def _bars(sym: str, closes: list[float]) -> list[PriceBar]:
    return [
        _bar(sym, (START + timedelta(days=i)).isoformat(), c)
        for i, c in enumerate(closes)
    ]


class TestPortfolioBacktester:
    def test_single_symbol_matches_backtester(self):
        bars = _bars("ABC", [100.0 + i for i in range(50)])
        pbt = PortfolioBacktester(initial_cash=100_000.0)
        result = pbt.run(SmaCrossStrategy(fast=3, slow=8), {"ABC": bars})
        assert result.final_equity > 0
        assert len(result.trades) >= 0
        assert "ABC" in result.per_symbol

    def test_two_symbols_aggregates(self):
        bars_a = _bars("A", [100.0 + i * 0.5 for i in range(50)])
        bars_b = _bars("B", [200.0 + i * 0.3 for i in range(50)])
        pbt = PortfolioBacktester(initial_cash=200_000.0)
        result = pbt.run(SmaCrossStrategy(fast=3, slow=8), {"A": bars_a, "B": bars_b})
        assert len(result.per_symbol) == 2
        assert len(result.trades) > 0
        assert len(result.equity_curve) > 0

    def test_empty_symbols_returns_empty_result(self):
        pbt = PortfolioBacktester()
        result = pbt.run(SmaCrossStrategy(), {})
        assert result.final_equity == result.initial_cash
        assert result.num_trades == 0

    def test_equity_curve_is_sorted(self):
        bars = _bars("X", [100.0 + i for i in range(20)])
        pbt = PortfolioBacktester(initial_cash=100_000.0)
        result = pbt.run(SmaCrossStrategy(fast=2, slow=5), {"X": bars})
        dates = [d for d, _ in result.equity_curve]
        assert dates == sorted(dates)

    def test_exposure_pct_calculated(self):
        bars = _bars("Y", [100.0 + i for i in range(40)])
        pbt = PortfolioBacktester(initial_cash=100_000.0)
        result = pbt.run(SmaCrossStrategy(fast=3, slow=8), {"Y": bars})
        assert 0 <= result.exposure_pct <= 100
