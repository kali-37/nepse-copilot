"""Tests for cross-source reconciliation."""

from __future__ import annotations

from datetime import date

from nepse_trader.ingest.reconcile import reconcile_bars
from nepse_trader.models import PriceBar, SourceName

D = date(2026, 6, 9)


def _bar(source, close, **kw):
    return PriceBar(symbol="NABIL", business_date=D, close=close, source=source, **kw)


def test_full_agreement_high_confidence():
    bars = [
        _bar(SourceName.SHARESANSAR, 500.0),
        _bar(SourceName.MEROLAGANI, 500.5),  # within 0.5% tol
        _bar(SourceName.CHUKUL, 500.2),
    ]
    [r] = reconcile_bars(bars, tolerance=0.005)
    assert r.confidence == 1.0
    assert not r.disputed_fields
    assert r.is_trustworthy
    assert 500.0 <= r.close <= 500.5
    assert len(r.sources_agreeing) == 3


def test_outlier_flags_dispute_and_lowers_confidence():
    bars = [
        _bar(SourceName.SHARESANSAR, 500.0),
        _bar(SourceName.MEROLAGANI, 500.1),
        _bar(SourceName.CHUKUL, 650.0),  # outlier
    ]
    [r] = reconcile_bars(bars, tolerance=0.005)
    assert "close" in r.disputed_fields
    assert r.confidence == round(2 / 3, 4)
    assert r.close < 510  # consensus mean of the agreeing pair, not the outlier


def test_single_source_no_dispute_but_low_confidence_share():
    bars = [_bar(SourceName.SHARESANSAR, 500.0)]
    [r] = reconcile_bars(bars)
    assert r.close == 500.0
    assert r.sources_present == [SourceName.SHARESANSAR]
    assert r.confidence == 1.0  # the only source trivially agrees with itself


def test_groups_by_symbol_and_date():
    bars = [
        PriceBar(symbol="A", business_date=D, close=10, source=SourceName.SHARESANSAR),
        PriceBar(symbol="B", business_date=D, close=20, source=SourceName.SHARESANSAR),
    ]
    out = reconcile_bars(bars)
    assert {r.symbol for r in out} == {"A", "B"}
