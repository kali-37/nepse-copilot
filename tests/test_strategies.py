"""Tests for trading strategies — pure, fixture-driven, no network."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from nepse_trader.analysis.strategies import (
    STRATEGIES,
    BollingerStrategy,
    CompositeStrategy,
    MacdStrategy,
    RsiStrategy,
    SmaCrossStrategy,
    Strategy,
    build_strategy,
)
from nepse_trader.models import PriceBar, Signal, SignalAction, SourceName

START = date(2024, 1, 1)


def _bars(closes: list[float | None], symbol: str = "ABC") -> list[PriceBar]:
    """Build chronological PriceBars from a close series (one per business day)."""
    bars: list[PriceBar] = []
    for i, c in enumerate(closes):
        bars.append(
            PriceBar(
                symbol=symbol,
                business_date=START + timedelta(days=i),
                close=c,
                source=SourceName.MANUAL,
            )
        )
    return bars


def _by_date(signals: list[Signal]) -> dict[date, Signal]:
    return {s.business_date: s for s in signals}


def _assert_well_formed(signals: list[Signal]) -> None:
    for s in signals:
        assert 0.0 <= s.strength <= 1.0
        assert all(isinstance(v, float) for v in s.indicators.values())
        assert s.action in (SignalAction.BUY, SignalAction.SELL, SignalAction.HOLD)


# ---------------------------------------------------------------------------
# SMA cross
# ---------------------------------------------------------------------------


def test_sma_cross_buy_then_sell() -> None:
    # Rise sharply (fast crosses above slow) then fall sharply (fast below slow).
    rising = [float(x) for x in range(10, 40)]  # 30 days up
    falling = [float(x) for x in range(40, 10, -1)]  # 30 days down
    bars = _bars(rising + falling)
    strat = SmaCrossStrategy(fast=3, slow=8)
    signals = strat.generate(bars)
    _assert_well_formed(signals)

    actions = [s.action for s in signals]
    assert SignalAction.BUY in actions
    assert SignalAction.SELL in actions
    # BUY must occur before SELL given rise-then-fall.
    buy_idx = next(i for i, a in enumerate(actions) if a is SignalAction.BUY)
    sell_idx = next(i for i, a in enumerate(actions) if a is SignalAction.SELL)
    assert buy_idx < sell_idx
    # Exactly one of each crossover for this clean monotone path.
    assert actions.count(SignalAction.BUY) == 1
    assert actions.count(SignalAction.SELL) == 1
    # Everything else is HOLD.
    assert actions.count(SignalAction.HOLD) == len(actions) - 2
    # Indicators populated on emitted days.
    for s in signals:
        assert "sma_fast" in s.indicators
        assert "sma_slow" in s.indicators


def test_sma_cross_skips_none_close_and_carries_forward() -> None:
    closes: list[float | None] = [float(x) for x in range(10, 25)]
    closes.insert(5, None)  # a gap day
    bars = _bars(closes)
    strat = SmaCrossStrategy(fast=2, slow=4)
    signals = strat.generate(bars)
    emitted_dates = {s.business_date for s in signals}
    gap_date = bars[5].business_date
    assert gap_date not in emitted_dates  # no signal on the None-close day


# ---------------------------------------------------------------------------
# RSI
# ---------------------------------------------------------------------------


def test_rsi_buy_on_oversold_exit_and_sell_on_overbought_exit() -> None:
    # Drop hard into oversold, recover (cross up through 30 -> BUY),
    # then climb hard into overbought and drop (cross down through 70 -> SELL).
    down = [100.0 - 3 * i for i in range(15)]  # push RSI low
    up = [down[-1] + 3 * i for i in range(1, 30)]  # recover and overshoot high
    back = [up[-1] - 3 * i for i in range(1, 15)]  # come back down
    bars = _bars(down + up + back)
    strat = RsiStrategy(period=14, oversold=30, overbought=70)
    signals = strat.generate(bars)
    _assert_well_formed(signals)
    actions = [s.action for s in signals]
    assert SignalAction.BUY in actions
    assert SignalAction.SELL in actions
    buy_idx = next(i for i, a in enumerate(actions) if a is SignalAction.BUY)
    sell_idx = next(i for i, a in enumerate(actions) if a is SignalAction.SELL)
    assert buy_idx < sell_idx
    for s in signals:
        assert "rsi" in s.indicators
        assert 0.0 <= s.indicators["rsi"] <= 100.0


# ---------------------------------------------------------------------------
# MACD
# ---------------------------------------------------------------------------


def test_macd_buy_then_sell() -> None:
    rising = [float(x) for x in range(20, 70)]
    falling = [float(x) for x in range(70, 20, -1)]
    bars = _bars(rising + falling)
    strat = MacdStrategy(fast=3, slow=6, signal=3)
    signals = strat.generate(bars)
    _assert_well_formed(signals)
    actions = [s.action for s in signals]
    assert SignalAction.BUY in actions
    assert SignalAction.SELL in actions
    buy_idx = next(i for i, a in enumerate(actions) if a is SignalAction.BUY)
    sell_idx = next(i for i, a in enumerate(actions) if a is SignalAction.SELL)
    assert buy_idx < sell_idx
    for s in signals:
        for key in ("macd", "signal", "hist"):
            assert key in s.indicators


# ---------------------------------------------------------------------------
# Bollinger
# ---------------------------------------------------------------------------


def test_bollinger_buy_below_lower_sell_above_upper() -> None:
    # Flat baseline to build a tight band, then a sharp dip (below lower -> BUY),
    # recovery into the band, then a sharp spike (above upper -> SELL).
    flat = [100.0] * 25
    dip = [80.0]  # well below lower band
    recover = [100.0] * 5
    spike = [120.0]  # well above upper band
    tail = [100.0] * 5
    bars = _bars(flat + dip + recover + spike + tail)
    strat = BollingerStrategy(period=20, num_std=2.0)
    signals = strat.generate(bars)
    _assert_well_formed(signals)
    by_date = _by_date(signals)

    dip_date = bars[25].business_date
    spike_date = bars[31].business_date
    assert by_date[dip_date].action is SignalAction.BUY
    assert by_date[spike_date].action is SignalAction.SELL
    for s in signals:
        for key in ("lower", "middle", "upper", "close"):
            assert key in s.indicators


# ---------------------------------------------------------------------------
# Composite voting (stub sub-strategies)
# ---------------------------------------------------------------------------


class _StubStrategy(Strategy):
    """Emits a fixed action on every bar's date."""

    def __init__(self, name: str, action: SignalAction) -> None:
        self.name = name
        self._action = action

    def generate(self, bars: list[PriceBar]) -> list[Signal]:
        return [self._emit(b, self._action, 0.5, "stub", {"x": 1.0}) for b in bars]


