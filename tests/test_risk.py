"""Tests for risk-managed position sizing and stop-loss."""

from __future__ import annotations

from nepse_trader.analysis.risk import (
    exposure_pct,
    size_position,
    stop_loss_price,
    take_profit_price,
)


class TestSizePosition:
    def test_simple_fractional(self):
        qty = size_position(equity=100_000.0, price=500.0, max_exposure_pct=50.0)
        # Budget = 50k, price = 500 → qty = 100, lot_size rounds to 100
        assert qty == 100

    def test_atr_driven(self):
        qty = size_position(
            equity=100_000.0,
            price=500.0,
            risk_per_trade_pct=2.0,
            atr=20.0,
            atr_multiple=2.0,
        )
        # risk per share = 40, risk capital = 2000 → qty = 50, lot rounds to 50
        assert qty == 50

    def test_lot_rounding(self):
        qty = size_position(equity=100_000.0, price=300.0, max_exposure_pct=100.0, lot_size=10)
        # budget = 100k, price = 300 → qty = 333, rounded to 330
        assert qty == 330

    def test_zero_equity_returns_zero(self):
        assert size_position(equity=0.0, price=100.0) == 0

    def test_zero_price_returns_zero(self):
        assert size_position(equity=100_000.0, price=0.0) == 0


class TestStopLoss:
    def test_atr_based_stop(self):
        stop = stop_loss_price(entry_price=500.0, atr=20.0, atr_multiple=2.0)
        # 500 - 2*20 = 460
        assert stop == 460.0

    def test_percentage_stop(self):
        stop = stop_loss_price(entry_price=500.0, stop_pct=5.0)
        # 500 * 0.95 = 475
        assert stop == 475.0

    def test_circuit_limit_clamps(self):
        stop = stop_loss_price(entry_price=100.0, atr=30.0, atr_multiple=2.0)
        # raw = 100 - 60 = 40, but circuit = 10% → clamped to 90
        assert stop == 90.0

    def test_no_data_returns_none(self):
        assert stop_loss_price(entry_price=100.0) is None


class TestTakeProfit:
    def test_atr_based(self):
        tp = take_profit_price(entry_price=500.0, atr=20.0, atr_multiple=2.0, risk_reward=2.0)
        # 500 + 2*20*2 = 580
        assert tp == 580.0

    def test_percentage(self):
        tp = take_profit_price(entry_price=500.0, tp_pct=10.0)
        assert tp == 550.0

    def test_no_data_returns_none(self):
        assert take_profit_price(entry_price=100.0) is None


class TestExposure:
    def test_half_deployed(self):
        assert exposure_pct(position_value=50_000.0, equity=100_000.0) == 50.0

    def test_full_deployed(self):
        assert exposure_pct(position_value=100_000.0, equity=100_000.0) == 100.0

    def test_zero_equity(self):
        assert exposure_pct(position_value=50_000.0, equity=0.0) == 0.0
