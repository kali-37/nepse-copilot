"""Tests for the RAG document corpus builders.

Two invariants carry the whole layer and are asserted here directly:

* **Deterministic ids** — the same input must produce the same ``doc_id``, or daily
  re-indexing would duplicate instead of update.
* **Prose bodies** — the numbers must appear as readable text, since Normal mode
  renders these documents straight into a report with no LLM in the loop.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from nepse_trader.models import (
    CorporateAction,
    CorporateActionType,
    FundamentalData,
    PriceBar,
    ReconciledPrice,
    Signal,
    SignalAction,
    SourceName,
)
from nepse_trader.rag.corpus import (
    KIND_CORPORATE_ACTION,
    KIND_INDICATOR,
    KIND_PRICE,
    KIND_QUANT,
    KIND_RECONCILE,
    KIND_REPORT,
    KIND_SIGNAL,
    breadth_document,
    build_symbol_documents,
    corporate_action_document,
    fundamental_document,
    indicator_document,
    iter_documents,
    price_document,
    quant_document,
    reconcile_document,
    signal_document,
)


def _bar(day: int, close: float, symbol: str = "NABIL") -> PriceBar:
    return PriceBar(
        symbol=symbol,
        business_date=date(2026, 1, day),
        open=close - 2,
        high=close + 3,
        low=close - 4,
        close=close,
        previous_close=close - 1,
        volume=1_000 + day,
        turnover=close * (1_000 + day),
        source=SourceName.SHARESANSAR,
    )


def _series(n: int = 60, symbol: str = "NABIL") -> list[PriceBar]:
    """A rising series long enough for SMA50/RSI/MACD/Bollinger to have values."""
    return [
        PriceBar(
            symbol=symbol,
            business_date=date(2026, 1, 1) + timedelta(days=i),
            open=500.0 + i,
            high=505.0 + i,
            low=496.0 + i,
            close=500.0 + i,
            previous_close=499.0 + i,
            volume=1_000 + i,
            turnover=(500.0 + i) * (1_000 + i),
            source=SourceName.SHARESANSAR,
        )
        for i in range(n)
    ]


class TestPriceDocument:
    def test_body_states_close_and_direction(self):
        doc = price_document(_bar(5, 512.0))
        assert "512.00" in doc.body
        assert "up" in doc.body  # close 512 vs previous_close 511
        assert doc.kind == KIND_PRICE
        assert doc.symbol == "NABIL"
        assert doc.business_date == date(2026, 1, 5)

    def test_id_is_deterministic(self):
        assert price_document(_bar(5, 512.0)).doc_id == price_document(_bar(5, 512.0)).doc_id

    def test_id_varies_by_symbol_and_date(self):
        a = price_document(_bar(5, 512.0, "NABIL"))
        b = price_document(_bar(5, 512.0, "ADBL"))
        c = price_document(_bar(6, 512.0, "NABIL"))
        assert len({a.doc_id, b.doc_id, c.doc_id}) == 3

    def test_reconciled_price_adds_confidence(self):
        rp = ReconciledPrice(
            symbol="NABIL",
            business_date=date(2026, 1, 5),
            close=512.0,
            previous_close=511.0,
            sources_present=[SourceName.SHARESANSAR, SourceName.MEROLAGANI],
            sources_agreeing=[SourceName.SHARESANSAR, SourceName.MEROLAGANI],
            confidence=1.0,
        )
        assert "confidence" in price_document(rp).body.lower()

    def test_missing_previous_close_omits_direction(self):
        bar = _bar(5, 512.0)
        bar.previous_close = None
        body = price_document(bar).body
        assert "512.00" in body
        assert " up " not in body and " down " not in body


class TestIndicatorDocument:
    def test_returns_none_on_thin_history(self):
        assert indicator_document("NABIL", [_bar(1, 500.0)]) is None

    def test_names_each_indicator_with_its_reading(self):
        doc = indicator_document("NABIL", _series(60))
        assert doc is not None
        for token in ("SMA20", "SMA50", "RSI(14)", "MACD", "ATR(14)", "Bollinger"):
            assert token in doc.body, f"missing {token}"

    def test_states_interpretation_not_just_numbers(self):
        """A bare number is useless in a report; the reading must be explained."""
        doc = indicator_document("NABIL", _series(60))
        assert doc is not None
        assert "above" in doc.body or "below" in doc.body
        assert any(z in doc.body for z in ("overbought", "oversold", "neutral"))

    def test_dated_to_the_last_bar(self):
        bars = _series(60)
        doc = indicator_document("NABIL", bars)
        assert doc is not None
        assert doc.business_date == bars[-1].business_date
        assert doc.kind == KIND_INDICATOR


class TestQuantDocument:
    def test_returns_none_on_thin_history(self):
        assert quant_document("NABIL", [_bar(1, 500.0)]) is None

    def test_reports_risk_metrics(self):
        doc = quant_document("NABIL", _series(60))
        assert doc is not None
        for token in ("Sharpe", "Sortino", "drawdown", "VaR", "volatility"):
            assert token in doc.body, f"missing {token}"
        assert doc.kind == KIND_QUANT


class TestSignalDocument:
    def test_records_action_strategy_and_conviction(self):
        sig = Signal(
            symbol="NABIL",
            business_date=date(2026, 1, 5),
            strategy="composite",
            action=SignalAction.BUY,
            strength=0.75,
            reason="3 of 4 strategies agree",
            price=512.0,
            indicators={"rsi": 55.0},
        )
        doc = signal_document(sig)
        assert "BUY" in doc.body
        assert "composite" in doc.body
        assert "0.75" in doc.body
        assert "3 of 4 strategies agree" in doc.body
        assert "rsi=55.00" in doc.body
        assert doc.kind == KIND_SIGNAL

    def test_id_includes_strategy_so_strategies_dont_collide(self):
        base = dict(
            symbol="NABIL",
            business_date=date(2026, 1, 5),
            action=SignalAction.BUY,
            strength=0.5,
            price=512.0,
        )
        a = signal_document(Signal(strategy="composite", **base))
        b = signal_document(Signal(strategy="rsi", **base))
        assert a.doc_id != b.doc_id


class TestReconcileDocument:
    def test_states_trust_verdict_plainly(self):
        rp = ReconciledPrice(
            symbol="NABIL",
            business_date=date(2026, 1, 5),
            close=512.0,
            sources_present=[SourceName.SHARESANSAR],
            sources_agreeing=[SourceName.SHARESANSAR],
            confidence=0.4,
            disputed_fields=["close"],
        )
        doc = reconcile_document(rp)
        assert "NOT trustworthy" in doc.body
        assert "close" in doc.body
        assert doc.kind == KIND_RECONCILE

    def test_trustworthy_when_sources_agree(self):
        rp = ReconciledPrice(
            symbol="NABIL",
            business_date=date(2026, 1, 5),
            close=512.0,
            sources_present=[SourceName.SHARESANSAR, SourceName.CHUKUL],
            sources_agreeing=[SourceName.SHARESANSAR, SourceName.CHUKUL],
            confidence=1.0,
        )
        body = reconcile_document(rp).body
        assert "trustworthy" in body
        assert "NOT trustworthy" not in body


class TestFundamentalDocument:
    def test_includes_valuation_ratios(self):
        data = FundamentalData(
            symbol="NABIL",
            company_name="Nabil Bank Limited",
            sector="Commercial Banks",
            market_price=512.0,
            eps=35.2,
            pe_ratio=14.5,
            book_value=280.0,
            pbv=1.83,
            dividend_pct=11.0,
            fetched_at=datetime(2026, 1, 5, 10, 0),
        )
        doc = fundamental_document(data)
        assert "Nabil Bank Limited" in doc.body
        assert "14.50" in doc.body
        assert doc.business_date == date(2026, 1, 5)


class TestCorporateActionDocument:
    def test_explains_the_adjustment_factor(self):
        ca = CorporateAction(
            symbol="NABIL",
            ex_date=date(2026, 1, 5),
            action_type=CorporateActionType.BONUS,
            ratio_numerator=1,
            ratio_denominator=10,
            factor=Decimal("0.909091"),
            source=SourceName.SHARESANSAR,
            notes="10% bonus",
        )
        doc = corporate_action_document(ca)
        assert "bonus" in doc.body.lower()
        assert "0.909091" in doc.body
        assert "10% bonus" in doc.body
        assert doc.kind == KIND_CORPORATE_ACTION


class TestBreadthDocument:
    def test_none_without_a_date(self):
        assert breadth_document({"advancers": 100}) is None

    @pytest.mark.parametrize(
        ("adv", "dec", "expected"),
        [(150, 50, "broadly positive"), (50, 150, "broadly negative"), (100, 100, "mixed")],
    )
    def test_tone_follows_advance_decline(self, adv: int, dec: int, expected: str):
        doc = breadth_document(
            {"business_date": "2026-01-05", "advancers": adv, "decliners": dec, "symbols": 250}
        )
        assert doc is not None
        assert expected in doc.body
        assert doc.kind == KIND_REPORT

    def test_accepts_a_date_object_as_well_as_a_string(self):
        doc = breadth_document({"business_date": date(2026, 1, 5), "advancers": 1, "decliners": 0})
        assert doc is not None
        assert doc.business_date == date(2026, 1, 5)


class TestBuildSymbolDocuments:
    def test_caps_price_documents_at_recent_days(self):
        docs = build_symbol_documents("NABIL", _series(60), recent_days=5)
        prices = [d for d in docs if d.kind == KIND_PRICE]
        assert len(prices) == 5

    def test_includes_indicator_and_quant_documents(self):
        kinds = {d.kind for d in build_symbol_documents("NABIL", _series(60))}
        assert KIND_INDICATOR in kinds
        assert KIND_QUANT in kinds

    def test_empty_history_yields_nothing(self):
        assert build_symbol_documents("NABIL", []) == []

    def test_ids_are_unique_within_a_run(self):
        docs = build_symbol_documents("NABIL", _series(60), recent_days=10)
        ids = [d.doc_id for d in docs]
        assert len(ids) == len(set(ids))

    def test_rerun_produces_identical_ids(self):
        """Daily re-indexing must upsert, not accumulate."""
        first = [d.doc_id for d in build_symbol_documents("NABIL", _series(60))]
        second = [d.doc_id for d in build_symbol_documents("NABIL", _series(60))]
        assert first == second


class TestAsRow:
    def test_row_matches_documents_column_order(self):
        row = price_document(_bar(5, 512.0)).as_row()
        assert len(row) == 9
        assert row[0].startswith("price:NABIL:")
        assert row[1] == KIND_PRICE
        assert row[2] == "NABIL"
        assert row[3] == "2026-01-05"

    def test_dates_serialise_to_iso_strings(self):
        row = price_document(_bar(5, 512.0)).as_row()
        assert isinstance(row[3], str)


def test_iter_documents_drops_nones():
    docs = iter_documents([price_document(_bar(1, 500.0)), None, price_document(_bar(2, 501.0))])
    assert len(docs) == 2
