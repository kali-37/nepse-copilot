"""Historical ingestion shared by the CLI and background jobs."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from datetime import date

from nepse_trader.config import load_sources
from nepse_trader.ingest.base import BaseClient
from nepse_trader.ingest.chukul import ChukulClient
from nepse_trader.ingest.sharesansar import ShareSansarClient
from nepse_trader.pipeline import DailyPipeline


@dataclass
class BackfillReport:
    symbols: int = 0
    bars: int = 0
    reconciled: int = 0
    first_date: str | None = None
    last_date: str | None = None
    per_symbol: dict[str, int] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    source: str = "sharesansar"

    def as_dict(self) -> dict:
        return asdict(self)


def backfill_history(
    pipeline: DailyPipeline,
    symbols: Sequence[str],
    *,
    since: date | None = None,
    until: date | None = None,
    on_progress: Callable[[int, int, str], object] | None = None,
    check_cancelled: Callable[[], object] | None = None,
    client: ShareSansarClient | None = None,
    source: str = "sharesansar",
) -> BackfillReport:
    """Upsert published sessions and reconcile each day, with per-name isolation.

    Repeating a backfill updates existing rows. Dates come exclusively from the
    source response; a requested range never becomes a price's business date.
    """
    names = sorted({s.strip().upper() for s in symbols if s.strip()})
    if not names or len(names) > 500 or any(not re.fullmatch(r"[A-Z0-9][A-Z0-9.-]{0,19}(?:/[0-9]{1,4})?", s) for s in names):
        raise ValueError("Provide 1–500 valid ticker symbols.")
    until = until or date.today()
    if since is not None and since > until:
        raise ValueError("Start date must be on or before the end date.")
    if not pipeline.settings.online:
        raise ValueError("History download requires online mode.")
    factories = {"sharesansar": ShareSansarClient, "chukul": ChukulClient}
    if source not in factories:
        raise ValueError("History source must be sharesansar or chukul.")
    owned = client is None
    client = client or factories[source](client=BaseClient(pipeline.settings, cache_raw=False),
                                        source_spec=load_sources(pipeline.settings.sources_file).get(source))
    report = BackfillReport(symbols=len(names), source=source)
    dates: set[date] = set()
    reconciled_symbols: set[str] = set()
    try:
        for index, symbol in enumerate(names, 1):
            if check_cancelled:
                check_cancelled()
            try:
                bars = [bar for bar in client.fetch_company_history(symbol, since=since)
                        if bar.business_date <= until and (since is None or bar.business_date >= since)]
                if not bars:
                    report.errors[symbol] = "No published history returned."
                count = pipeline.storage.upsert_price_bars(bars)
                dates.update(bar.business_date for bar in bars)
                report.per_symbol[symbol] = count
                report.bars += count
            except Exception as exc:
                # Do not expose response bodies, cookies or request tokens.
                report.errors[symbol] = f"History fetch failed ({type(exc).__name__})."
            if on_progress:
                on_progress(index, len(names), symbol)
        for business_date in sorted(dates):
            if check_cancelled:
                check_cancelled()
            # Batch consensus for all fetched days, then adjust history once.
            from nepse_trader.ingest.reconcile import reconcile_bars

            prices = reconcile_bars(pipeline.storage.bars_for_date(business_date),
                                    tolerance=pipeline.settings.price_agreement_tolerance)
            report.reconciled += pipeline.storage.upsert_reconciled(prices)
            reconciled_symbols.update(price.symbol for price in prices)
        pipeline.refresh_adjustments(reconciled_symbols)
    finally:
        if owned:
            client.client.close()
    if dates:
        report.first_date = min(dates).isoformat()
        report.last_date = max(dates).isoformat()
    return report
