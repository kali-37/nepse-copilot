"""NEPSE Trader command-line interface.

Run as ``python -m nepse_trader.cli.main <command>`` or the installed
``nepse-trader`` script. Commands cover the full daily loop: ingest, reconcile,
signal, backtest, paper-trade, report, plus the HAR endpoint-discovery toolkit.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from decimal import Decimal
from pathlib import Path

import typer
from rich.console import Console

from nepse_trader.analysis.backtest import Backtester
from nepse_trader.analysis.costs import CostEngine
from nepse_trader.analysis.strategies import STRATEGIES, build_strategy
from nepse_trader.calendar import is_trading_day
from nepse_trader.cli.progress import progress_bars, progress_spinner
from nepse_trader.config import get_settings, load_sources
from nepse_trader.export import EXPORT_TABLES, export_csv, export_parquet
from nepse_trader.har import analyzer
from nepse_trader.ingest.fundamentals import MeroLaganiFundamentalsClient
from nepse_trader.logging_setup import run_logger
from nepse_trader.models import CorporateAction, CorporateActionType, SourceName
from nepse_trader.pipeline import DailyPipeline
from nepse_trader.rag.corpus import ALL_KINDS
from nepse_trader.reporting import (
    backtest_report,
    leaderboard_md,
    portfolio_summary,
    quant_md,
    reconciliation_report,
    signals_table,
    write_markdown_report,
)
from nepse_trader.storage import Storage


def _safe_run(fn):
    """Decorator: catch common exceptions and print user-friendly messages."""
    from functools import wraps

    @wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except typer.Exit:
            raise
        except (ConnectionError, TimeoutError):
            console.print("[red]Network error — check your internet connection.[/red]")
            raise typer.Exit(1) from None
        except FileNotFoundError as e:
            console.print(f"[red]File not found:[/red] {e}")
            raise typer.Exit(1) from None
        except ValueError as e:
            console.print(f"[red]Invalid value:[/red] {e}")
            raise typer.Exit(1) from None
        except KeyError as e:
            console.print(f"[red]Missing key:[/red] {e}")
            raise typer.Exit(1) from None
        except Exception as e:
            console.print(f"[red]Unexpected error:[/red] {e}")
            raise typer.Exit(1) from None

    return wrapper


app = typer.Typer(
    add_completion=False,
    help="NEPSE public-data aggregation, analysis, backtesting & paper trading.",
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
    pretty_exceptions_enable=False,
)
har_app = typer.Typer(help="HAR capture analysis & endpoint discovery.", no_args_is_help=True)
paper_app = typer.Typer(help="Paper-trading (no live orders).", no_args_is_help=True)
ca_app = typer.Typer(help="Corporate actions (manual add & list).", no_args_is_help=True)
app.add_typer(har_app, name="har")
app.add_typer(paper_app, name="paper")
app.add_typer(ca_app, name="corporate-actions")
fund_app = typer.Typer(help="Company fundamentals (EPS, PE, PB, etc.).", no_args_is_help=True)
app.add_typer(fund_app, name="fundamentals")

console = Console()
PAPER_CASH_DEFAULT = 100_000.0


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter(f"date must be YYYY-MM-DD: {value}") from exc


def _strategy_kwargs(fast, slow, period, signal) -> dict:
    kw = {}
    if fast is not None:
        kw["fast"] = fast
    if slow is not None:
        kw["slow"] = slow
    if period is not None:
        kw["period"] = period
    if signal is not None:
        kw["signal"] = signal
    return kw


@app.callback()
def _root(
    ctx: typer.Context,
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging"),
):
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    # Log every invocation to logs/cli/<time>-<date>-<command...>.log. The run
    # logger is bound to the Click context, so it stays open for the whole
    # command body and closes (flushing + detaching) when the command returns.
    sub = ctx.invoked_subcommand or "help"
    extras = [a for a in (ctx.args or []) if not a.startswith("-")]
    about = "-".join([sub, *extras]) if extras else sub
    path = ctx.with_resource(run_logger("cli", about))
    log = logging.getLogger("nepse_trader.cli")
    log.info("command: %s  argv-extras: %s", sub, extras)
    log.info("logfile: %s", path)


@app.command()
def sources() -> None:
    """List configured data sources and whether they're enabled."""
    settings = get_settings()
    cfg = load_sources()
    console.print(f"[bold]Enabled (settings):[/bold] {', '.join(settings.enabled_sources)}")
    for name, spec in cfg.sources.items():
        flag = "on" if spec.enabled else "off"
        console.print(
            f"  • [cyan]{name}[/cyan] [{flag}] {spec.base_url}  "
            f"({len(spec.endpoints)} endpoints, {spec.access_method})"
        )


