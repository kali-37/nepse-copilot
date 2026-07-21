"""Tests for the backtest screening leaderboard."""

from __future__ import annotations

import math
from datetime import date, timedelta

import pytest

from nepse_trader.analysis.screen import ScreenRow, best_per_symbol, screen
from nepse_trader.models import PriceBar, SourceName

START = date(2024, 1, 1)


def _bars(symbol: str, closes: list[float]) -> list[PriceBar]:
    return [
        PriceBar(
            symbol=symbol,
            business_date=START + timedelta(days=i),
            open=c,
            high=c,
            low=c,
            close=c,
            source=SourceName.MANUAL,
        )
        for i, c in enumerate(closes)
    ]


def _hump(n: int = 90) -> list[float]:
    return [500 + 80 * math.sin(i / n * math.pi) for i in range(n)]


def _store():
    data = {"AAA": _bars("AAA", _hump()), "BBB": _bars("BBB", _hump())}
    return lambda sym: data.get(sym, [])


def test_screen_runs_all_pairs_and_ranks():
    get_bars = _store()
    rows = screen(get_bars, ["AAA", "BBB"], ["sma_cross", "rsi", "macd", "bollinger"], min_bars=60)
    # 2 symbols x 4 strategies = 8 rows.
    assert len(rows) == 8
    assert all(isinstance(r, ScreenRow) for r in rows)
    sharpes = [r.sharpe for r in rows]
    assert sharpes == sorted(sharpes, reverse=True)  # ranked best-first by sharpe


def test_screen_skips_short_history():
    get_bars = lambda s: _bars(s, [100.0, 101.0, 102.0])  # noqa: E731 - tiny fixture
    rows = screen(get_bars, ["AAA"], ["sma_cross"], min_bars=60)
    assert rows == []


def test_screen_rank_by_drawdown_is_ascending():
    rows = screen(
        _store(), ["AAA", "BBB"], ["sma_cross", "macd"], min_bars=60, rank_by="max_drawdown_pct"
    )
    dds = [r.max_drawdown_pct for r in rows]
    assert dds == sorted(dds)  # lower drawdown first


def test_screen_invalid_rank_by_raises():
    with pytest.raises(ValueError):
        screen(_store(), ["AAA"], ["sma_cross"], rank_by="nonsense")


def test_best_per_symbol_collapses():
    rows = screen(_store(), ["AAA", "BBB"], ["sma_cross", "rsi", "macd", "bollinger"], min_bars=60)
    best = best_per_symbol(rows, rank_by="sharpe")
    assert {r.symbol for r in best} == {"AAA", "BBB"}
    assert len(best) == 2
    # Each is the max-sharpe row for that symbol.
    for b in best:
        same = [r for r in rows if r.symbol == b.symbol]
        assert b.sharpe == max(r.sharpe for r in same)