def test_composite_majority_buy() -> None:
    bars = _bars([float(x) for x in range(10, 20)])
    subs = [
        _StubStrategy("a", SignalAction.BUY),
        _StubStrategy("b", SignalAction.BUY),
        _StubStrategy("c", SignalAction.SELL),
    ]
    comp = CompositeStrategy(subs, buy_threshold=0.5, sell_threshold=0.5)
    signals = comp.generate(bars)
    _assert_well_formed(signals)
    # net = (2 - 1)/3 = 0.333 < 0.5 -> HOLD
    assert all(s.action is SignalAction.HOLD for s in signals)


def test_composite_unanimous_buy_and_sell() -> None:
    bars = _bars([float(x) for x in range(10, 20)])
    buy_comp = CompositeStrategy(
        [_StubStrategy("a", SignalAction.BUY), _StubStrategy("b", SignalAction.BUY)]
    )
    sell_comp = CompositeStrategy(
        [_StubStrategy("a", SignalAction.SELL), _StubStrategy("b", SignalAction.SELL)]
    )
    buy_sigs = buy_comp.generate(bars)
    sell_sigs = sell_comp.generate(bars)
    assert all(s.action is SignalAction.BUY for s in buy_sigs)
    assert all(abs(s.strength - 1.0) < 1e-9 for s in buy_sigs)
    assert all(s.action is SignalAction.SELL for s in sell_sigs)
    # Reason lists contributors.
    assert "BUY:a,b" in buy_sigs[0].reason
    assert "SELL:a,b" in sell_sigs[0].reason


def test_composite_aligns_by_business_date() -> None:
    # Sub-strategies that only emit on some dates still align correctly.
    bars = _bars([100.0, 101.0, 102.0, 103.0])

    class _SparseStub(Strategy):
        def __init__(self) -> None:
            self.name = "sparse"

        def generate(self, b: list[PriceBar]) -> list[Signal]:
            # Only emit a BUY on the last bar.
            return [self._emit(b[-1], SignalAction.BUY, 0.4, "", {"x": 1.0})]

    comp = CompositeStrategy([_SparseStub()])
    signals = comp.generate(bars)
    by_date = _by_date(signals)
    # Last date: 1 BUY out of 1 -> net 1.0 -> BUY.
    assert by_date[bars[-1].business_date].action is SignalAction.BUY
    # Earlier dates: no votes -> HOLD.
    assert by_date[bars[0].business_date].action is SignalAction.HOLD


def test_composite_requires_substrategies() -> None:
    with pytest.raises(ValueError):
        CompositeStrategy([])


# ---------------------------------------------------------------------------
# Registry / build_strategy
# ---------------------------------------------------------------------------


def test_build_strategy_known() -> None:
    strat = build_strategy("sma_cross", fast=5, slow=10)
    assert isinstance(strat, SmaCrossStrategy)
    assert strat.fast == 5
    assert strat.slow == 10


def test_build_strategy_unknown_raises() -> None:
    with pytest.raises(ValueError):
        build_strategy("does_not_exist")


def test_registry_complete() -> None:
    assert set(STRATEGIES) == {"sma_cross", "rsi", "macd", "bollinger"}
    for name in STRATEGIES:
        assert isinstance(build_strategy(name), Strategy)


def test_latest_signal_is_last_day() -> None:
    bars = _bars([float(x) for x in range(10, 40)])
    strat = SmaCrossStrategy(fast=3, slow=8)
    sig = strat.latest_signal(bars)
    assert sig is not None
    assert sig.business_date == bars[-1].business_date


def test_latest_signal_none_when_insufficient() -> None:
    bars = _bars([100.0, 101.0])  # too short for slow SMA
    strat = SmaCrossStrategy(fast=3, slow=8)
    assert strat.latest_signal(bars) is None
