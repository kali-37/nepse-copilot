"""Daily orchestration: ingest -> reconcile -> signals -> report.

This is the glue that the CLI and any scheduler drive. It builds the enabled
source clients, pulls public data into SQLite idempotently, reconciles across
sources into a confidence-scored consensus, and (optionally) derives signals and
a markdown report. Every step is defensive: a failing source is logged and
skipped, never fatal.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from nepse_trader import reporting
from nepse_trader.analysis import quant
from nepse_trader.analysis.costs import CostEngine
from nepse_trader.analysis.screen import ScreenRow, best_per_symbol, screen
from nepse_trader.analysis.strategies import STRATEGIES, Strategy, build_strategy
from nepse_trader.calendar import periods_per_year as _calendar_periods
from nepse_trader.calendar import previous_trading_day
from nepse_trader.config import Settings, SourcesConfig, get_settings, load_sources
from nepse_trader.ingest.base import SourceClient
from nepse_trader.ingest.chukul import ChukulClient
from nepse_trader.ingest.merolagani import MeroLaganiClient
from nepse_trader.ingest.nepse_official import NepseScraperClient
from nepse_trader.ingest.nepsealpha import NepseAlphaClient
from nepse_trader.ingest.policy import IngestPolicy
from nepse_trader.ingest.reconcile import adjust_prices, reconcile_bars
from nepse_trader.ingest.sharesansar import ShareSansarClient
from nepse_trader.models import PriceBar, ReconciledPrice, Signal, SourceName
from nepse_trader.storage import Storage
from nepse_trader.trading.portfolio import PaperPortfolio

log = logging.getLogger("nepse_trader.pipeline")

_CLIENT_FACTORIES = {
    SourceName.SHARESANSAR.value: ShareSansarClient,
    SourceName.MEROLAGANI.value: MeroLaganiClient,
    SourceName.CHUKUL.value: ChukulClient,
    SourceName.NEPSEALPHA.value: NepseAlphaClient,
    SourceName.NEPSE_OFFICIAL.value: NepseScraperClient,
}


def build_clients(
    settings: Settings | None = None,
    sources: SourcesConfig | None = None,
    include_all: bool = False,
) -> list[SourceClient]:
    """Instantiate the source clients to run.

    By default this honours ``settings.enabled_sources`` and each source's
    ``enabled`` flag in sources.yaml. Set ``include_all=True`` (or
    ``NEPSE_ENABLED_SOURCES=all``) to construct EVERY known client regardless of
    those flags — "scrape all sites, keep whatever responds". Sources whose
    endpoints aren't reachable simply return [] and are skipped at reconcile.
    """
    settings = settings or get_settings()
    sources = sources or load_sources()

    want_all = include_all or [s.lower() for s in settings.enabled_sources] == ["all"]
    names = list(_CLIENT_FACTORIES) if want_all else settings.enabled_sources

    clients: list[SourceClient] = []
    for name in names:
        factory = _CLIENT_FACTORIES.get(name)
        if factory is None:
            log.warning("no client factory for source %r; skipping", name)
            continue
        spec = sources.get(name)
        if not want_all and spec is not None and not spec.enabled:
            log.info("source %r disabled in sources.yaml; skipping", name)
            continue
        try:
            clients.append(_construct(factory, spec))
        except Exception as exc:  # noqa: BLE001 - never let one source break setup
            log.warning("failed to construct client %r: %s", name, exc)
    return clients


def _construct(factory, spec):
    # NepseScraperClient takes no constructor args; others accept source_spec.
    if factory is NepseScraperClient:
        return factory()
    return factory(source_spec=spec)


@dataclass
class IngestReport:
    business_date: date | None
    per_source: dict[str, int] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    skipped: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    total_bars: int = 0
    total_indices: int = 0
    business_dates: set[date] = field(default_factory=set)

    def as_dict(self) -> dict:
        return {
            "business_date": self.business_date.isoformat() if self.business_date else None,
            "business_dates": sorted(d.isoformat() for d in self.business_dates),
            "per_source": self.per_source,
            "errors": self.errors,
            "skipped": self.skipped,
            "warnings": self.warnings,
            "total_bars": self.total_bars,
            "total_indices": self.total_indices,
        }


class DailyPipeline:
    def __init__(
        self,
        settings: Settings | None = None,
        storage: Storage | None = None,
        clients: list[SourceClient] | None = None,
        cost_engine: CostEngine | None = None,
        include_all_sources: bool = False,
    ) -> None:
        self.settings = settings or get_settings()
        self.storage = storage or Storage(self.settings.db_path)
        self.clients = (
            clients
            if clients is not None
            else build_clients(self.settings, include_all=include_all_sources)
        )
        self.cost_engine = cost_engine or CostEngine()
        self.ingest_policy = IngestPolicy(self.storage, self.settings)

    # ------------------------------------------------------------- ingestion
    def ingest(self, business_date: date | None = None, *, force: bool = False) -> IngestReport:
        report = IngestReport(business_date=business_date)
        for client in self.clients:
            sname = client.name.value
            reason = self.ingest_policy.skip_reason(sname, business_date, force=force)
            if reason:
                report.skipped[sname] = reason
                continue
            # Isolate prices and indices independently: a failure fetching one
            # data type must NOT discard a successful fetch of the other.
            bars = self._safe_fetch(client.fetch_prices, business_date, sname, "prices", report)
            indices = self._safe_fetch(
                client.fetch_indices, business_date, sname, "indices", report
            )
            report.business_dates.update(bar.business_date for bar in bars)
            n = self.storage.upsert_price_bars(bars)
            ni = self.storage.upsert_index_values(indices)
            report.per_source[sname] = n
            report.total_bars += n
            report.total_indices += ni
            report.warnings.extend(self.ingest_policy.record(sname, bars, business_date))
        return report

    async def async_ingest(self, business_date: date | None = None, *, force: bool = False) -> IngestReport:
        """Async variant: fetches from all sources concurrently."""
        report = IngestReport(business_date=business_date)
        async def _fetch_one(client):
            sname = client.name.value
            reason = self.ingest_policy.skip_reason(sname, business_date, force=force)
            if reason:
                report.skipped[sname] = reason
                return
            bars = await self._safe_async_fetch(
                client.async_fetch_prices, business_date, sname, "prices", report
            )
            indices = await self._safe_async_fetch(
                client.async_fetch_indices, business_date, sname, "indices", report
            )
            report.business_dates.update(bar.business_date for bar in bars)
            n = self.storage.upsert_price_bars(bars)
            ni = self.storage.upsert_index_values(indices)
            report.per_source[sname] = report.per_source.get(sname, 0) + n
            report.total_bars += n
            report.total_indices += ni
            report.warnings.extend(self.ingest_policy.record(sname, bars, business_date))

        await asyncio.gather(*[_fetch_one(c) for c in self.clients])
        return report

    async def _safe_async_fetch(self, fn, business_date, sname, kind, report) -> list:
        try:
            result = await fn(business_date)
            return result or []
        except Exception as exc:
            report.errors[f"{sname}:{kind}"] = str(exc)
            self.storage.log_ingest(sname, kind, business_date, 0, "error", str(exc))
            log.warning("ingest %s failed for %s: %s", kind, sname, exc)
            return []

    def _safe_fetch(self, fn, business_date, sname, kind, report) -> list:
        """Call a client fetch method, isolating its failure to that data type."""
        try:
            return fn(business_date) or []
        except Exception as exc:  # noqa: BLE001 - one data type failing is not fatal
            report.errors[f"{sname}:{kind}"] = str(exc)
            self.storage.log_ingest(sname, kind, business_date, 0, "error", str(exc))
            log.warning("ingest %s failed for %s: %s", kind, sname, exc)
            return []

    # --------------------------------------------------------- reconciliation
    def reconcile(self, business_date: date) -> list[ReconciledPrice]:
        bars = self.storage.bars_for_date(business_date)
        reconciled = reconcile_bars(bars, tolerance=self.settings.price_agreement_tolerance)
        self.storage.upsert_reconciled(reconciled)
        self.refresh_adjustments({p.symbol for p in reconciled})
        return self.storage.reconciled_history_for_date(business_date)

    def refresh_adjustments(self, symbols: set[str] | None = None) -> int:
        """Recompute from raw closes so late/corrected events never compound."""
        count = 0
        actions = self.storage.corporate_actions()
        for symbol in sorted(symbols if symbols is not None else self.storage.symbols()):
            prices = self.storage.reconciled_history(symbol)
            adjust_prices(prices, [ca for ca in actions if ca.symbol == symbol])
            count += self.storage.upsert_reconciled(prices)
        return count

    # ---------------------------------------------------------------- signals
    def reconciled_bars(self, symbol: str, *, adjusted: bool = True, as_of: date | None = None) -> list[PriceBar]:
        """Reconciled history for a symbol as PriceBars (for indicators)."""
        out: list[PriceBar] = []
        actions = self.storage.corporate_actions(symbol) if adjusted else []
        history = self.storage.reconciled_history(symbol)
        if as_of is not None:
            history = [r for r in history if r.business_date <= as_of]
            actions = [action for action in actions if action.ex_date <= as_of]
            if adjusted:
                adjust_prices(history, actions)
        prior: ReconciledPrice | None = None
        for r in history:
            factor = r.adjusted_close / r.close if adjusted and r.adjusted_close is not None and r.close else 1.0
            def scaled(value: float | None, multiplier: float = factor) -> float | None:
                return value * multiplier if value is not None else None
            previous_close = scaled(r.previous_close)
            if previous_close is not None:
                # The previous close predates today's ex-date, whereas today's
                # OHLC are already quoted in the new share units.
                for action in actions:
                    if action.ex_date == r.business_date:
                        previous_close *= float(action.factor)
                if (adjusted and prior is not None and prior.close == r.previous_close
                        and prior.business_date == previous_trading_day(r.business_date - timedelta(days=1))):
                    previous_close = prior.adjusted_close if prior.adjusted_close is not None else prior.close
            out.append(
                PriceBar(
                    symbol=r.symbol,
                    business_date=r.business_date,
                    open=scaled(r.open),
                    high=scaled(r.high),
                    low=scaled(r.low),
                    close=scaled(r.close),
                    previous_close=previous_close,
                    volume=r.volume,
                    turnover=r.turnover,
                    source=SourceName.MANUAL,
                )
            )
            if r.close is not None:
                prior = r
        return out

    def signals_for(
        self, symbol: str, strategy: str | Strategy = "sma_cross", **kwargs
    ) -> list[Signal]:
        strat = strategy if isinstance(strategy, Strategy) else build_strategy(strategy, **kwargs)
        bars = self.reconciled_bars(symbol)
        signals = strat.generate(bars)
        self.storage.upsert_signals(signals)
        return signals

    def latest_signals(
        self, symbols: list[str] | None = None, strategy: str = "sma_cross"
    ) -> list[Signal]:
        symbols = symbols or self.storage.symbols()
        out: list[Signal] = []
        for sym in symbols:
            sigs = self.signals_for(sym, strategy)
            if sigs:
                out.append(sigs[-1])
        return out

    # --------------------------------------------------------------- portfolio
    def replay_portfolio(self, initial_cash: float = 100_000.0) -> PaperPortfolio:
        """Rebuild the paper portfolio by replaying stored trades (no re-persist)."""
        pf = PaperPortfolio(initial_cash=initial_cash, cost_engine=self.cost_engine, storage=None)
        for t in self.storage.paper_trades():
            if t.side.value == "BUY":
                pf.buy(t.symbol, t.price, t.quantity, t.business_date, t.strategy)
            else:
                pf.sell(t.symbol, t.price, t.quantity, t.business_date, t.strategy)
        return pf

    # ----------------------------------------------------------- analytics
    def market_breadth(self, business_date: date) -> dict:
        """Advancers/decliners/turnover/reconcile-quality for a date."""
        rows = self.storage.reconciled_history_for_date(business_date)
        adv = dec = unch = 0
        turnover = 0.0
        confidences: list[float] = []
        disputed = 0
        for r in rows:
            ch = self._reconciled_change_pct(r)
            if ch is None:
                unch += 1
            elif ch > 0:
                adv += 1
            elif ch < 0:
                dec += 1
            else:
                unch += 1
            if r.turnover:
                turnover += r.turnover
            confidences.append(r.confidence)
            if not r.is_trustworthy:
                disputed += 1
        return {
            "business_date": business_date.isoformat(),
            "symbols": len(rows),
            "advancers": adv,
            "decliners": dec,
            "unchanged": unch,
            "total_turnover": round(turnover, 2),
            "avg_confidence": round(sum(confidences) / len(confidences), 4)
            if confidences
            else None,
            "disputed": disputed,
        }

    @staticmethod
    def _reconciled_change_pct(r: ReconciledPrice) -> float | None:
        if r.close is None or not r.previous_close:
            return None
        return (r.close - r.previous_close) / r.previous_close * 100.0

    def top_movers(self, business_date: date, top: int = 5) -> tuple[list[dict], list[dict]]:
        """Top gainers and losers for a date, by reconciled change %.

        Split by the sign of the change, not by slicing the ranked list from
        both ends: with fewer symbols than *top* the two slices overlap, and
        the overlap has to be resolved by dropping one side — which reported a
        symbol that rose 2% as a top loser. A gainer is a symbol that went up.
        Flat symbols belong to neither list.
        """
        rows = []
        for r in self.storage.reconciled_history_for_date(business_date):
            ch = self._reconciled_change_pct(r)
            if ch is None:
                continue
            rows.append({"symbol": r.symbol, "close": r.close, "change_percent": round(ch, 2)})
        gainers = sorted(
            (d for d in rows if d["change_percent"] > 0),
            key=lambda d: d["change_percent"],
            reverse=True,
        )[:top]
        losers = sorted(
            (d for d in rows if d["change_percent"] < 0),
            key=lambda d: d["change_percent"],
        )[:top]
        return gainers, losers

    def quant_stats(self, symbols: list[str], periods_per_year: int | None = None) -> list[dict]:
        periods_per_year = periods_per_year or _calendar_periods()
        """Per-symbol quantitative summary over reconciled close history."""
        out: list[dict] = []
        for sym in symbols:
            closes = [b.close for b in self.reconciled_bars(sym) if b.close is not None]
            stats = quant.summary_stats(closes, periods_per_year=periods_per_year)
            row = {"symbol": sym}
            row.update(stats.as_dict())
            out.append(row)
        return out

    def screen_strategies(
        self,
        symbols: list[str] | None = None,
        strategy_names: list[str] | None = None,
        *,
        cash: float = 100_000.0,
        min_bars: int = 60,
        rank_by: str = "sharpe",
        on_progress: Callable[[int, int, str], Any] | None = None,
        max_pe: float | None = None,
        max_pbv: float | None = None,
        min_eps: float | None = None,
        sector: str | None = None,
    ) -> list[ScreenRow]:
        """Backtest the strategy panel across symbols; return a ranked leaderboard."""
        from nepse_trader.analysis.fundamentals import filter_symbols

        symbols = filter_symbols(symbols if symbols is not None else self.storage.symbols(),
            self.storage.fundamentals(as_of=self.storage.latest_reconciled_date()),
            max_pe=max_pe, max_pbv=max_pbv, min_eps=min_eps, sector=sector)
        return screen(
            self.reconciled_bars,
            symbols,
            strategy_names or list(STRATEGIES),
            cash=cash,
            min_bars=min_bars,
            cost_engine=self.cost_engine,
            rank_by=rank_by,
            on_progress=on_progress,
        )

    # --------------------------------------------------------------- report
    def daily_report(
        self,
        business_date: date,
        *,
        strategies: list[str] | None = None,
        top: int = 25,
        rank_by: str = "sharpe",
        min_bars: int = 60,
        paper_cash: float = 100_000.0,
        on_progress: Callable[[int, int, str], Any] | None = None,
    ) -> tuple[dict[str, str], dict]:
        """Assemble the full once-a-day report. Returns (sections, summary).

        sections: title -> markdown, ready for reporting.write_markdown_report.
        summary: machine-readable headline numbers for logging/alerting.

        ``on_progress`` is forwarded to the screening leg, which is where nearly
        all the wall-clock goes; callers that want a progress bar over a daily
        run pass it here.
        """
        strategies = strategies or list(STRATEGIES)
        breadth = self.market_breadth(business_date)
        gainers, losers = self.top_movers(business_date, top=5)

        all_symbols = self.storage.symbols()
        tracked = all_symbols[:top]

        # Multi-strategy latest signals (actionable first).
        signals: list[Signal] = []
        for strat in strategies:
            signals.extend(self.latest_signals(tracked, strat))
        actionable = [s for s in signals if s.action.value in ("BUY", "SELL")]

        quant_rows = self.quant_stats(tracked)
        leaderboard = self.screen_strategies(
            tracked,
            strategies,
            cash=paper_cash,
            min_bars=min_bars,
            rank_by=rank_by,
            on_progress=on_progress,
        )
        best = best_per_symbol(leaderboard, rank_by=rank_by)
        portfolio = self.replay_portfolio(paper_cash)

        sections = {
            "Market overview": reporting.market_overview_md(breadth),
            "Top movers": reporting.movers_md(gainers, losers),
            "Reconciliation quality": reporting.reconciliation_report(
                self.storage.reconciled_history_for_date(business_date)[:50]
            ),
            "Signals (actionable)": reporting.signals_markdown(actionable or signals[:20]),
            "Quantitative stats": reporting.quant_md(quant_rows),
            f"Backtest leaderboard (by {rank_by})": reporting.leaderboard_md(
                [r.as_dict() for r in leaderboard]
            ),
            "Best strategy per symbol": reporting.leaderboard_md([r.as_dict() for r in best]),
            "Paper portfolio": reporting.portfolio_summary(portfolio.to_dict()),
        }
        summary = {
            "business_date": business_date.isoformat(),
            "symbols": breadth["symbols"],
            "advancers": breadth["advancers"],
            "decliners": breadth["decliners"],
            "actionable_signals": len(actionable),
            "backtests": len(leaderboard),
            "top_strategy": (leaderboard[0].as_dict() if leaderboard else None),
        }
        log.info("daily_report summary: %s", summary)
        self.storage.record_run_metrics("daily-report", business_date, summary)
        return sections, summary