@app.command()
@_safe_run
def ingest(
    date_: str = typer.Option(None, "--date", help="Trading date YYYY-MM-DD (default: today)"),
    all_sources: bool = typer.Option(
        False, "--all-sources", help="Pull from EVERY configured source, ignore enable flags"
    ),
    async_: bool = typer.Option(False, "--async", help="Fetch from all sources concurrently"),
) -> None:
    """Pull public data from sources into the local database.

    By default only the sources enabled in config are used. --all-sources scrapes
    every site and keeps whatever responds (resilient to any one site being down).
    Use --async to fetch from all sources concurrently (faster but more memory).
    """
    bd = _parse_date(date_)
    pipe = DailyPipeline(include_all_sources=all_sources)
    with progress_spinner(console, f"Ingesting from {len(pipe.clients)} source(s)..."):
        import asyncio
        rep = asyncio.run(pipe.async_ingest(bd)) if async_ else pipe.ingest(bd)
    console.print_json(json.dumps(rep.as_dict()))
    if rep.errors:
        console.print(f"[yellow]sources with errors:[/yellow] {', '.join(rep.errors)}")
    if rep.total_bars == 0:
        console.print(
            "[yellow]No rows ingested.[/yellow] Markets may be closed, the date may be a "
            "holiday/weekend, or a source's layout changed — capture a HAR and re-verify."
        )


@app.command()
def reconcile(
    date_: str = typer.Option(None, "--date", help="Trading date YYYY-MM-DD (default: today)"),
) -> None:
    """Reconcile stored prices across sources into a confidence-scored consensus."""
    bd = _parse_date(date_) or date.today()
    pipe = DailyPipeline()
    with progress_spinner(console, "Reconciling prices across sources..."):
        prices = pipe.reconcile(bd)
    console.print(reconciliation_report(prices))
    low = [p for p in prices if not p.is_trustworthy]
    console.print(
        f"\n[bold]{len(prices)}[/bold] symbols reconciled; "
        f"[{'yellow' if low else 'green'}]{len(low)}[/] flagged low-confidence/disputed."
    )


@app.command()
def signal(
    symbol: str,
    strategy: str = typer.Option("sma_cross", help=f"One of: {', '.join(STRATEGIES)}"),
    fast: int = typer.Option(None),
    slow: int = typer.Option(None),
    period: int = typer.Option(None),
    signal_: int = typer.Option(None, "--signal"),
) -> None:
    """Generate signals for a symbol from its reconciled history."""
    pipe = DailyPipeline()
    kwargs = _strategy_kwargs(fast, slow, period, signal_)
    sigs = pipe.signals_for(symbol, strategy, **kwargs)
    if not sigs:
        console.print(
            f"[yellow]No signals for {symbol.upper()}[/yellow] — not enough reconciled history. "
            "Ingest + reconcile several trading days first."
        )
        raise typer.Exit()
    console.print(signals_table(sigs[-15:]))
    console.print(f"\nLatest: [bold]{sigs[-1].action.value}[/bold] ({sigs[-1].reason})")


