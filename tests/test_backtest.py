"""Tests for the long-only Nepal-cost backtester. No network."""

from __future__ import annotations

from datetime import date, timedelta

from nepse_trader.analysis.backtest import Backtester, BacktestResult, _max_drawdown
from nepse_trader.models import PriceBar, Signal, SignalAction, SourceName


def _bars(closes: list[float], start: date | None = None, symbol: str = "ABC") -> list[PriceBar]:
    start = start or date(2024, 1, 1)
    out: list[PriceBar] = []
    for i, c in enumerate(closes):
        out.append(
            PriceBar(
                symbol=symbol,
                business_date=start + timedelta(days=i),
                open=c,
                high=c,
                low=c,
                close=c,
                source=SourceName.MANUAL,
            )
        )
    return out


class _OneTradeStrategy:
    """Emit BUY on the first bar's date and SELL on the last bar's date."""

    name = "one_trade"

    def generate(self, bars: list[PriceBar]) -> list[Signal]:
        if len(bars) < 2:
            return []
        return [
            Signal(
                symbol=bars[0].symbol,
                business_date=bars[0].business_date,
                action=SignalAction.BUY,
                strategy=self.name,
            ),
            Signal(
                symbol=bars[-1].symbol,
                business_date=bars[-1].business_date,
                action=SignalAction.SELL,
                strategy=self.name,
            ),
        ]


class _FlatStrategy:
    name = "flat"

    def generate(self, bars: list[PriceBar]) -> list[Signal]:
        return []


# --------------------------------------------------------------------------


def test_max_drawdown_known_curve():
    curve = [
        (date(2024, 1, 1), 100.0),
        (date(2024, 1, 2), 120.0),  # peak
        (date(2024, 1, 3), 90.0),   # -25% from 120
        (date(2024, 1, 4), 110.0),
        (date(2024, 1, 5), 60.0),   # -50% from 120 (deepest)
    ]
    assert _max_drawdown(curve) == 50.0


def test_max_drawdown_monotonic_rising_is_zero():
    curve = [(date(2024, 1, i + 1), 100.0 + i) for i in range(5)]
    assert _max_drawdown(curve) == 0.0


def test_max_drawdown_empty_is_zero():
    assert _max_drawdown([]) == 0.0


def test_one_trade_profit():
    # Price rises 100 -> 200. One round trip.
    bars = _bars([100.0, 150.0, 180.0, 200.0])
    bt = Backtester(initial_cash=100_000.0)
    res = bt.run(_OneTradeStrategy(), bars)

    assert isinstance(res, BacktestResult)
    assert res.num_trades == 1
    assert len(res.equity_curve) == len(bars)

    trade = res.trades[0]
    assert trade["entry_price"] == 100.0
    assert trade["exit_price"] == 200.0
    assert trade["entry_date"] == bars[0].business_date
    assert trade["exit_date"] == bars[-1].business_date
    # A near-doubling of price stays profitable after fees.
    assert trade["pnl"] > 0
    assert res.total_return_pct > 0
    # Final equity is below a naive fee-free double because of buy+sell fees+CGT.
    assert res.final_equity > 100_000.0
    assert res.win_rate_pct == 100.0


def test_one_trade_loss_reflects_fees():
    # Price falls 200 -> 100. Loss must be larger in magnitude than raw price move
    # because fees are paid on top of the price loss.
    bars = _bars([200.0, 150.0, 120.0, 100.0])
    bt = Backtester(initial_cash=100_000.0)
    res = bt.run(_OneTradeStrategy(), bars)

    assert res.num_trades == 1
    trade = res.trades[0]
    assert trade["pnl"] < 0
    assert res.final_equity < 100_000.0
    assert res.total_return_pct < 0
    # No CGT on a loss.
    assert trade["cgt"] == 0.0
    assert res.win_rate_pct == 0.0
    assert len(res.equity_curve) == len(bars)


def test_final_equity_matches_cash_after_liquidation():
    bars = _bars([100.0, 110.0, 120.0])
    bt = Backtester(initial_cash=50_000.0)
    res = bt.run(_OneTradeStrategy(), bars)
    # After full liquidation the last equity point equals final_equity.
    assert res.equity_curve[-1][1] == res.final_equity


