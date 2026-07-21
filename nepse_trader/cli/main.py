"""NEPSE Trader command-line interface.

Run as ``python -m nepse_trader.cli.main <command>`` or the installed
``nepse-trader`` script. Commands cover the full daily loop: ingest, reconcile,
signal, backtest, paper-trade, report, plus the HAR endpoint-discovery toolkit.
"""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

import typer
from rich.console import Console

from nepse_trader.analysis.backtest import Backtester
from nepse_trader.analysis.costs import CostEngine
from nepse_trader.analysis.strategies import STRATEGIES, build_strategy
from nepse_trader.calendar import is_trading_day
from nepse_trader.config import get_settings, load_sources
from nepse_trader.har import analyzer
from nepse_trader.logging_setup import run_logger
from nepse_trader.pipeline import DailyPipeline
from nepse_trader.reporting import (
    backtest_report,
    leaderboard_md,
    portfolio_summary,
    quant_md,
    reconciliation_report,
    signals_table,
    write_markdown_report,
)

app = typer.Typer(
    add_completion=False,
    help="NEPSE public-data aggregation, analysis, backtesting & paper trading.",
    no_args_is_help=True,
)
har_app = typer.Typer(help="HAR capture analysis & endpoint discovery.", no_args_is_help=True)
paper_app = typer.Typer(help="Paper-trading (no live orders).", no_args_is_help=True)
app.add_typer(har_app, name="har")
app.add_typer(paper_app, name="paper")

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
def ingest(
    date_: str = typer.Option(None, "--date", help="Trading date YYYY-MM-DD (default: today)"),
    all_sources: bool = typer.Option(
        False, "--all-sources", help="Pull from EVERY configured source, ignore enable flags"
    ),
) -> None:
    """Pull public data from sources into the local database.

    By default only the sources enabled in config are used. --all-sources scrapes
    every site and keeps whatever responds (resilient to any one site being down).
    """
    bd = _parse_date(date_)
    pipe = DailyPipeline(include_all_sources=all_sources)
    rep = pipe.ingest(bd)
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
    strat_list = (
        list(STRATEGIES)
        if strategies.strip().lower() == "all"
        else [s.strip() for s in strategies.split(",") if s.strip()]
    )
    rows = pipe.screen_strategies(
        strategy_names=strat_list, cash=cash, min_bars=min_bars, rank_by=rank_by
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
    ing = pipe.ingest(bd)
    console.print(
        f"Ingested {ing.total_bars} bars from {len(ing.per_source)} source(s)"
        + (f"; errors: {', '.join(ing.errors)}" if ing.errors else "")
    )
    prices = pipe.reconcile(bd)
    console.print(f"Reconciled {len(prices)} symbols.")

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
def paper_status(
    cash: float = typer.Option(PAPER_CASH_DEFAULT, help="Starting cash (keep consistent)"),
) -> None:
    """Show the current paper portfolio (rebuilt from recorded trades)."""
    pipe = DailyPipeline()
    pf = pipe.replay_portfolio(cash)
    console.print(portfolio_summary(pf.to_dict()))
    console.print(f"\n{pf.summary()}")


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


@har_app.command("redact")
def har_redact(har_file: str) -> None:
    """Strip cookies/auth headers; write <name>.redacted.har next to the input."""
    har = analyzer.load_har(har_file)
    red = analyzer.redact(har)
    out = Path(har_file).with_suffix(".redacted.har")
    out.write_text(json.dumps(red, indent=2), encoding="utf-8")
    console.print(f"[green]Redacted HAR written:[/green] {out}")


if __name__ == "__main__":
    app()