@app.command()
def backtest(
    symbol: str,
    strategy: str = typer.Option("sma_cross", help=f"One of: {', '.join(STRATEGIES)}"),
    cash: float = typer.Option(100_000.0, help="Initial capital (NPR)"),
    fraction: float = typer.Option(1.0, help="Fraction of cash deployed per entry"),
    fast: int = typer.Option(None),
    slow: int = typer.Option(None),
    period: int = typer.Option(None),
    signal_: int = typer.Option(None, "--signal"),
) -> None:
    """Backtest a strategy on a symbol's reconciled history (Nepal costs applied)."""
    pipe = DailyPipeline()
    with progress_spinner(console, f"Loading reconciled history for {symbol.upper()}..."):
        bars = pipe.reconciled_bars(symbol)
    if len(bars) < 2:
        console.print(f"[yellow]Not enough history for {symbol.upper()} to backtest.[/yellow]")
        raise typer.Exit(code=1)
    strat = build_strategy(strategy, **_strategy_kwargs(fast, slow, period, signal_))
    bt = Backtester(cost_engine=CostEngine(), initial_cash=cash, position_fraction=fraction)
    result = bt.run(strat, bars)
    console.print(backtest_report(result.summary()))
    console.print(f"\n{result}")


@app.command()
def stats(
    symbols: str = typer.Argument(None, help="Comma-separated symbols (default: all stored)"),
    top: int = typer.Option(25, help="Max symbols when none are named"),
    periods: int = typer.Option(252, help="Trading periods/year for annualisation"),
) -> None:
    """Quantitative statistics per symbol over reconciled history.

    Annualised return & volatility, Sharpe, Sortino, max drawdown, 95% VaR,
    skewness and kurtosis — the mathematical view of each name.
    """
    pipe = DailyPipeline()
    syms = (
        [s.strip().upper() for s in symbols.split(",") if s.strip()]
        if symbols
        else pipe.storage.symbols()[:top]
    )
    if not syms:
        console.print("[yellow]No symbols in the database yet — ingest + reconcile first.[/yellow]")
        raise typer.Exit()
    with progress_spinner(console, f"Computing stats for {len(syms)} symbol(s)..."):
        rows = pipe.quant_stats(syms, periods_per_year=periods)
    console.print(quant_md(rows))


@app.command()
def screen(
    strategies: str = typer.Option(
        "all", "--strategies", help=f"Comma list or 'all' of: {', '.join(STRATEGIES)}"
    ),
    rank_by: str = typer.Option(
        "sharpe", help="sharpe|total_return_pct|cagr_pct|max_drawdown_pct|win_rate_pct"
    ),
    cash: float = typer.Option(100_000.0, help="Initial capital per backtest"),
    min_bars: int = typer.Option(60, help="Skip symbols with fewer bars"),
    top: int = typer.Option(30, help="Show top N leaderboard rows"),
    best_only: bool = typer.Option(False, "--best-only", help="Best strategy per symbol only"),
) -> None:
    """Backtest the strategy panel across all symbols and rank the results.

    Nepal costs (commission/SEBON/DP/CGT) are applied to every simulated trade,
    so the leaderboard reflects net, after-cost performance.
    """
    pipe = DailyPipeline()
    all_syms = pipe.storage.symbols()
    strat_list = (
        list(STRATEGIES)
        if strategies.strip().lower() == "all"
        else [s.strip() for s in strategies.split(",") if s.strip()]
    )
    console.print(f"[dim]Screening {len(all_syms)} symbols × {len(strat_list)} strategies...[/dim]")
    with progress_bars(console) as prog:
        task = prog.add_task("Backtesting...", total=len(all_syms))
        def _progress(_i, _total, _sym):
            prog.update(task, completed=_i, description=f"Backtesting {_sym}")
        rows = pipe.screen_strategies(
            strategy_names=strat_list, cash=cash, min_bars=min_bars, rank_by=rank_by,
            on_progress=_progress,
        )
    if not rows:
        console.print(
            "[yellow]Nothing to screen[/yellow] — need symbols with >= "
            f"{min_bars} reconciled bars. Backfill more history first."
        )
        raise typer.Exit()
    if best_only:
        from nepse_trader.analysis.screen import best_per_symbol

        rows = best_per_symbol(rows, rank_by=rank_by)
    console.print(leaderboard_md([r.as_dict() for r in rows], limit=top))