def test_flat_strategy_no_trades():
    bars = _bars([100.0, 90.0, 120.0, 80.0, 130.0])
    bt = Backtester(initial_cash=100_000.0)
    res = bt.run(_FlatStrategy(), bars)

    assert res.num_trades == 0
    assert res.final_equity == 100_000.0
    assert res.total_return_pct == 0.0
    assert res.max_drawdown_pct == 0.0
    assert res.sharpe == 0.0
    assert res.win_rate_pct == 0.0
    assert res.exposure_pct == 0.0
    # Flat cash means an exactly flat equity curve.
    assert len(res.equity_curve) == len(bars)
    assert all(eq == 100_000.0 for _, eq in res.equity_curve)


def test_empty_bars_zero_trade_result():
    bt = Backtester(initial_cash=100_000.0)
    res = bt.run(_OneTradeStrategy(), [])
    assert res.num_trades == 0
    assert res.final_equity == 100_000.0
    assert res.equity_curve == []
    assert res.max_drawdown_pct == 0.0
    assert res.sharpe == 0.0


def test_no_signals_zero_trade_result():
    bars = _bars([100.0, 105.0, 110.0])

    class _Empty:
        name = "empty"

        def generate(self, bars):
            return []

    res = Backtester().run(_Empty(), bars)
    assert res.num_trades == 0
    assert res.final_equity == res.initial_cash


def test_exposure_fraction():
    # BUY on bar 0, SELL on bar 3 -> holding bars 0,1,2 (sell exits on bar 3,
    # which is not counted as held after exit). 4 bars total.
    bars = _bars([100.0, 110.0, 120.0, 130.0])
    res = Backtester().run(_OneTradeStrategy(), bars)
    # Held during bars index 0,1,2 -> 3 of 4 bars.
    assert res.exposure_pct == 75.0


def test_slippage_worsens_fills():
    bars = _bars([100.0, 150.0, 200.0])
    base = Backtester(initial_cash=100_000.0, slippage_pct=0.0).run(_OneTradeStrategy(), bars)
    slipped = Backtester(initial_cash=100_000.0, slippage_pct=1.0).run(_OneTradeStrategy(), bars)
    # Slippage makes buys fill higher and sells fill lower -> strictly worse.
    assert slipped.final_equity < base.final_equity
    assert slipped.trades[0]["entry_price"] > 100.0  # 100 * 1.01
    assert slipped.trades[0]["exit_price"] < 200.0   # 200 * 0.99


def test_summary_and_str_are_compact():
    bars = _bars([100.0, 150.0, 200.0])
    res = Backtester().run(_OneTradeStrategy(), bars)

    summary = res.summary()
    assert summary["strategy_name"] == "one_trade"
    assert summary["num_trades"] == 1
    assert set(summary) == {
        "strategy_name",
        "initial_cash",
        "final_equity",
        "total_return_pct",
        "cagr_pct",
        "max_drawdown_pct",
        "sharpe",
        "num_trades",
        "win_rate_pct",
        "exposure_pct",
    }

    line = str(res)
    assert isinstance(line, str)
    assert "\n" not in line  # one-line report
    assert "one_trade" in line


def test_position_fraction_limits_capital_deployed():
    bars = _bars([100.0, 100.0, 100.0])
    # Flat price: with half the capital deployed, only ~half cash is at risk.
    res = Backtester(initial_cash=100_000.0, position_fraction=0.5).run(
        _OneTradeStrategy(), bars
    )
    trade = res.trades[0]
    # ~50k budget at price 100 buys 497 shares (gross 49,700 + buy fees ~< 300).
    assert trade["qty"] == 497


class _BuyAndHoldStrategy:
    """Emit a single BUY on the first bar and never sell."""

    name = "buy_hold"

    def generate(self, bars: list[PriceBar]) -> list[Signal]:
        if not bars:
            return []
        return [
            Signal(
                symbol=bars[0].symbol,
                business_date=bars[0].business_date,
                action=SignalAction.BUY,
                strategy=self.name,
            )
        ]


def test_open_position_with_none_last_close_marks_at_entry_not_zero():
    # Holding through a last bar with NO close must not zero out the position:
    # final_equity must match the equity-curve tail (entry-price fallback),
    # not collapse to a spurious ~-100% return.
    bars = _bars([100.0, 120.0, 110.0])
    bars.append(
        PriceBar(
            symbol="ABC",
            business_date=bars[-1].business_date + timedelta(days=1),
            close=None,
            source=SourceName.MANUAL,
        )
    )
    bt = Backtester(initial_cash=100_000.0)
    result = bt.run(_BuyAndHoldStrategy(), bars)
    assert result.final_equity == result.equity_curve[-1][1]
    # The position was bought near 100 and is marked at entry, so equity must
    # be in the right ballpark — emphatically not near zero.
    assert result.final_equity > 90_000.0
    assert result.total_return_pct > -10.0
