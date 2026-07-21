"""Tests for the quantitative statistics module."""

from __future__ import annotations

import math

from nepse_trader.analysis import quant


def test_returns_exact():
    got = quant.returns([100, 110, 99])
    assert math.isclose(got[0], 0.1, rel_tol=1e-9)
    assert math.isclose(got[1], (99 - 110) / 110, rel_tol=1e-9)


def test_returns_handles_zero_prev():
    assert quant.returns([0, 5]) == [0.0]


def test_mean_and_stdev():
    assert quant.mean([1, 2, 3]) == 2.0
    # sample stdev of [1,2,3] = 1.0
    assert math.isclose(quant.stdev([1, 2, 3]), 1.0, rel_tol=1e-9)
    assert quant.stdev([5]) is None  # too short for sample sd


def test_max_drawdown_exact():
    # peak 110 -> trough 99 = 11/110 = 10.0%
    assert math.isclose(quant.max_drawdown([100, 110, 99]), 11 / 110 * 100, rel_tol=1e-9)


def test_max_drawdown_monotonic_is_zero():
    assert quant.max_drawdown([1, 2, 3, 4]) == 0.0


def test_quantile():
    xs = [1, 2, 3, 4, 5]
    assert quant.quantile(xs, 0.0) == 1
    assert quant.quantile(xs, 1.0) == 5
    assert quant.quantile(xs, 0.5) == 3
    assert math.isclose(quant.quantile(xs, 0.25), 2.0, rel_tol=1e-9)


def test_value_at_risk():
    rets = [-0.10, -0.05, 0.0, 0.05, 0.10]
    # quantile(0.05) = -0.10*0.8 + -0.05*0.2 = -0.09 -> VaR 9%
    assert math.isclose(quant.value_at_risk(rets, 0.95), 9.0, rel_tol=1e-9)


def test_value_at_risk_no_loss_is_zero():
    assert quant.value_at_risk([0.01, 0.02, 0.03], 0.95) == 0.0


def test_correlation_perfect_and_inverse():
    a = [1.0, 2.0, 3.0]
    assert math.isclose(quant.correlation(a, [2.0, 4.0, 6.0]), 1.0, rel_tol=1e-9)
    assert math.isclose(quant.correlation(a, [6.0, 4.0, 2.0]), -1.0, rel_tol=1e-9)


def test_beta_scales_with_market():
    market = [0.01, 0.02, -0.01, 0.03]
    asset = [2 * m for m in market]
    assert math.isclose(quant.beta(asset, market), 2.0, rel_tol=1e-9)
    assert math.isclose(quant.beta(market, market), 1.0, rel_tol=1e-9)


def test_sharpe_constant_returns_is_none():
    # zero variance -> undefined Sharpe
    closes = [100.0, 110.0, 121.0]  # constant +10% each step
    rets = quant.returns(closes)
    assert quant.sharpe(rets) is None


def test_sharpe_positive_for_uptrend_with_variation():
    closes = [100, 102, 101, 105, 104, 110, 109, 116, 115, 123]
    rets = quant.returns(closes)
    s = quant.sharpe(rets)
    assert s is not None and s > 0


def test_skewness_symmetric_near_zero():
    rets = [-0.02, -0.01, 0.0, 0.01, 0.02]
    assert abs(quant.skewness(rets)) < 1e-9


def test_summary_stats_short_series():
    s = quant.summary_stats([100.0])
    assert s.n == 1
    assert s.total_return_pct is None
    assert s.sharpe is None


def test_summary_stats_full_series_populated():
    closes = [100, 102, 101, 105, 104, 110, 109, 116, 115, 123, 120, 128]
    s = quant.summary_stats(closes)
    d = s.as_dict()
    assert d["n"] == len(closes)
    assert d["last_close"] == 128
    for key in ("total_return_pct", "annualized_vol_pct", "max_drawdown_pct", "var_95_pct"):
        assert d[key] is not None
    assert d["max_drawdown_pct"] >= 0.0