@app.command(name="run-daily")
@_safe_run
def run_daily(
    date_: str = typer.Option(None, "--date", help="Trading date YYYY-MM-DD (default: today)"),
    strategies: str = typer.Option(
        "all", "--strategies", help=f"Comma list or 'all' of: {', '.join(STRATEGIES)}"
    ),
    report: str = typer.Option(None, "--report", help="Write the full markdown report here"),
    top: int = typer.Option(25, help="Max symbols to analyse"),
    rank_by: str = typer.Option("sharpe", help="Leaderboard rank metric"),
    cash: float = typer.Option(100_000.0, help="Paper-portfolio starting cash"),
    all_sources: bool = typer.Option(
        True, "--all-sources/--enabled-only", help="Scrape every site (default) or only enabled"
    ),
) -> None:
    """The once-a-day run: ingest (all sources) → reconcile → full analytics report.

    Produces market breadth, top movers, reconciliation quality, multi-strategy
    signals, per-symbol quant stats, and a Nepal-cost backtest leaderboard — the
    single command you schedule daily.
    """
    bd = _parse_date(date_) or date.today()
    if not is_trading_day(bd):
        console.print(f"[yellow]Skipping {bd.isoformat()} — not a NEPSE trading day[/yellow]")
        raise typer.Exit()
    strat_list = (
        list(STRATEGIES)
        if strategies.strip().lower() == "all"
        else [s.strip() for s in strategies.split(",") if s.strip()]
    )
    pipe = DailyPipeline(include_all_sources=all_sources)
    with progress_spinner(console, f"Ingesting from {len(pipe.clients)} source(s)..."):
        ing = pipe.ingest(bd)
    console.print(
        f"Ingested {ing.total_bars} bars from {len(ing.per_source)} source(s)"
        + (f"; errors: {', '.join(ing.errors)}" if ing.errors else "")
    )
    with progress_spinner(console, "Reconciling..."):
        prices = pipe.reconcile(bd)
    console.print(f"Reconciled {len(prices)} symbols.")

    all_syms = pipe.storage.symbols()
    console.print(f"[dim]Full analysis on {len(all_syms)} symbols...[/dim]")
    sections, summary = pipe.daily_report(
        bd, strategies=strat_list, top=top, rank_by=rank_by, paper_cash=cash
    )
    # Console: headline summary + the leaderboard + actionable signals.
    console.print_json(json.dumps(summary, default=str))
    for title in (
        "Market overview",
        f"Backtest leaderboard (by {rank_by})",
        "Signals (actionable)",
    ):
        if title in sections:
            console.print(f"\n[bold]{title}[/bold]\n{sections[title]}")
    if report:
        write_markdown_report(report, sections)
        console.print(f"\n[green]Full report written:[/green] {report}")


# --------------------------------------------------------------------- paper
@paper_app.command("buy")
@_safe_run
def paper_buy(
    symbol: str,
    price: float = typer.Option(..., help="Buy price per share (NPR)"),
    qty: int = typer.Option(..., "--qty", help="Number of shares"),
    date_: str = typer.Option(None, "--date", help="Trade date YYYY-MM-DD"),
    cash: float = typer.Option(PAPER_CASH_DEFAULT, help="Starting cash (keep consistent)"),
) -> None:
    """Record a paper BUY (full Nepal fees applied)."""
    bd = _parse_date(date_) or date.today()
    pipe = DailyPipeline()
    pf = pipe.replay_portfolio(cash)
    pf.storage = pipe.storage  # persist only the new trade
    try:
        trade = pf.buy(symbol, price, qty, bd)
    except ValueError as exc:
        console.print(f"[red]Rejected:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    console.print(
        f"[green]BUY[/green] {trade.quantity} {trade.symbol} @ {trade.price} "
        f"→ cash out {trade.net_amount:,.2f} (fees {trade.broker_commission + trade.sebon_fee + trade.dp_charge:,.2f})"
    )
    console.print(pf.summary())


@paper_app.command("sell")
@_safe_run
def paper_sell(
    symbol: str,
    price: float = typer.Option(..., help="Sell price per share (NPR)"),
    qty: int = typer.Option(..., "--qty", help="Number of shares"),
    date_: str = typer.Option(None, "--date", help="Trade date YYYY-MM-DD"),
    cash: float = typer.Option(PAPER_CASH_DEFAULT, help="Starting cash (keep consistent)"),
) -> None:
    """Record a paper SELL (fees + CGT applied on realized gain)."""
    bd = _parse_date(date_) or date.today()
    pipe = DailyPipeline()
    pf = pipe.replay_portfolio(cash)
    pf.storage = pipe.storage
    try:
        trade = pf.sell(symbol, price, qty, bd)
    except ValueError as exc:
        console.print(f"[red]Rejected:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    console.print(
        f"[red]SELL[/red] {trade.quantity} {trade.symbol} @ {trade.price} "
        f"→ cash in {trade.net_amount:,.2f} (CGT {trade.cgt:,.2f})"
    )
    console.print(pf.summary())


