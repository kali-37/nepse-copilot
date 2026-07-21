"""Tests for pure technical indicators."""

from __future__ import annotations

import math

from nepse_trader.analysis import indicators as ind


def test_sma_basic():
    assert ind.sma([1, 2, 3, 4, 5], 3) == [None, None, 2.0, 3.0, 4.0]


def test_sma_too_short():
    assert ind.sma([1, 2], 5) == [None, None]


def test_ema_seeded_with_sma():
    # period=3 -> k=0.5; seed = mean(1,2,3)=2.0; then 0.5*4+0.5*2=3.0; 0.5*5+0.5*3=4.0
    assert ind.ema([1, 2, 3, 4, 5], 3) == [None, None, 2.0, 3.0, 4.0]


def test_rsi_all_gains_is_100():
    series = list(range(1, 20))
    rsi = ind.rsi(series, 14)
    assert rsi[:14] == [None] * 14
    assert rsi[14] == 100.0
    assert ind.latest(rsi) == 100.0


def test_rsi_all_losses_is_0():
    series = list(range(20, 1, -1))
    rsi = ind.rsi(series, 14)
    assert rsi[14] == 0.0


def test_rsi_bounds():
    series = [10, 11, 10.5, 12, 11.8, 13, 12.5, 14, 13, 15, 14, 16, 15, 17, 16, 18]
    for v in ind.rsi(series, 14):
        if v is not None:
            assert 0.0 <= v <= 100.0


def test_macd_returns_three_aligned_series():
    series = [float(x) for x in range(1, 60)]
    macd_line, signal_line, hist = ind.macd(series)
    assert len(macd_line) == len(signal_line) == len(hist) == len(series)
    # Steadily rising series -> positive MACD once defined.
    assert ind.latest(macd_line) is not None
    assert ind.latest(macd_line) > 0


def test_bollinger_constant_series_has_zero_width():
    series = [100.0] * 25
    lower, middle, upper = ind.bollinger_bands(series, 20, 2.0)
    assert middle[-1] == 100.0
    assert lower[-1] == 100.0 and upper[-1] == 100.0


def test_bollinger_width_positive_on_variation():
    series = [
        100,
        102,
        98,
        104,
        96,
        105,
        95,
        106,
        94,
        107,
        93,
        108,
        92,
        109,
        91,
        110,
        90,
        111,
        89,
        112,
        88,
    ]
    lower, middle, upper = ind.bollinger_bands(series, 20, 2.0)
    assert upper[-1] > middle[-1] > lower[-1]


def test_atr_positive():
    highs = [float(x) + 1 for x in range(1, 30)]
    lows = [float(x) - 1 for x in range(1, 30)]
    closes = [float(x) for x in range(1, 30)]
    a = ind.atr(highs, lows, closes, 14)
    assert ind.latest(a) is not None
    assert ind.latest(a) > 0


def test_latest_none_when_all_none():
    assert ind.latest([None, None]) is None


def test_ema_matches_manual_for_known_input():
    series = [22.0, 24.0, 23.0, 26.0, 28.0]
    e = ind.ema(series, 2)
    # k = 2/3; seed at index1 = mean(22,24)=23
    assert e[0] is None
    assert math.isclose(e[1], 23.0, rel_tol=1e-9)


def test_supertrend_basic():
    highs = [10.0, 11.0, 12.0, 11.5, 12.5, 13.0]
    lows = [9.0, 9.5, 10.0, 10.5, 11.0, 11.5]
    closes = [9.5, 10.5, 11.5, 11.0, 12.0, 12.5]
    band, direction = ind.supertrend(highs, lows, closes, period=3, multiplier=2.0)
    assert len(band) == 6
    assert len(direction) == 6
    assert band[0] is None
    assert band[1] is None
    assert band[2] is None
    # After warmup, direction should be defined.
    assert direction[3] in (+1, -1)


def test_tenkan_sen():
    highs = [10.0, 12.0, 11.0, 14.0, 13.0]
    lows = [8.0, 9.0, 10.0, 11.0, 12.0]
    ts = ind.tenkan_sen(highs, lows, 3)
    assert ts[:2] == [None, None]
    # Over indices 0..2: max high=12, min low=8 → (12+8)/2 = 10
    assert ts[2] == 10.0
    # Over indices 1..3: max high=14, min low=9 → (14+9)/2 = 11.5
    assert ts[3] == 11.5


def test_kijun_sen_same_as_tenkan():
    highs = [10.0, 12.0, 11.0, 14.0, 13.0]
    lows = [8.0, 9.0, 10.0, 11.0, 12.0]
    ks = ind.kijun_sen(highs, lows, 3)
    assert ks[2] == 10.0


def test_donchian_channel():
    highs = [10.0, 12.0, 11.0, 14.0, 13.0]
    lows = [8.0, 9.0, 10.0, 11.0, 12.0]
    upper, middle, lower = ind.donchian_channel(highs, lows, 3)
    assert upper[:2] == [None, None]
    # Over indices 0..2: max high=12, min low=8
    assert upper[2] == 12.0
    assert lower[2] == 8.0
    assert middle[2] == 10.0
