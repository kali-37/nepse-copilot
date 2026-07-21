"""Tests for risk-managed stop-loss / take-profit in the event-driven backtester."""

from __future__ import annotations

from datetime import date

from nepse_trader.analysis.backtest import Backtester
from nepse_trader.models import PriceBar, Signal, SignalAction, SourceName


class _DummyStrategy:
    def __init__(self, signals: list[Signal]) -> None:
        self.signals = signals

    def generate(self, bars: list[PriceBar]) -> list[Signal]:
        return self.signals


def _bar(
    d: str,
    o: float = 100.0,
    h: float = 110.0,
    lo: float = 90.0,
    c: float = 105.0,
    v: int = 10_000,
    sym: str = "TEST",
) -> PriceBar:
    return PriceBar(
        symbol=sym,
        business_date=date.fromisoformat(d),
        open=o,
        high=h,
        low=lo,
        close=c,
        volume=v,
        source=SourceName.SHARESANSAR,
    )


def _buy_sig(d: str) -> Signal:
    return Signal(
        symbol="TEST",
        business_date=date.fromisoformat(d),
        action=SignalAction.BUY,
        strategy="test",
        reason="entry",
    )


class TestStopLossInBacktest:
    def test_stop_loss_triggers_sell(self):
        bt = Backtester(stop_loss_pct=5.0)
        bars = [
            _bar("2024-01-02", c=100.0),
            _bar("2024-01-03", c=90.0),
            _bar("2024-01-04", c=80.0),
        ]
        result = bt.run(_DummyStrategy([_buy_sig("2024-01-02")]), bars)
        assert len(result.trades) == 1
        assert result.trades[0]["exit_reason"] == "stop_loss"

    def test_stop_loss_not_triggered_when_price_holds(self):
        bt = Backtester(stop_loss_pct=10.0)
        bars = [
            _bar("2024-01-02", c=100.0),
            _bar("2024-01-03", c=95.0),
            _bar("2024-01-04", c=92.0),
        ]
        result = bt.run(_DummyStrategy([_buy_sig("2024-01-02")]), bars)
        # 10% stop at 90, low is 92 — not triggered. But last bar liquidates.
        assert len(result.trades) == 1
        assert result.trades[0]["exit_reason"] == "signal"

    def test_take_profit_triggers(self):
        bt = Backtester(take_profit_pct=5.0)
        bars = [
            _bar("2024-01-02", c=100.0),
            _bar("2024-01-03", c=106.0),
        ]
        result = bt.run(_DummyStrategy([_buy_sig("2024-01-02")]), bars)
        assert len(result.trades) == 1
        assert result.trades[0]["exit_reason"] == "take_profit"

    def test_atr_based_stop_in_backtest(self):
        bt = Backtester(use_atr_stops=True, stop_loss_pct=None)
        bars = [
            _bar("2024-01-02", c=100.0),
            _bar("2024-01-03", c=50.0),
        ]
        # ATR of 25 → stop at 100 - 2*25 = 50, bar 3 close is 50 → triggers
        result = bt.run(
            _DummyStrategy([_buy_sig("2024-01-02")]),
            bars,
            atr_bars={date(2024, 1, 2): 25.0},
        )
        assert len(result.trades) == 1
        assert result.trades[0]["exit_reason"] == "stop_loss"

    def test_risk_sizing_uses_size_position(self):
        bt = Backtester(risk_per_trade_pct=2.0)
        bars = [
            _bar("2024-01-02", c=100.0),
            _bar("2024-01-03", c=50.0),
        ]
        result = bt.run(
            _DummyStrategy([_buy_sig("2024-01-02")]),
            bars,
            atr_bars={date(2024, 1, 2): 20.0},
        )
        assert len(result.trades) == 1
        assert result.trades[0]["qty"] > 0