@paper_app.command("status")
@_safe_run
def paper_status(
    cash: float = typer.Option(PAPER_CASH_DEFAULT, help="Starting cash for replay"),
) -> None:
    """Show the current paper portfolio (rebuilt from recorded trades)."""
    pipe = DailyPipeline()
    pf = pipe.replay_portfolio(cash)
    console.print(portfolio_summary(pf.to_dict()))
    console.print(f"\n{pf.summary()}")


# ---------------------------------------------------------------- fundamentals
@fund_app.command("show")
def fund_show(
    symbol: str = typer.Argument(..., help="NEPSE symbol"),
) -> None:
    """Show fundamental data for a symbol from MeroLagani."""
    client = MeroLaganiFundamentalsClient()
    data = client.fetch_fundamentals(symbol)
    if data is None or (data.market_price is None and data.eps is None):
        console.print(f"[red]No fundamentals found for {symbol}.[/red]")
        raise typer.Exit(1)
    from rich.table import Table
    table = Table(title=f"{symbol} — Fundamentals", show_header=False)
    table.add_column("Field")
    table.add_column("Value")
    for field, val in [
        ("Company", data.company_name),
        ("Sector", data.sector),
        ("Market Price", f"NPR {data.market_price:,.2f}" if data.market_price else "—"),
        ("EPS", f"{data.eps:.2f}" if data.eps else "—"),
        ("P/E", f"{data.pe_ratio:.2f}" if data.pe_ratio else "—"),
        ("Book Value", f"{data.book_value:.2f}" if data.book_value else "—"),
        ("PBV", f"{data.pbv:.2f}" if data.pbv else "—"),
        ("Dividend", f"{data.dividend_pct:.2f}%" if data.dividend_pct else "—"),
        ("Market Cap", f"NPR {data.market_cap:,.0f}" if data.market_cap else "—"),
        ("Shares Out.", f"{data.shares_outstanding:,.0f}" if data.shares_outstanding else "—"),
        ("52W High", f"{data.high_52w:.2f}" if data.high_52w else "—"),
        ("52W Low", f"{data.low_52w:.2f}" if data.low_52w else "—"),
        ("30D Avg Vol", f"{data.avg_volume_30d:,}" if data.avg_volume_30d else "—"),
    ]:
        table.add_row(field, val)
    console.print(table)


# ---------------------------------------------------------------- corporate-actions
@ca_app.command("list")
def ca_list(
    symbol: str = typer.Option(None, "--symbol", "-s", help="Filter by symbol"),
) -> None:
    """List stored corporate action events."""
    storage = Storage(get_settings().db_path)
    cas = storage.corporate_actions(symbol=symbol)
    if not cas:
        console.print("[yellow]No corporate actions found.[/yellow]")
        raise typer.Exit()
    from rich.table import Table

    table = Table(title="Corporate Actions")
    for col in ("Symbol", "Ex-Date", "Type", "Ratio", "Factor", "Source", "Notes"):
        table.add_column(col)
    for ca in cas:
        table.add_row(
            ca.symbol,
            ca.ex_date.isoformat(),
            ca.action_type.value,
            f"{ca.ratio_numerator}:{ca.ratio_denominator}",
            str(ca.factor),
            ca.source.value,
            ca.notes or "",
        )
    console.print(table)


