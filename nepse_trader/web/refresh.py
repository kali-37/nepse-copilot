"""One-button source refresh, historical repair and decision generation."""
from __future__ import annotations

from datetime import date, timedelta

from nepse_trader.advisor.decisions import build_decisions, publish_decisions
from nepse_trader.advisor.positions import owned_positions
from nepse_trader.ingest.history import backfill_history


def refresh_today(ctx) -> dict:
    pipe = None
    try:
        if not ctx.settings.online:
            raise ValueError("Online mode is disabled. Enable it in Settings to refresh public sources; saved advice remains available offline.")
        pipe = ctx.pipeline(include_all_sources=False)
        return _refresh_today(ctx, pipe)
    finally:
        if pipe is not None:
            for source in pipe.clients:
                transport = getattr(source, 'client', None)
                if transport is not None and hasattr(transport, 'close'):
                    transport.close()


def _refresh_today(ctx, pipe) -> dict:
    if not ctx.settings.online:
        raise ValueError("Online mode is disabled. Enable it in Settings to refresh public sources; saved advice remains available offline.")
    warnings = []
    with ctx.stage("ingest") as stage:
        ctx.log_line(f"Refreshing {len(pipe.clients)} enabled public sources; keeping their published dates")
        report = pipe.ingest(None, force=True)
        warnings.extend(report.warnings)
        warnings.extend(f"{name}: download failed" for name in report.errors)
        if not report.total_bars:
            warnings.append("No market prices returned. Advice uses stored data.")
        stage.detail = f"{report.total_bars} price rows; {len(report.errors)} source errors"
    ctx.check_cancelled()
    with ctx.stage("reconcile") as stage:
        # Reconcile observed dates, including the previous session returned on
        # a holiday. A requested date never gets stamped onto source data.
        days = sorted(day for day in report.business_dates if day <= date.today())
        if any(day > date.today() for day in report.business_dates):
            warnings.append("Future-dated source rows excluded from current advice.")
        count = sum(len(pipe.reconcile(day)) for day in days)
        stage.detail = f"{count} consensus rows across {len(days)} published sessions"
    with ctx.stage("history") as stage:
        observed = ctx.storage.latest_reconciled_date()
        names = [row[0] for row in ctx.storage._conn.execute(
            "SELECT symbol FROM reconciled_prices GROUP BY symbol HAVING COUNT(*)<60 AND MAX(volume)>=1000 ORDER BY symbol")]
        owned = {p["symbol"] for p in owned_positions(pipe)}
        names = sorted(set(names) | {s for s in owned if len(ctx.storage.reconciled_history(s)) < 60})
        if names:
            history = backfill_history(pipe, names[:30], since=date.today() - timedelta(days=800),
                until=observed, source="chukul", on_progress=ctx.progress, check_cancelled=ctx.check_cancelled)
            warnings.extend(f"{symbol}: history unavailable" for symbol in history.errors)
            if len(names) > 30:
                warnings.append(f"History repaired for 30 names; {len(names)-30} still need history. Refresh again to continue.")
            stage.detail = f"{history.bars} history rows; {len(history.errors)} unavailable names"
        else:
            stage.detail = "Stored price history is ready"
    with ctx.stage("analyse") as stage:
        board = build_decisions(pipe, on_progress=ctx.progress, check_cancelled=ctx.check_cancelled)
        stage.detail = f"{board['coverage']['analysable']} charts analysed; daily/monthly fee-aware historical comparisons rebuilt"
    with ctx.stage("context") as stage:
        from nepse_trader.ingest.base import BaseClient
        from nepse_trader.ingest.chukul import ChukulClient
        from nepse_trader.ingest.fundamentals import MeroLaganiFundamentalsClient
        watchlist = {p['symbol'] for p in board.get('investments',{}).get('candidates',[])}
        snapshots_to_refresh = {symbol for symbol, data in ctx.storage.fundamentals().items()
            if data.eps and data.eps>0 and data.pe_ratio and 0<data.pe_ratio<=30 and data.book_value and data.book_value>0}
        priority = board.get("fundamental_checks_needed",[]) + sorted(watchlist | snapshots_to_refresh)
        trade_names = sorted(owned | {idea['symbol'] for group in board['buys'].values() for idea in group})
        names = list(dict.fromkeys(priority+trade_names))[:14]
        snapshots = contracts = 0
        with BaseClient(ctx.settings, cache_raw=False) as http:
            client = MeroLaganiFundamentalsClient(client=http)
            for i, symbol in enumerate(names, 1):
                ctx.check_cancelled()
                try:
                    data = client.fetch_fundamentals(symbol)
                    if data and (data.eps is not None or data.market_price is not None):
                        ctx.storage.upsert_fundamental(data)
                        snapshots += 1
                    else:
                        warnings.append(f"{symbol}: fundamentals unavailable")
                except Exception:
                    warnings.append(f"{symbol}: fundamentals unavailable")
                ctx.progress(i, len(names), symbol)
            if board["market_date"]:
                try:
                    entries = ChukulClient(client=http).fetch_floorsheet(date.fromisoformat(board["market_date"]))
                    contracts = ctx.storage.upsert_floorsheet(entries)
                    if not entries:
                        warnings.append("No current broker contracts returned.")
                except Exception:
                    warnings.append("Broker contracts could not be refreshed.")
        stage.detail = f"{snapshots} company snapshots; {contracts} broker contracts"
    with ctx.stage("save") as stage:
        board["refresh"] = {"sources": report.per_source, "warnings": warnings,
                            "downloaded_prices": report.total_bars, "fundamentals": snapshots,
                            "contracts": contracts}
        refresh_status = board["refresh"]
        board = publish_decisions(pipe, board)
        if "refresh" not in board:
            board["refresh"] = refresh_status
            board = publish_decisions(pipe, board)
        stage.detail = "Buy ideas, holdings, charts and source status saved"
    return {"board": board, "ingest": report.as_dict(), "warnings": warnings}
