"""NEPSE Trader command-line interface.

Run as ``python -m nepse_trader.cli.main <command>`` or the installed
``nepse-trader`` script. Commands cover the full daily loop: ingest, reconcile,
signal, backtest, paper-trade, report, plus the HAR endpoint-discovery toolkit.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

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
from nepse_trader.rag.build import DEFAULT_STRATEGIES
from nepse_trader.rag.corpus import ALL_KINDS
from nepse_trader.reporting import (
    backtest_report,
    leaderboard_md,
    portfolio_summary,
    quant_md,
    rashifal_md,
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
# Advisor/portfolio groups are deliberately separate from the existing paper
# commands.  The groups expose read/review actions only; nothing in this file
# can submit a broker order, an auction bid, or an IPO/ASBA application.
journal_app = typer.Typer(help="Prediction journal lifecycle and calibration.", no_args_is_help=True)
auction_app = typer.Typer(help="Auction bid advice (manual, never submitted).", no_args_is_help=True)
meroshare_app = typer.Typer(
    help="Read-only MeroShare mirror (credentials stay out of logs and the DB).",
    no_args_is_help=True,
)
mcp_app = typer.Typer(help="Expose the local toolkit over MCP stdio.", no_args_is_help=True)
app.add_typer(journal_app, name="journal")
app.add_typer(auction_app, name="auction")
app.add_typer(meroshare_app, name="meroshare")
app.add_typer(mcp_app, name="mcp")

console = Console()
PAPER_CASH_DEFAULT = 100_000.0

# How each health verdict renders. "off" is a feature nobody turned on, so it is
# grey rather than red — it is information, not a problem.
_HEALTH_MARKS = {
    "ok": "[green]ok[/green]",
    "warn": "[yellow]warn[/yellow]",
    "fail": "[red]FAIL[/red]",
    "off": "[dim]off[/dim]",
}


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


def _normalise_symbols(value: str | None, fallback: list[str]) -> list[str]:
    """Return distinct upper-case tickers from an option or the stored default."""
    raw = value.split(",") if value else fallback
    symbols: list[str] = []
    for item in raw:
        symbol = str(item).strip().upper()
        if symbol and symbol not in symbols:
            symbols.append(symbol)
    return symbols


def _advisor_mode(value: str) -> str:
    mode = value.strip().lower()
    if mode not in {"normal", "ai"}:
        raise ValueError("mode must be 'normal' or 'ai'")
    return mode


def _advisor_horizon(value: str) -> str:
    from nepse_trader.advisor.doses import DOSE_HORIZONS

    horizon = value.strip().lower()
    if horizon not in DOSE_HORIZONS:
        raise ValueError(f"horizon must be one of {', '.join(DOSE_HORIZONS)}")
    return horizon


def _latest_strategy_panel(pipe: DailyPipeline, symbol: str) -> list[Any]:
    """Generate one current vote per strategy without writing derived signals."""
    bars = pipe.reconciled_bars(symbol)
    panel: list[Any] = []
    for name in STRATEGIES:
        signals = build_strategy(name).generate(bars)
        if signals:
            panel.append(signals[-1])
    return panel


def _journal_confidence(conn, **context: Any):
    """Look up the comparable, already-resolved history for one plan card."""
    from nepse_trader.advisor.confidence import market
    from nepse_trader.advisor.doses import DOSE_HORIZONS
    from nepse_trader.advisor.journal import confidence_for_prediction

    horizon_days = int(context.get("horizon_days") or 0)
    horizon = next((name for name, days in DOSE_HORIZONS.items() if days == horizon_days), "")
    try:
        return confidence_for_prediction(
            conn,
            symbol=str(context.get("symbol") or ""),
            action=str(context.get("action") or ""),
            horizon=horizon,
            horizon_days=horizon_days,
        )
    except Exception:
        # A confidence lookup must not make a deterministic prescription fail.
        return market(0.45, "journal confidence unavailable; house prior")


def _advisor_evidence(conn, settings, online: bool):
    """Build the optional AI-only evidence callback over local RAG and live web."""
    from nepse_trader.rag import DocumentIndex, build_evidence, build_retriever

    index = DocumentIndex(conn)
    retriever = build_retriever(index, settings, online=online)

    def evidence_for(symbol: str) -> str:
        query = symbol or "NEPSE market breadth regime"
        hits = retriever.retrieve(
            query,
            limit=settings.rag_max_documents,
            symbols=[symbol] if symbol else None,
        )
        return build_evidence(
            hits,
            query=query,
            max_documents=settings.rag_max_documents,
            max_chars=settings.rag_max_evidence_chars,
        ).render()

    return evidence_for


def _advisor_positions(pipe: DailyPipeline, equity: float) -> dict[str, int]:
    """Prefer the local read-only MeroShare mirror, then the paper portfolio."""
    from nepse_trader.meroshare import stored_holdings

    mirror = stored_holdings(pipe.storage._conn)
    if mirror:
        positions: dict[str, int] = {}
        for holding in mirror:
            positions[holding.symbol] = positions.get(holding.symbol, 0) + holding.current_balance
        return positions
    return {position.symbol: position.quantity for position in pipe.replay_portfolio(equity).holdings()}


def _build_advisor_result(
    pipe: DailyPipeline,
    *,
    symbols: str | None,
    equity: float,
    run_date: date | None,
    mode: str,
    online: bool,
    horizon: str,
):
    """Compose a prescription from local data; callers choose whether to save it."""
    from nepse_trader.advisor.rashifal import build_rashifal

    mode = _advisor_mode(mode)
    horizon = _advisor_horizon(horizon)
    run_date = run_date or pipe.storage.latest_reconciled_date()
    if run_date is None:
        raise ValueError("no reconciled prices are available; ingest and reconcile data first")
    if equity <= 0:
        raise ValueError("equity must be positive")

    candidates = _normalise_symbols(
        symbols,
        pipe.settings.watchlist or pipe.storage.symbols(),
    )[: max(1, pipe.settings.advisor_max_symbols)]
    if not candidates:
        raise ValueError("no symbols are available; ingest and reconcile data first")

    analyst = None
    evidence_for = None
    if mode == "ai":
        from nepse_trader.ai import Analyst

        analyst = Analyst(pipe.storage._conn, pipe.settings, online=online)
        evidence_for = _advisor_evidence(pipe.storage._conn, pipe.settings, online)

    return build_rashifal(
        symbols=candidates,
        bars_for=pipe.reconciled_bars,
        signals_for=lambda symbol: _latest_strategy_panel(pipe, symbol),
        equity=equity,
        run_date=run_date,
        mode=mode,
        horizon=horizon,
        online=online,
        breadth=pipe.market_breadth(run_date),
        positions=_advisor_positions(pipe, equity),
        analyst=analyst,
        evidence_for=evidence_for,
        cost_engine=pipe.cost_engine,
        confidence_for=lambda **context: _journal_confidence(pipe.storage._conn, **context),
        max_symbols=pipe.settings.advisor_max_symbols,
    )


def _advisor_sections(result: Any) -> dict[str, str]:
    """Markdown sections shared by the direct advisor command and run-daily."""
    from nepse_trader.advisor.doses import render_doses

    payload = result.as_dict()
    doses = result.doses
    return {
        "Daily investment prescription": rashifal_md(payload),
        "Investment doses": render_doses(doses) if doses is not None else "No dose data available.",
    }


def _safe_holding_payload(holding: Any) -> dict[str, Any]:
    """Render a mirror row without exposing its full demat identifier."""
    demat = str(
        getattr(holding, "demat_last4", "")
        or getattr(holding, "demat_number", "")
        or ""
    )
    return {
        "symbol": holding.symbol,
        "current_balance": holding.current_balance,
        "previous_balance": holding.previous_balance,
        "pledged_balance": holding.pledged_balance,
        "wacc": holding.wacc,
        "previous_closing_price": holding.previous_closing_price,
        "cost_basis": holding.cost_basis,
        "market_value": holding.market_value,
        "isin": holding.isin,
        "script_desc": holding.script_desc,
        "demat_last4": demat[-4:] if demat else None,
        "last_transaction_date": (
            holding.last_transaction_date.isoformat() if holding.last_transaction_date else None
        ),
        "source": holding.source,
    }


_MEROSHARE_ENABLED_LINE = re.compile(r"^(\s*(?:export\s+)?NEPSE_MEROSHARE_ENABLED\s*=).*$", re.I)


def _set_meroshare_enabled(enabled: bool, env_path: Path = Path(".env")) -> Path:
    """Change only the integration toggle in the local .env file."""
    value = "true" if enabled else "false"
    text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    lines = text.splitlines(keepends=True)
    changed = False
    for index, line in enumerate(lines):
        match = _MEROSHARE_ENABLED_LINE.match(line.rstrip("\r\n"))
        if match is None:
            continue
        ending = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
        lines[index] = f"{match.group(1)}{value}{ending}"
        changed = True
        break
    if not changed:
        if lines and not lines[-1].endswith(("\n", "\r")):
            lines.append("\n")
        lines.append(f"NEPSE_MEROSHARE_ENABLED={value}\n")
    env_path.write_text("".join(lines), encoding="utf-8")
    get_settings.cache_clear()
    return env_path


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
    date_: str = typer.Option(
        None, "--date", help="Trading date YYYY-MM-DD (default: newest ingested date)"
    ),
) -> None:
    """Reconcile stored prices across sources into a confidence-scored consensus."""
    pipe = DailyPipeline()
    bd = _parse_date(date_) or pipe.storage.latest_price_date() or date.today()
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
    advisor: bool = typer.Option(
        False,
        "--advisor/--no-advisor",
        help="Also generate and save the deterministic/AI investment prescription",
    ),
    advisor_mode: str = typer.Option("normal", "--advisor-mode", help="normal or ai"),
    advisor_horizon: str = typer.Option("week", "--advisor-horizon", help="day, week, month or year"),
    advisor_online: bool = typer.Option(
        False,
        "--advisor-online/--advisor-offline",
        help="Allow live RAG/LLM retrieval for the advisor (offline by default)",
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

    if advisor:
        try:
            result = _build_advisor_result(
                pipe,
                symbols=None,
                equity=cash,
                run_date=bd,
                mode=advisor_mode,
                online=advisor_online,
                horizon=advisor_horizon,
            )
            from nepse_trader.advisor.rashifal import save_rashifal

            save_rashifal(pipe.storage._conn, result)
            advisor_sections = _advisor_sections(result)
            console.print("\n[bold]Daily investment prescription[/bold]\n" + advisor_sections[
                "Daily investment prescription"
            ])
            if report:
                # Re-write with the advisor sections included. Existing report
                # content is preserved and the advisor becomes an auditable
                # appendix rather than changing the daily summary contract.
                write_markdown_report(report, {**sections, **advisor_sections})
        except (ValueError, RuntimeError) as exc:
            console.print(f"[yellow]Advisor skipped:[/yellow] {exc}")


# --------------------------------------------------------------------- advisor
@app.command("advise")
@app.command("rashifal")
@_safe_run
def rashifal(
    symbols: str = typer.Option(None, "--symbols", help="Comma-separated symbols (default: watchlist or stored)"),
    equity: float = typer.Option(100_000.0, help="Capital shared by all four doses (NPR)"),
    date_: str = typer.Option(None, "--date", help="Trading date YYYY-MM-DD (default: latest reconciled)"),
    mode: str = typer.Option("normal", "--mode", help="normal or ai; AI can add prose only"),
    online: bool = typer.Option(
        False,
        "--online/--offline",
        help="Allow live RAG/LLM retrieval in AI mode (offline by default)",
    ),
    horizon: str = typer.Option("week", "--horizon", help="Primary card horizon: day, week, month or year"),
    save: bool = typer.Option(True, "--save/--no-save", help="Log this prescription for later scoring"),
    report: str = typer.Option(None, "--report", help="Write the prescription as a Markdown report"),
) -> None:
    """Generate a four-horizon, fee-aware investment prescription.

    The report is advisory only. It never places an order, and AI mode can add
    narrative but cannot change a price, stop, target, quantity, or confidence.
    """
    settings = get_settings()
    storage = Storage(settings.db_path)
    try:
        pipe = DailyPipeline(settings=settings, storage=storage, clients=[])
        result = _build_advisor_result(
            pipe,
            symbols=symbols,
            equity=equity,
            run_date=_parse_date(date_),
            mode=mode,
            online=online,
            horizon=horizon,
        )
        if save:
            from nepse_trader.advisor.rashifal import save_rashifal

            save_rashifal(storage._conn, result)
        sections = _advisor_sections(result)
        console.print(sections["Daily investment prescription"])
        console.print("\n[bold]Investment doses[/bold]\n" + sections["Investment doses"])
        if report:
            write_markdown_report(report, sections)
            console.print(f"\n[green]Prescription report written:[/green] {report}")
    finally:
        storage.close()


@app.command()
@_safe_run
def doses(
    symbols: str = typer.Option(None, "--symbols", help="Comma-separated symbols (default: watchlist or stored)"),
    equity: float = typer.Option(100_000.0, help="Capital shared by all four doses (NPR)"),
    date_: str = typer.Option(None, "--date", help="Trading date YYYY-MM-DD (default: latest reconciled)"),
    mode: str = typer.Option("normal", "--mode", help="normal or ai; AI can add prose only"),
    online: bool = typer.Option(
        False,
        "--online/--offline",
        help="Allow live RAG/LLM retrieval in AI mode (offline by default)",
    ),
    horizon: str = typer.Option("week", "--horizon", help="Primary card horizon: day, week, month or year"),
    latest: bool = typer.Option(False, "--latest", help="Show the most recently saved prescription"),
    save: bool = typer.Option(False, "--save/--no-save", help="Save a newly generated prescription"),
) -> None:
    """Show all day/week/month/year doses over one shared capital pool."""
    from nepse_trader.advisor.doses import latest_dose_run, render_doses
    from nepse_trader.advisor.rashifal import save_rashifal

    settings = get_settings()
    storage = Storage(settings.db_path)
    try:
        if latest:
            result = latest_dose_run(storage._conn)
            if result is None:
                console.print("[yellow]No saved dose prescription yet — run rashifal first.[/yellow]")
                raise typer.Exit(code=1)
            console.print(render_doses(result))
            return

        pipe = DailyPipeline(settings=settings, storage=storage, clients=[])
        result = _build_advisor_result(
            pipe,
            symbols=symbols,
            equity=equity,
            run_date=_parse_date(date_),
            mode=mode,
            online=online,
            horizon=horizon,
        )
        if save:
            save_rashifal(storage._conn, result)
        if result.doses is None:
            raise ValueError("the prescription did not produce a dose report")
        console.print(render_doses(result.doses))
    finally:
        storage.close()


# --------------------------------------------------------------------- journal
@journal_app.command("history")
@_safe_run
def journal_history_cmd(
    symbol: str = typer.Option(None, "--symbol", help="Filter by symbol"),
    status: str = typer.Option(None, "--status", help="Filter: open, scored, reviewed or retired"),
    limit: int = typer.Option(100, help="Maximum rows"),
) -> None:
    """List recorded predictions and their current lifecycle state."""
    from nepse_trader.advisor.journal import journal_history

    storage = Storage(get_settings().db_path)
    try:
        rows = journal_history(storage._conn, symbol=symbol, status=status, limit=limit)
        console.print_json(json.dumps(rows, default=str))
    finally:
        storage.close()


@journal_app.command("score")
@_safe_run
def journal_score_cmd(
    prediction_id: str = typer.Argument(None, help="One prediction id (default: all open predictions)"),
    as_of: str = typer.Option(None, "--as-of", help="Score only through YYYY-MM-DD"),
    limit: int = typer.Option(100, help="Maximum open predictions to score"),
) -> None:
    """Score open calls against reconciled bars; stop is checked before target."""
    from nepse_trader.advisor.journal import record_score
    from nepse_trader.advisor.outcomes import score_predictions

    storage = Storage(get_settings().db_path)
    try:
        if prediction_id:
            rows = storage._conn.execute(
                "SELECT * FROM predictions WHERE (prediction_id=? OR CAST(id AS TEXT)=?) AND status='open'",
                (prediction_id, prediction_id),
            ).fetchall()
            if not rows:
                raise ValueError("no open prediction matched that id")
        else:
            rows = storage._conn.execute(
                "SELECT * FROM predictions WHERE status='open' ORDER BY made_on, id LIMIT ?",
                (max(1, limit),),
            ).fetchall()
        pipe = DailyPipeline(settings=get_settings(), storage=storage, clients=[])
        results = score_predictions(
            list(rows),
            pipe.reconciled_bars,
            cost_engine=pipe.cost_engine,
            as_of=_parse_date(as_of),
        )
        for result in results:
            record_score(storage._conn, result.prediction_id, result)
        console.print_json(json.dumps([result.as_dict() for result in results], default=str))
    finally:
        storage.close()


@journal_app.command("review")
@_safe_run
def journal_review_cmd(
    prediction_id: str = typer.Argument(..., help="Prediction id"),
    text: str = typer.Option(..., "--text", help="Human or AI review of the scored outcome"),
) -> None:
    """Attach a review to a scored prediction."""
    from nepse_trader.advisor.journal import record_review

    storage = Storage(get_settings().db_path)
    try:
        prediction = record_review(storage._conn, prediction_id, text)
        console.print_json(json.dumps(prediction.as_dict(), default=str))
    finally:
        storage.close()


@journal_app.command("distill")
@_safe_run
def journal_distill_cmd(
    prediction_id: str = typer.Argument(..., help="Prediction id"),
    lesson: str = typer.Option(..., "--lesson", help="Durable lesson to index for future RAG"),
) -> None:
    """Distill a reviewed prediction into a RAG-searchable lesson."""
    from nepse_trader.advisor.journal import distill_lesson

    storage = Storage(get_settings().db_path)
    try:
        lesson_id = distill_lesson(storage._conn, prediction_id, lesson)
        console.print_json(json.dumps({"prediction_id": prediction_id, "lesson_id": lesson_id}))
    finally:
        storage.close()


@journal_app.command("retire")
@_safe_run
def journal_retire_cmd(
    prediction_id: str = typer.Argument(..., help="Prediction id"),
) -> None:
    """Retire a reviewed prediction after its lesson is saved."""
    from nepse_trader.advisor.journal import retire_prediction

    storage = Storage(get_settings().db_path)
    try:
        prediction = retire_prediction(storage._conn, prediction_id)
        console.print_json(json.dumps(prediction.as_dict(), default=str))
    finally:
        storage.close()


@journal_app.command("calibration")
@_safe_run
def journal_calibration_cmd(
    symbol: str = typer.Option(None, "--symbol", help="Filter by symbol"),
    horizon: str = typer.Option(None, "--horizon", help="Filter by dose horizon"),
) -> None:
    """Show the materialised hit-rate and realised-vs-expected calibration."""
    storage = Storage(get_settings().db_path)
    try:
        clauses: list[str] = []
        params: list[str] = []
        if symbol:
            clauses.append("subject=?")
            params.append(symbol.strip().upper())
        if horizon:
            clauses.append("horizon=?")
            params.append(_advisor_horizon(horizon))
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        rows = storage._conn.execute(
            "SELECT * FROM calibration" + where + " ORDER BY subject, horizon", params
        ).fetchall()
        console.print_json(json.dumps([dict(row) for row in rows], default=str))
    finally:
        storage.close()


# --------------------------------------------------------------------- auction
@auction_app.command("advise")
@_safe_run
def auction_advise_cmd(
    symbol: str = typer.Argument(..., help="NEPSE symbol"),
    auction_date: str = typer.Option(None, "--auction-date", help="Auction date YYYY-MM-DD (default: today)"),
    units: int = typer.Option(..., "--units", help="Units offered in the auction"),
    min_bid_price: float = typer.Option(..., "--min-bid-price", help="Auction minimum bid price (NPR)"),
    market_price: float = typer.Option(..., "--market-price", help="Current market price (NPR)"),
    expected_exit_price: float = typer.Option(None, "--expected-exit-price", help="Explicit future exit assumption (NPR)"),
    horizon_days: int = typer.Option(10, "--horizon-days", help="Holding horizon in trading days"),
    quantity: int = typer.Option(None, "--quantity", help="Units to evaluate (default: all offered)"),
    confidence: float = typer.Option(None, "--confidence", min=0.0, max=1.0, help="0 to 1 market confidence"),
    edge_buffer_pct: float = typer.Option(0.10, "--edge-buffer-pct", help="Conservative margin under fee-neutral bid"),
) -> None:
    """Calculate a fee-aware manual bid ceiling; this never submits a bid."""
    from nepse_trader.advisor.auction import build_auction_advice, save_auction_advice

    advice = build_auction_advice(
        symbol,
        auction_date=_parse_date(auction_date) or date.today(),
        units=units,
        min_bid_price=min_bid_price,
        market_price=market_price,
        expected_exit_price=expected_exit_price,
        horizon_days=horizon_days,
        quantity=quantity,
        confidence=confidence,
        edge_buffer_pct=edge_buffer_pct,
    )
    storage = Storage(get_settings().db_path)
    try:
        save_auction_advice(storage._conn, advice)
        storage._conn.commit()
    finally:
        storage.close()
    console.print_json(json.dumps(advice.as_dict(), default=str))
    console.print("[dim]Manual advice only. No auction bid was submitted.[/dim]")


@auction_app.command("list")
@_safe_run
def auction_list_cmd(
    symbol: str = typer.Option(None, "--symbol", help="Filter by symbol"),
    limit: int = typer.Option(50, help="Maximum rows"),
) -> None:
    """List saved manual auction advice, newest first."""
    from nepse_trader.advisor.auction import auction_advice_history

    storage = Storage(get_settings().db_path)
    try:
        rows = auction_advice_history(storage._conn, symbol=symbol, limit=limit)
        console.print_json(json.dumps(rows, default=str))
    finally:
        storage.close()


# ------------------------------------------------------------------- meroshare
@meroshare_app.command("connect")
def meroshare_connect_cmd(
    yes: bool = typer.Option(False, "--yes", help="Confirm the disclosed read-only CDSC login"),
) -> None:
    """Show the data disclosure, then test one read-only MeroShare connection."""
    from nepse_trader.meroshare import connect, connection_disclosure

    settings = get_settings()
    console.print(connection_disclosure(settings))
    if not yes:
        console.print("\n[yellow]No connection was made. Re-run with --yes to confirm.[/yellow]")
        return
    try:
        result = connect(settings)
    except Exception:
        console.print("[red]MeroShare connection failed. No account changes were made.[/red]")
        raise typer.Exit(code=1) from None
    if result.ok:
        console.print("[green]Read-only MeroShare connection completed. No account data was changed.[/green]")
        return
    console.print("[red]MeroShare connection failed. No account changes were made.[/red]")
    raise typer.Exit(code=1)


@meroshare_app.command("sync")
def meroshare_sync_cmd(
    yes: bool = typer.Option(False, "--yes", help="Confirm the disclosed read-only CDSC login"),
    transactions: bool = typer.Option(
        True,
        "--transactions/--holdings-only",
        help="Also mirror transaction history when CDSC makes it available",
    ),
) -> None:
    """Read and mirror holdings only; no MeroShare-side action is available."""
    from nepse_trader.meroshare import MeroShareClient, ensure_enabled, sync_from_client

    if not yes:
        console.print("[yellow]No portal request was made. Re-run with --yes to confirm.[/yellow]")
        return
    storage = Storage(get_settings().db_path)
    client = None
    try:
        settings = ensure_enabled(get_settings())
        client = MeroShareClient(settings)
        result = sync_from_client(storage._conn, client, with_transactions=transactions)
    except Exception:
        console.print("[red]MeroShare sync could not complete. Existing mirrored holdings were left unchanged.[/red]")
        raise typer.Exit(code=1) from None
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
        storage.close()
    if not result.ok:
        console.print("[red]MeroShare sync could not complete. Existing mirrored holdings were left unchanged.[/red]")
        raise typer.Exit(code=1)
    console.print(
        f"[green]Mirrored {result.holdings} holding(s) and {result.transactions} transaction(s).[/green]"
    )


@meroshare_app.command("import")
def meroshare_import_cmd(
    file: Path = typer.Option(..., "--file", help="CSV export to mirror locally"),
) -> None:
    """Import a MeroShare CSV export without using any portal credential."""
    from nepse_trader.meroshare import sync_from_csv

    storage = Storage(get_settings().db_path)
    try:
        result = sync_from_csv(storage._conn, file, is_path=True)
    except Exception:
        console.print("[red]MeroShare CSV import could not complete. Existing mirrored holdings were left unchanged.[/red]")
        raise typer.Exit(code=1) from None
    finally:
        storage.close()
    if not result.ok:
        console.print("[red]MeroShare CSV import could not complete. Existing mirrored holdings were left unchanged.[/red]")
        raise typer.Exit(code=1)
    console.print(f"[green]Imported {result.holdings} holding(s) into the local read-only mirror.[/green]")


@meroshare_app.command("holdings")
def meroshare_holdings_cmd() -> None:
    """Show locally mirrored holdings. This command makes no portal request."""
    from nepse_trader.meroshare import stored_holdings, sync_status

    storage = Storage(get_settings().db_path)
    try:
        payload = {
            "status": {key: value for key, value in sync_status(storage._conn).items() if key != "last_error"},
            "holdings": [_safe_holding_payload(holding) for holding in stored_holdings(storage._conn)],
            "source": "local mirror only; no CDSC request was made",
        }
        console.print_json(json.dumps(payload, default=str))
    finally:
        storage.close()


@meroshare_app.command("status")
def meroshare_status_cmd() -> None:
    """Show local mirror freshness without displaying any credential or raw error."""
    from nepse_trader.meroshare import sync_status

    storage = Storage(get_settings().db_path)
    try:
        payload = {key: value for key, value in sync_status(storage._conn).items() if key != "last_error"}
        payload["enabled"] = get_settings().meroshare_enabled
        console.print_json(json.dumps(payload, default=str))
    finally:
        storage.close()


@meroshare_app.command("toggle")
@_safe_run
def meroshare_toggle_cmd(
    state: str = typer.Argument(..., help="on or off"),
    env_file: Path = typer.Option(Path(".env"), "--env-file", help="Settings file to update"),
) -> None:
    """Turn the optional MeroShare integration on or off in one local setting."""
    wanted = state.strip().lower()
    if wanted not in {"on", "off"}:
        raise ValueError("state must be 'on' or 'off'")
    path = _set_meroshare_enabled(wanted == "on", env_file)
    console.print(f"[green]MeroShare integration set to {wanted} in {path}.[/green]")


# ------------------------------------------------------------------------ mcp
@mcp_app.command("serve")
def mcp_serve_cmd() -> None:
    """Serve the local, read-only MCP toolkit over stdio."""
    from nepse_trader.mcp_server.server import serve_stdio

    # stdout is the JSON-RPC transport. Do not print before entering the server.
    serve_stdio()


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
def health(
    json_out: bool = typer.Option(False, "--json", help="Emit the whole report as JSON"),
    problems_only: bool = typer.Option(
        False, "--problems", help="Print only the warnings and failures"
    ),
    record: bool = typer.Option(
        False, "--record", help="Store this report in health_snapshots for trend tracking"
    ),
    history: int = typer.Option(
        0, "--history", help="Instead of checking, show the last N recorded snapshots"
    ),
) -> None:
    """Check every moving part: schema, data freshness, sources, RAG, AI, MeroShare.

    Read-only and offline — no source is fetched and no provider is called. Exits
    non-zero when any check fails, so cron can alert on it.
    """
    from nepse_trader import health as health_mod

    storage = Storage(get_settings().db_path)
    try:
        if history:
            rows = health_mod.snapshot_history(storage._conn, limit=history)
            if json_out:
                console.print_json(json.dumps(rows, default=str))
                return
            if not rows:
                console.print("[yellow]No snapshots recorded yet — run 'health --record'.[/yellow]")
                return
            for row in rows:
                mark = _HEALTH_MARKS.get(row["status"], row["status"])
                console.print(
                    f"{mark} [dim]{row['captured_at']}[/dim]  "
                    f"ok={row['ok']} warn={row['warn']} fail={row['fail']} off={row['off']}"
                )
            return

        report = health_mod.system_health(storage, get_settings())
        if record:
            report["snapshot_id"] = health_mod.record_snapshot(storage._conn, report)
    finally:
        storage.close()

    if json_out:
        console.print_json(json.dumps(report, default=str))
    else:
        shown = health_mod.problems(report) if problems_only else report["checks"]
        counts = report["counts"]
        console.print(
            f"[bold]Overall:[/bold] {_HEALTH_MARKS.get(report['status'], report['status'])}  "
            f"[dim]{counts.get('ok', 0)} ok, {counts.get('warn', 0)} warn, "
            f"{counts.get('fail', 0)} fail, {counts.get('off', 0)} off[/dim]"
        )
        if problems_only and not shown:
            console.print("[green]Nothing needs attention.[/green]")
        for check in shown:
            mark = _HEALTH_MARKS.get(check["status"], check["status"])
            console.print(f"\n{mark} [bold]{check['name']}[/bold]\n  {check['detail']}")
        if record:
            console.print(f"\n[dim]recorded as snapshot {report['snapshot_id']}[/dim]")

    if report["status"] == "fail":
        raise typer.Exit(1)


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
    strategies: str = typer.Option(
        ",".join(DEFAULT_STRATEGIES), help=f"Strategies to record signals for: {', '.join(STRATEGIES)}"
    ),
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
        console.print(f"[yellow]{len(report.errors)} problem(s) during indexing:[/yellow]")
        for key, err in list(report.errors.items())[:10]:
            console.print(f"  • {key}: {err}")

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


# ------------------------------------------------------------------------ ai
ai_app = typer.Typer(
    help="AI mode: provider status, token budget, connectivity check.", no_args_is_help=True
)
app.add_typer(ai_app, name="ai")


def _router(online: bool | None = None):
    """A router over the real database. Opens the DB; caller keeps the Storage."""
    from nepse_trader.ai import LLMRouter

    settings = get_settings()
    storage = Storage(settings.db_path)
    return LLMRouter(storage._conn, settings, online=online), storage


@ai_app.command("models")
@_safe_run
def ai_models() -> None:
    """Show each provider chain and which legs are actually usable."""
    router, storage = _router()
    try:
        status = router.status()
    finally:
        storage.close()

    console.print(f"[bold]Mode:[/bold] {'online' if status['online'] else 'offline'}")
    for tier, legs in status["tiers"].items():
        console.print(f"\n[bold]{tier}[/bold] chain:")
        if not legs:
            console.print("  [yellow](empty — nothing configured)[/yellow]")
        for leg in legs:
            if not leg["known"]:
                mark, note = "[red]✗[/red]", "unknown provider name"
            elif leg["available"]:
                mark, note = "[green]✓[/green]", leg["model"]
            else:
                mark, note = "[yellow]–[/yellow]", "not configured"
            console.print(f"  {mark} {leg['name']}  [dim]{note}[/dim]")
    if not any(leg["available"] for legs in status["tiers"].values() for leg in legs):
        console.print(
            "\n[yellow]No provider is usable — AI mode will degrade to normal mode. "
            "See .env.example for what to set.[/yellow]"
        )


@ai_app.command("budget")
@_safe_run
def ai_budget(
    history: int = typer.Option(0, "--history", help="Also show the last N ledger rows"),
) -> None:
    """Today's LLM spend against the caps, plus cache size."""
    router, storage = _router()
    try:
        summary = router.budget.summary()
        cache = router.cache.stats()
        rows = router.budget.history(limit=history) if history else []
    finally:
        storage.close()

    console.print(f"[bold]{summary.day}[/bold]  (week {summary.week})")
    console.print(f"  calls   {summary.calls}/{summary.max_calls}  [dim]({summary.calls_left} left)[/dim]")
    console.print(
        f"  tokens  {summary.tokens:,}/{summary.max_tokens:,}  "
        f"[dim]({summary.tokens_left:,} left)[/dim]"
    )
    console.print(
        f"  deep    {summary.deep_passes}/{summary.max_deep_passes} this week  "
        f"[dim]({summary.deep_passes_left} left)[/dim]"
    )
    console.print(f"  [dim]served from cache: {summary.cached_calls}; failed: {summary.failed_calls}[/dim]")
    if summary.exhausted:
        console.print("[yellow]Budget exhausted — AI mode will degrade to normal mode today.[/yellow]")

    state = "off" if not cache["enabled"] else f"{cache['ttl_hours']}h TTL"
    console.print(f"\n[bold]Cache:[/bold] {cache['entries']} entry(ies), {state}")
    if cache["newest"]:
        console.print(f"  [dim]newest {cache['newest']}[/dim]")

    for row in rows:
        flag = "cache" if row["cached"] else ("ok" if row["ok"] else "fail")
        tokens = row["prompt_tokens"] + row["completion_tokens"]
        console.print(
            f"  [dim]{row['created_at'][:19]}  {row['task']:<14} {row['provider']:<11} "
            f"{flag:<5} {tokens:>7,}  {row['error'] or ''}[/dim]"
        )


@ai_app.command("test")
@_safe_run
def ai_test(
    tier: str = typer.Option("synthesis", help="Which chain to exercise: bulk | synthesis"),
) -> None:
    """Send one tiny prompt through a chain and report what answered.

    This spends real budget — a few tokens — because the only honest way to know a
    provider works is to use it.
    """
    from nepse_trader.ai import TIERS, prompts

    if tier not in TIERS:
        raise typer.BadParameter(f"tier must be one of {', '.join(TIERS)}")

    router, storage = _router(online=True)
    try:
        with progress_spinner(console, f"Asking the {tier} chain..."):
            response = router.complete(
                prompts.PING, task="ai_test", tier=tier, max_tokens=64, use_cache=False
            )
    finally:
        storage.close()

    if response.ok:
        console.print(
            f"[green]{response.provider}[/green] answered "
            f"[dim]({response.model}, {response.total_tokens:,} tokens)[/dim]"
        )
        console.print(f"  {response.text.strip()[:200]}")
    else:
        console.print(f"[red]No provider answered.[/red] {response.error}")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