@ca_app.command("add")
def ca_add(
    symbol: str = typer.Option(..., help="Ticker symbol"),
    ex_date: str = typer.Option(..., "--ex-date", help="Ex-date YYYY-MM-DD"),
    action_type: str = typer.Option(..., "--type", help="bonus / rights / split / dividend"),
    ratio_numerator: int = typer.Option(1, "--num", help="Ratio numerator (e.g. 1 for 1:1)"),
    ratio_denominator: int = typer.Option(1, "--den", help="Ratio denominator (e.g. 1 for 1:1)"),
    notes: str = typer.Option("", "--notes", help="Optional notes"),
) -> None:
    """Manually record a corporate action event."""
    try:
        atype = CorporateActionType(action_type.lower())
    except ValueError:
        console.print(f"[red]Invalid action type: {action_type}. Use bonus/rights/split/dividend[/red]")
        raise typer.Exit(code=1) from None
    try:
        bd = date.fromisoformat(ex_date)
    except ValueError:
        console.print(f"[red]Invalid date: {ex_date}. Use YYYY-MM-DD[/red]")
        raise typer.Exit(code=1) from None

    factor = round(ratio_denominator / ratio_numerator, 6) if ratio_numerator else 1.0
    d_factor = Decimal(str(factor))

    ca = CorporateAction(
        symbol=symbol,
        ex_date=bd,
        action_type=atype,
        ratio_numerator=ratio_numerator,
        ratio_denominator=ratio_denominator,
        factor=d_factor,
        source=SourceName.MANUAL,
        notes=notes,
    )
    storage = Storage(get_settings().db_path)
    storage.upsert_corporate_action(ca)
    console.print(f"[green]Recorded:[/green] {ca.description} for {ca.symbol} on {ca.ex_date} (factor {ca.factor})")


# ----------------------------------------------------------------------- har
@har_app.command("analyze")
def har_analyze(har_file: str, top: int = typer.Option(20, help="Show top N candidates")) -> None:
    """Rank candidate data endpoints found in a HAR capture."""
    har = analyzer.load_har(har_file)
    cands = analyzer.analyze(har)[:top]
    if not cands:
        console.print("[yellow]No data-like endpoints found.[/yellow]")
        raise typer.Exit()
    from rich.table import Table

    table = Table(title=f"Endpoint candidates — {Path(har_file).name}")
    for col in ("Request", "Kind", "Score", "Sample keys / tables"):
        table.add_column(col, overflow="fold")
    for c in cands:
        table.add_row(*c.as_row())
    console.print(table)


@har_app.command("to-config")
def har_to_config(har_file: str, source: str = typer.Option(..., help="Source name")) -> None:
    """Emit a sources.yaml snippet for the top endpoints in a HAR."""
    har = analyzer.load_har(har_file)
    console.print(analyzer.to_config_snippet(har, source))


@app.command()
@_safe_run
def dashboard() -> None:
    """Summary statistics about the local database and paper portfolio."""
    storage = Storage(get_settings().db_path)
    stats = storage.db_stats()
    from rich.table import Table

    rows = [
        ("Symbols with price data", stats.get("symbols_with_data", 0)),
        ("Sources contributing data", stats.get("sources_with_data", 0)),
        ("Price bar rows", f"{stats.get('price_bar_rows', 0):,}"),
        ("Reconciled rows", f"{stats.get('reconciled_rows', 0):,}"),
        ("Price date range", f"{stats.get('price_date_earliest')} → {stats.get('price_date_latest')}"),
        ("Reconciled date range", f"{stats.get('reconciled_date_earliest')} → {stats.get('reconciled_date_latest')}"),
        ("Signal strategies", stats.get("signal_strategies", 0)),
        ("Signal rows", f"{stats.get('signal_rows', 0):,}"),
        ("Ingest log entries", f"{stats.get('ingest_log_rows', 0):,}"),
        ("Paper trades recorded", stats.get("paper_trades", 0)),
    ]

    if stats.get("latest_reconciled_date"):
        rows.append(("Latest reconciliation", stats["latest_reconciled_date"]))
        rows.append(("  • Symbols", stats.get("latest_symbols", 0)))
        rows.append(("  • Avg confidence", stats.get("latest_avg_confidence", "—")))
        rows.append(("  • Disputed (<70%)", stats.get("latest_disputed", 0)))

    db_path = Path(get_settings().db_path)
    size_mb = db_path.stat().st_size / (1024 * 1024) if db_path.exists() else 0
    rows.append(("Database size", f"{size_mb:.1f} MB"))

    table = Table(title="NEPSE Trader — Dashboard", show_header=False)
    table.add_column("Metric")
    table.add_column("Value")
    for label, val in rows:
        table.add_row(label, str(val))
    console.print(table)

    # Paper portfolio summary
    try:
        from nepse_trader.trading.portfolio import PaperPortfolio
        pf = PaperPortfolio(initial_cash=100_000.0)
        for t in storage.paper_trades():
            if t.side.value == "BUY":
                pf.buy(t.symbol, t.price, t.quantity, t.business_date, t.strategy)
            else:
                pf.sell(t.symbol, t.price, t.quantity, t.business_date, t.strategy)
        if pf.trades:
            console.print(f"\n[bold]Paper portfolio:[/bold] {pf.summary()}")
    except Exception:
        pass


