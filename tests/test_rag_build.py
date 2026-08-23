"""Tests for corpus construction against a real (temp) database.

These drive ``build_corpus`` through a live :class:`DailyPipeline` rather than
mocking it, because the defects this file guards against only appear at that
seam: a strategy name that cannot be built, and a symbol whose reconciled
history is too thin to describe.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from nepse_trader.config import Settings
from nepse_trader.models import PriceBar, SourceName
from nepse_trader.pipeline import DailyPipeline
from nepse_trader.rag.build import DEFAULT_STRATEGIES, build_corpus, index_documents
from nepse_trader.rag.corpus import (
    KIND_INDICATOR,
    KIND_NEWS,
    KIND_PRICE,
    KIND_QUANT,
    KIND_RECONCILE,
    KIND_SIGNAL,
    Document,
)
from nepse_trader.rag.index import DocumentIndex

START = date(2026, 5, 1)


def _bars(symbol: str, n: int, base: float, step: float) -> list[PriceBar]:
    return [
        PriceBar(
            symbol=symbol,
            business_date=START + timedelta(days=i),
            open=base + i * step - 2,
            high=base + i * step + 3,
            low=base + i * step - 4,
            close=base + i * step,
            previous_close=base + i * step - 1,
            volume=10_000 + i,
            turnover=(base + i * step) * (10_000 + i),
            source=SourceName.SHARESANSAR,
        )
        for i in range(n)
    ]


@pytest.fixture
def pipeline(tmp_path: Path) -> DailyPipeline:
    """A pipeline over a temp DB holding two reconciled symbols."""
    settings = Settings(_env_file=None, db_path=tmp_path / "corpus.db", online=False)
    pipe = DailyPipeline(settings=settings)
    pipe.storage.upsert_price_bars([*_bars("NABIL", 70, 500.0, 1.5), *_bars("ADBL", 70, 300.0, -0.8)])
    for i in range(70):
        pipe.reconcile(START + timedelta(days=i))
    return pipe


class TestBuildCorpus:
    def test_writes_documents_for_every_symbol(self, pipeline: DailyPipeline):
        report = build_corpus(pipeline)
        assert report.symbols == 2
        assert report.documents > 0

    def test_covers_each_derived_kind(self, pipeline: DailyPipeline):
        report = build_corpus(pipeline)
        for kind in (KIND_PRICE, KIND_INDICATOR, KIND_QUANT, KIND_RECONCILE, KIND_SIGNAL):
            assert report.per_kind.get(kind), f"no {kind} documents"

    def test_recent_days_caps_price_documents(self, pipeline: DailyPipeline):
        report = build_corpus(pipeline, recent_days=3)
        assert report.per_kind[KIND_PRICE] == 6  # 3 days x 2 symbols

    def test_symbol_filter_narrows_the_run(self, pipeline: DailyPipeline):
        report = build_corpus(pipeline, symbols=["NABIL"])
        assert report.symbols == 1

    def test_rerun_upserts_rather_than_accumulating(self, pipeline: DailyPipeline):
        """Deterministic ids mean daily indexing is idempotent."""
        first = build_corpus(pipeline).per_kind
        second = build_corpus(pipeline).per_kind
        assert first == second

    def test_reports_no_errors_on_the_happy_path(self, pipeline: DailyPipeline):
        assert build_corpus(pipeline).errors == {}

    def test_indexed_documents_are_searchable(self, pipeline: DailyPipeline):
        build_corpus(pipeline)
        index = DocumentIndex(pipeline.storage._conn)  # noqa: SLF001 - same connection
        assert index.search("NABIL overbought RSI")


class TestStrategySelection:
    def test_default_strategies_all_produce_signals(self, pipeline: DailyPipeline):
        """Every default name must be buildable — otherwise the default is broken."""
        report = build_corpus(pipeline)
        assert report.per_kind[KIND_SIGNAL] == len(DEFAULT_STRATEGIES) * 2
        assert report.errors == {}

    def test_unknown_strategy_is_reported_not_swallowed(self, pipeline: DailyPipeline):
        """'composite' needs sub-strategy instances, so it can never build by name."""
        report = build_corpus(pipeline, strategies=["composite"])
        assert "composite" in " ".join(report.errors.values())
        assert report.per_kind.get(KIND_SIGNAL, 0) == 0

    def test_known_strategies_still_run_alongside_an_unknown_one(self, pipeline: DailyPipeline):
        report = build_corpus(pipeline, strategies=["composite", "rsi"])
        assert report.errors
        assert report.per_kind[KIND_SIGNAL] == 2  # rsi on both symbols

    def test_empty_strategy_list_writes_no_signals(self, pipeline: DailyPipeline):
        report = build_corpus(pipeline, strategies=[])
        assert report.per_kind.get(KIND_SIGNAL, 0) == 0
        assert report.errors == {}

    def test_caller_list_is_not_mutated(self, pipeline: DailyPipeline):
        names = ["composite", "rsi"]
        build_corpus(pipeline, strategies=names)
        assert names == ["composite", "rsi"]


class TestThinHistory:
    def test_symbol_below_min_bars_is_skipped(self, tmp_path: Path):
        settings = Settings(_env_file=None, db_path=tmp_path / "thin.db", online=False)
        pipe = DailyPipeline(settings=settings)
        pipe.storage.upsert_price_bars(_bars("TINY", 1, 100.0, 1.0))
        pipe.reconcile(START)
        report = build_corpus(pipe, min_bars=2)
        assert report.symbols == 0
        # Breadth is market-wide, not per-symbol, so it survives; nothing
        # symbol-derived should.
        assert KIND_PRICE not in report.per_kind
        assert KIND_INDICATOR not in report.per_kind

    def test_empty_database_yields_an_empty_report(self, tmp_path: Path):
        settings = Settings(_env_file=None, db_path=tmp_path / "empty.db", online=False)
        report = build_corpus(DailyPipeline(settings=settings))
        assert report.documents == 0
        assert report.symbols == 0

    def test_unreconciled_bars_produce_nothing(self, tmp_path: Path):
        """Indicators run off reconciled history, so ingest alone is not enough."""
        settings = Settings(_env_file=None, db_path=tmp_path / "raw.db", online=False)
        pipe = DailyPipeline(settings=settings)
        pipe.storage.upsert_price_bars(_bars("NABIL", 70, 500.0, 1.5))
        assert build_corpus(pipe).documents == 0


class TestProgressCallback:
    def test_called_once_per_symbol(self, pipeline: DailyPipeline):
        seen: list[str] = []
        build_corpus(pipeline, on_progress=lambda i, total, sym: seen.append(sym))
        assert sorted(seen) == ["ADBL", "NABIL"]


class TestIndexDocuments:
    def test_writes_prebuilt_documents(self, pipeline: DailyPipeline):
        docs = [
            Document(
                doc_id="news:x1",
                kind=KIND_NEWS,
                title="NABIL declares dividend",
                body="NABIL declares an 11% dividend.",
                symbol="NABIL",
                business_date=date(2026, 7, 9),
            )
        ]
        assert index_documents(pipeline.storage, docs) == 1
        index = DocumentIndex(pipeline.storage._conn)  # noqa: SLF001 - same connection
        assert index.search("dividend")[0].document.doc_id == "news:x1"

    def test_empty_list_is_a_no_op(self, pipeline: DailyPipeline):
        assert index_documents(pipeline.storage, []) == 0
