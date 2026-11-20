"""Corpus construction: walk the database, emit documents, write the index.

:mod:`corpus` knows how to describe one thing; :mod:`index` knows how to store
it. This module is the part that decides *what* to describe — which symbols, how
much history, which auxiliary tables — and reports what it wrote.

It is deliberately incremental-friendly: every document id is deterministic, so
re-running over the same day updates rows in place. Running it daily after
reconciliation keeps the corpus current at roughly the cost of the symbols that
changed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

from nepse_trader.analysis.strategies import STRATEGIES
from nepse_trader.rag.corpus import (
    Document,
    breadth_document,
    build_symbol_documents,
    corporate_action_document,
    fundamental_document,
    reconcile_document,
    signal_document,
)
from nepse_trader.rag.index import DocumentIndex

log = logging.getLogger("nepse_trader.rag.build")

# Strategies indexed when the caller names none. These are registry names that
# build_strategy() can instantiate; "composite" is deliberately absent because it
# needs sub-strategy instances and cannot be built from a name alone.
DEFAULT_STRATEGIES = ("sma_cross", "rsi", "macd", "supertrend")


@dataclass
class IndexReport:
    """What an indexing run produced."""

    documents: int = 0
    symbols: int = 0
    per_kind: dict[str, int] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    uses_fts: bool = True

    def as_dict(self) -> dict:
        return {
            "documents": self.documents,
            "symbols": self.symbols,
            "per_kind": self.per_kind,
            "errors": self.errors,
            "uses_fts": self.uses_fts,
        }


def build_corpus(
    pipeline,
    *,
    symbols: list[str] | None = None,
    recent_days: int = 10,
    strategies: list[str] | None = None,
    include_breadth: bool = True,
    include_corporate_actions: bool = True,
    min_bars: int = 2,
    on_progress=None,
) -> IndexReport:
    """Index everything derivable for *symbols* into the document store.

    ``pipeline`` is a :class:`~nepse_trader.pipeline.DailyPipeline` — passed in
    rather than constructed so tests can drive this with a temp DB and callers can
    reuse an open connection.

    Per symbol this writes the last ``recent_days`` price documents, one indicator
    document, one quant document, one data-quality document for the latest date,
    and one signal document per named strategy. Symbols with fewer than
    ``min_bars`` reconciled bars are skipped — indicators on two points are noise.
    """
    index = DocumentIndex(pipeline.storage._conn)
    report = IndexReport(uses_fts=index.uses_fts)
    if not index.uses_fts:
        log.warning("indexing without FTS5; search will use the LIKE fallback")

    symbols = symbols or pipeline.storage.symbols()
    strategies = list(strategies) if strategies is not None else list(DEFAULT_STRATEGIES)
    unknown = [s for s in strategies if s not in STRATEGIES]
    if unknown:
        # Surfaced, not swallowed: a name that can never build would otherwise
        # cost a signal document per symbol with nothing to show for it.
        report.errors["strategies"] = (
            f"unknown strategy name(s) {', '.join(unknown)}; known: {', '.join(sorted(STRATEGIES))}"
        )
        log.warning("skipping unknown strategies: %s", ", ".join(unknown))
        strategies = [s for s in strategies if s in STRATEGIES]
    total = len(symbols)

    batch: list[Document] = []
    strategy_failures: dict[str, str] = {}
    for i, symbol in enumerate(symbols, start=1):
        if on_progress is not None:
            on_progress(i, total, symbol)
        try:
            docs = _documents_for_symbol(
                pipeline,
                symbol,
                recent_days=recent_days,
                strategies=strategies,
                min_bars=min_bars,
                failures=strategy_failures,
            )
        except Exception as exc:  # noqa: BLE001 - one bad symbol must not stop the run
            report.errors[symbol] = str(exc)
            log.warning("indexing %s failed: %s", symbol, exc)
            continue
        if docs:
            report.symbols += 1
            batch.extend(docs)
        if len(batch) >= 500:
            _flush(index, batch, report)

    # A strategy that failed on every symbol is a configuration problem, not
    # noise; report it rather than leaving it in the debug log.
    for name, message in strategy_failures.items():
        report.errors[f"strategy:{name}"] = message

    if include_breadth:
        batch.extend(_breadth_documents(pipeline, report))
    if include_corporate_actions:
        batch.extend(_corporate_action_documents(pipeline, report))
    batch.extend(fundamental_document(data) for data in pipeline.storage.fundamentals().values())

    _flush(index, batch, report)
    report.per_kind = index.kinds()
    return report


def index_documents(storage, documents: list[Document]) -> int:
    """Write pre-built documents (news, web pages) into the index."""
    if not documents:
        return 0
    return DocumentIndex(storage._conn).upsert(documents)


def _flush(index: DocumentIndex, batch: list[Document], report: IndexReport) -> None:
    if not batch:
        return
    report.documents += index.upsert(batch)
    batch.clear()


def _documents_for_symbol(
    pipeline,
    symbol: str,
    *,
    recent_days: int,
    strategies: list[str],
    min_bars: int,
    failures: dict[str, str] | None = None,
) -> list[Document]:
    bars = pipeline.reconciled_bars(symbol)
    if len(bars) < min_bars:
        return []

    docs = build_symbol_documents(
        symbol,
        bars,
        recent_days=recent_days,
        periods_per_year=_periods(pipeline),
    )

    # Data quality for the most recent date only — that is the one a decision
    # today depends on.
    latest = pipeline.storage.reconciled_history(symbol)
    if latest:
        docs.append(reconcile_document(latest[-1]))

    for name in strategies:
        try:
            signals = pipeline.signals_for(symbol, name)
        except Exception as exc:  # noqa: BLE001 - a strategy that can't run is not fatal
            log.debug("strategy %s failed on %s: %s", name, symbol, exc)
            if failures is not None:
                failures.setdefault(name, str(exc))
            continue
        if signals:
            docs.append(signal_document(signals[-1]))
    return docs


def _breadth_documents(pipeline, report: IndexReport) -> list[Document]:
    try:
        latest: date | None = pipeline.storage.latest_reconciled_date()
        if latest is None:
            return []
        doc = breadth_document(pipeline.market_breadth(latest))
        return [doc] if doc else []
    except Exception as exc:  # noqa: BLE001
        report.errors["breadth"] = str(exc)
        return []


def _corporate_action_documents(pipeline, report: IndexReport) -> list[Document]:
    try:
        return [corporate_action_document(a) for a in pipeline.storage.corporate_actions()]
    except Exception as exc:  # noqa: BLE001
        report.errors["corporate_actions"] = str(exc)
        return []


def _periods(pipeline) -> int:
    from nepse_trader.calendar import periods_per_year

    try:
        return periods_per_year()
    except Exception:  # noqa: BLE001 - calendar file trouble shouldn't block indexing
        return 244