@har_app.command("redact")
def har_redact(har_file: str) -> None:
    """Strip cookies/auth headers; write <name>.redacted.har next to the input."""
    har = analyzer.load_har(har_file)
    red = analyzer.redact(har)
    out = Path(har_file).with_suffix(".redacted.har")
    out.write_text(json.dumps(red, indent=2), encoding="utf-8")
    console.print(f"[green]Redacted HAR written:[/green] {out}")


# -------------------------------------------------------------------- export
export_app = typer.Typer(help="Export database tables to CSV or Parquet.", no_args_is_help=True)
app.add_typer(export_app, name="export")


@export_app.command("csv")
@_safe_run
def export_csv_cmd(
    out_dir: str = typer.Option("exports", help="Output directory"),
    tables: str = typer.Option(
        "all", help=f"Comma list or 'all' of: {', '.join(EXPORT_TABLES)}"
    ),
) -> None:
    """Export database tables to CSV files."""
    storage = Storage(get_settings().db_path)
    tbl_list = (
        list(EXPORT_TABLES)
        if tables.strip().lower() == "all"
        else [t.strip() for t in tables.split(",") if t.strip()]
    )
    with progress_spinner(console, f"Exporting {len(tbl_list)} table(s) to CSV..."):
        written = export_csv(storage, Path(out_dir), tbl_list)
    if not written:
        console.print("[yellow]No tables exported (all empty or none matched).[/yellow]")
    else:
        console.print(f"[green]Exported {len(written)} file(s) to {out_dir}/[/green]")
        for p in written:
            console.print(f"  • {p}")


@export_app.command("parquet")
@_safe_run
def export_parquet_cmd(
    out_dir: str = typer.Option("exports", help="Output directory"),
    tables: str = typer.Option(
        "all", help=f"Comma list or 'all' of: {', '.join(EXPORT_TABLES)}"
    ),
) -> None:
    """Export database tables to Parquet files (requires polars)."""
    storage = Storage(get_settings().db_path)
    tbl_list = (
        list(EXPORT_TABLES)
        if tables.strip().lower() == "all"
        else [t.strip() for t in tables.split(",") if t.strip()]
    )
    with progress_spinner(console, f"Exporting {len(tbl_list)} table(s) to Parquet..."):
        written = export_parquet(storage, Path(out_dir), tbl_list)
    if not written:
        console.print("[yellow]No tables exported. Install polars: pip install polars[/yellow]")
    else:
        console.print(f"[green]Exported {len(written)} file(s) to {out_dir}/[/green]")
        for p in written:
            console.print(f"  • {p}")


# ----------------------------------------------------------------------- rag
rag_app = typer.Typer(
    help="Retrieval corpus: index the database, then search it.", no_args_is_help=True
)
app.add_typer(rag_app, name="rag")


@rag_app.command("index")
@_safe_run
def rag_index(
    symbols: str = typer.Option(None, "--symbols", help="Comma-separated symbols (default: all)"),
    recent_days: int = typer.Option(10, help="Price documents to keep per symbol"),
    strategies: str = typer.Option("composite", help="Strategies to record signals for"),
    news: bool = typer.Option(False, "--news", help="Also fetch news & announcements (network)"),
) -> None:
    """Build the searchable document corpus from what's already in the database.

    Runs offline by default: everything indexed is derived from stored prices and
    reconciled history. Pass ``--news`` to additionally fetch ShareSansar news and
    announcements, which is the one part that needs the network.
    """
    from nepse_trader.rag import build_corpus, index_documents

    pipe = DailyPipeline()
    syms = [s.strip().upper() for s in symbols.split(",") if s.strip()] if symbols else None
    strat_list = [s.strip() for s in strategies.split(",") if s.strip()]
    target = syms or pipe.storage.symbols()
    if not target:
        console.print("[yellow]No symbols in the database yet — ingest + reconcile first.[/yellow]")
        raise typer.Exit()

    with progress_bars(console) as prog:
        task = prog.add_task("Indexing...", total=len(target))

        def _progress(i, _total, sym):
            prog.update(task, completed=i, description=f"Indexing {sym}")

        report = build_corpus(
            pipe,
            symbols=syms,
            recent_days=recent_days,
            strategies=strat_list,
            on_progress=_progress,
        )

    console.print(
        f"[green]Indexed {report.documents} document(s)[/green] "
        f"across {report.symbols} symbol(s)."
    )
    if not report.uses_fts:
        console.print(
            "[yellow]This SQLite build has no FTS5 — search will use the slower "
            "LIKE fallback.[/yellow]"
        )
    for kind, n in sorted(report.per_kind.items()):
        console.print(f"  • {kind}: {n}")
    if report.errors:
        console.print(f"[yellow]{len(report.errors)} symbol(s) failed:[/yellow]")
        for sym, err in list(report.errors.items())[:10]:
            console.print(f"  • {sym}: {err}")

    if news:
        from nepse_trader.ingest.news import NewsClient

        with progress_spinner(console, "Fetching news & announcements..."):
            docs = NewsClient().fetch_all(set(pipe.storage.symbols()))
            written = index_documents(pipe.storage, docs)
        console.print(f"[green]Indexed {written} news/announcement document(s).[/green]")


@rag_app.command("search")
@_safe_run
def rag_search(
    query: str = typer.Argument(..., help="What to look for"),
    limit: int = typer.Option(8, help="Max results"),
    symbols: str = typer.Option(None, "--symbols", help="Restrict to these symbols"),
    kinds: str = typer.Option(None, "--kinds", help=f"Restrict to kinds: {', '.join(ALL_KINDS)}"),
    since: str = typer.Option(None, "--since", help="Only documents on/after YYYY-MM-DD"),
    online: bool = typer.Option(
        False, "--online/--offline", help="Also search the live web when local results are thin"
    ),
    full: bool = typer.Option(False, "--full", help="Print each document body in full"),
) -> None:
    """Search the document corpus and show the ranked evidence.

    Offline by default. ``--online`` adds a live web leg, used only when the local
    index returns fewer than three hits.
    """
    from nepse_trader.rag import DocumentIndex, build_evidence, build_retriever

    settings = get_settings()
    storage = Storage(settings.db_path)
    index = DocumentIndex(storage._conn)
    if index.count() == 0:
        console.print("[yellow]The corpus is empty — run `rag index` first.[/yellow]")
        raise typer.Exit()

    retriever = build_retriever(index, settings, online=online)
    hits = retriever.retrieve(
        query,
        limit=limit,
        symbols=[s.strip().upper() for s in symbols.split(",") if s.strip()] if symbols else None,
        kinds=[k.strip() for k in kinds.split(",") if k.strip()] if kinds else None,
        since=_parse_date(since),
    )
    if not hits:
        console.print(f"[yellow]No documents matched {query!r}.[/yellow]")
        raise typer.Exit()

    pack = build_evidence(
        hits,
        query=query,
        max_documents=limit,
        max_chars=settings.rag_max_evidence_chars,
    )
    console.print(
        f"[dim]{len(pack)} of {pack.considered} hit(s); "
        f"{'FTS5 bm25' if index.uses_fts else 'LIKE fallback'} ranking[/dim]\n"
    )
    if full:
        console.print(pack.render())
    else:
        for item in pack.items:
            doc = item.document
            when = doc.business_date.isoformat() if doc.business_date else "—"
            console.print(f"[bold]{item.marker}[/bold] {doc.title} [dim]({when})[/dim]")
            console.print(f"    {doc.body[:220]}{'…' if len(doc.body) > 220 else ''}\n")


if __name__ == "__main__":
    app()
