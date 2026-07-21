"""Reporting & alerting: turn models into human-readable tables and markdown.

Two presentation surfaces are supported:
  * Rich console tables (rendered to a string for logging / capture).
  * Pure GitHub-flavoured markdown builders, which are exact-text testable and
    used for the daily report file and any webhook bodies.

Everything here is deliberately PURE: functions take models / plain dicts and
return strings. The only side effects live in ``write_markdown_report`` (file
write) and ``Alerter.send`` (optional HTTP POST), both kept thin so tests can
drive them without a network.
"""

from __future__ import annotations

import io
from pathlib import Path

import httpx
from rich.console import Console
from rich.table import Table

from nepse_trader.models import PriceBar, ReconciledPrice, Signal

__all__ = [
    "signals_table",
    "signals_markdown",
    "price_bars_markdown",
    "reconciliation_report",
    "portfolio_summary",
    "backtest_report",
    "write_markdown_report",
    "print_signals",
    "Alerter",
    "market_overview_md",
    "movers_md",
    "quant_md",
    "leaderboard_md",
]


def _fmt_num(value: float | int | None, places: int = 2) -> str:
    """Format a number for a table cell; blank for None."""
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.{places}f}"
    return str(value)


def _md_escape(text: str) -> str:
    """Escape pipe characters so cell content cannot break a markdown table."""
    return text.replace("|", "\\|").replace("\n", " ").strip()


def price_bars_markdown(bars: list[PriceBar]) -> str:
    """Markdown table of raw price bars (handy for a per-source appendix)."""
    header = "| Symbol | Date | Open | High | Low | Close | Volume | Source |"
    divider = "| --- | --- | --- | --- | --- | --- | --- | --- |"
    lines = [header, divider]
    for b in bars:
        lines.append(
            f"| {_md_escape(b.symbol)} | {b.business_date.isoformat()} "
            f"| {_fmt_num(b.open)} | {_fmt_num(b.high)} | {_fmt_num(b.low)} "
            f"| {_fmt_num(b.close)} | {_fmt_num(b.volume)} | {b.source.value} |"
        )
    if not bars:
        lines.append("| _no bars_ |  |  |  |  |  |  |  |")
    return "\n".join(lines)


def signals_table(signals: list[Signal]) -> str:
    """Render signals as a Rich table, captured to a plain string."""
    table = Table(title="Signals")
    for col in ("Symbol", "Action", "Strategy", "Strength", "Price", "Reason"):
        table.add_column(col)
    for s in signals:
        table.add_row(
            s.symbol,
            s.action.value,
            s.strategy,
            _fmt_num(s.strength),
            _fmt_num(s.price),
            s.reason or "",
        )
    buffer = io.StringIO()
    console = Console(file=buffer, width=120)
    console.print(table)
    return buffer.getvalue()


def signals_markdown(signals: list[Signal]) -> str:
    """Build a GitHub markdown table of signals (pure, exact-text testable)."""
    header = "| Symbol | Action | Strategy | Strength | Price | Reason |"
    divider = "| --- | --- | --- | --- | --- | --- |"
    lines = [header, divider]
    for s in signals:
        lines.append(
            f"| {_md_escape(s.symbol)} | {s.action.value} | {_md_escape(s.strategy)} "
            f"| {_fmt_num(s.strength)} | {_fmt_num(s.price)} | {_md_escape(s.reason)} |"
        )
    if not signals:
        lines.append("| _no signals_ |  |  |  |  |  |")
    return "\n".join(lines)


def reconciliation_report(prices: list[ReconciledPrice]) -> str:
    """Markdown table of reconciled prices, flagging low-confidence / disputed rows."""
    header = "| Symbol | Close | Confidence | Sources Agreeing | Disputed Fields | Flag |"
    divider = "| --- | --- | --- | --- | --- | --- |"
    lines = [header, divider]
    for p in prices:
        flagged = p.confidence < 0.5 or bool(p.disputed_fields)
        flag = "⚠️" if flagged else "OK"
        agreeing = ", ".join(src.value for src in p.sources_agreeing) or "-"
        disputed = ", ".join(p.disputed_fields) or "-"
        lines.append(
            f"| {_md_escape(p.symbol)} | {_fmt_num(p.close)} | {_fmt_num(p.confidence)} "
            f"| {_md_escape(agreeing)} | {_md_escape(disputed)} | {flag} |"
        )
    if not prices:
        lines.append("| _no prices_ |  |  |  |  |  |")
    return "\n".join(lines)


def portfolio_summary(summary: dict) -> str:
    """Markdown summary of cash, equity, PnL and current positions."""
    cash = summary.get("cash")
    equity = summary.get("equity")
    realized = summary.get("realized_pnl")
    unrealized = summary.get("unrealized_pnl")
    positions = summary.get("positions") or []

    lines = [
        "| Metric | Value |",
        "| --- | --- |",
        f"| Cash | {_fmt_num(cash)} |",
        f"| Equity | {_fmt_num(equity)} |",
        f"| Realized PnL | {_fmt_num(realized)} |",
        f"| Unrealized PnL | {_fmt_num(unrealized)} |",
        "",
        "| Symbol | Quantity | Avg Cost | Cost Basis |",
        "| --- | --- | --- | --- |",
    ]
    if positions:
        for pos in positions:
            symbol = str(pos.get("symbol", "-"))
            qty = pos.get("quantity")
            avg_cost = pos.get("avg_cost")
            cost_basis = None
            if isinstance(qty, (int, float)) and isinstance(avg_cost, (int, float)):
                cost_basis = qty * avg_cost
            lines.append(
                f"| {_md_escape(symbol)} | {_fmt_num(qty)} | {_fmt_num(avg_cost)} "
                f"| {_fmt_num(cost_basis)} |"
            )
    else:
        lines.append("| _no positions_ |  |  |  |")
    return "\n".join(lines)


def backtest_report(result_summary: dict) -> str:
    """Markdown summary of backtest performance metrics."""
    rows = [
        ("Total Return %", result_summary.get("total_return_pct")),
        ("CAGR %", result_summary.get("cagr_pct")),
        ("Max Drawdown %", result_summary.get("max_drawdown_pct")),
        ("Sharpe", result_summary.get("sharpe")),
        ("Num Trades", result_summary.get("num_trades")),
        ("Win Rate %", result_summary.get("win_rate_pct")),
    ]
    lines = ["| Metric | Value |", "| --- | --- |"]
    for label, value in rows:
        lines.append(f"| {label} | {_fmt_num(value)} |")
    return "\n".join(lines)


def write_markdown_report(path: str | Path, sections: dict[str, str]) -> None:
    """Write a combined daily report with a top title and one ``##`` per section."""
    parts = ["# NEPSE Trader Daily Report", ""]
    for title, body in sections.items():
        parts.append(f"## {title}")
        parts.append("")
        parts.append(body)
        parts.append("")
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(parts), encoding="utf-8")


class Alerter:
    """Optional webhook alerter. With no webhook configured it never touches the network."""

    def __init__(self, webhook_url: str | None = None):
        self.webhook_url = webhook_url

    def _post(self, payload: dict) -> httpx.Response:
        """Thin POST wrapper kept separate so tests can monkeypatch it."""
        return httpx.post(self.webhook_url, json=payload, timeout=10.0)

    def send(self, title: str, body: str) -> bool:
        """POST the alert if a webhook is set; return success. No webhook -> False, no call."""
        if not self.webhook_url:
            return False
        payload = {"title": title, "body": body}
        try:
            response = self._post(payload)
        except httpx.HTTPError:
            return False
        return 200 <= response.status_code < 300


def print_signals(signals: list[Signal], console: Console | None = None) -> None:
    """Thin wrapper: print the pure signals table to a console."""
    (console or Console()).print(signals_table(signals))


# --------------------------------------------------------------------------
# Daily-report builders (added for the comprehensive once-a-day run)
# --------------------------------------------------------------------------

def market_overview_md(breadth: dict) -> str:
    """Render market breadth: advancers/decliners/unchanged + totals.

    `breadth` keys: business_date, symbols, advancers, decliners, unchanged,
    total_turnover, avg_confidence, disputed.
    """
    rows = [
        ("Business date", str(breadth.get("business_date", "-"))),
        ("Symbols", _fmt_num(breadth.get("symbols"), 0)),
        ("Advancers", _fmt_num(breadth.get("advancers"), 0)),
        ("Decliners", _fmt_num(breadth.get("decliners"), 0)),
        ("Unchanged", _fmt_num(breadth.get("unchanged"), 0)),
        ("Total turnover (NPR)", _fmt_num(breadth.get("total_turnover"), 0)),
        ("Avg reconcile confidence", _fmt_num(breadth.get("avg_confidence"), 3)),
        ("Low-confidence/disputed", _fmt_num(breadth.get("disputed"), 0)),
    ]
    out = ["| Metric | Value |", "| --- | --- |"]
    out += [f"| {k} | {v} |" for k, v in rows]
    return "\n".join(out)


def movers_md(gainers: list[dict], losers: list[dict]) -> str:
    """Render top gainers and losers (each dict: symbol, close, change_percent)."""
    def _block(title: str, rows: list[dict]) -> list[str]:
        lines = [f"**{title}**", "", "| Symbol | Close | Change % |", "| --- | --- | --- |"]
        if not rows:
            lines.append("| _none_ |  |  |")
        for r in rows:
            lines.append(
                f"| {_md_escape(str(r.get('symbol', '')))} "
                f"| {_fmt_num(r.get('close'))} | {_fmt_num(r.get('change_percent'))} |"
            )
        return lines

    return "\n".join(_block("Top gainers", gainers) + ["", *_block("Top losers", losers)])


_QUANT_COLS = [
    ("symbol", "Symbol", 0),
    ("last_close", "Close", 2),
    ("annualized_return_pct", "Ann.Ret%", 2),
    ("annualized_vol_pct", "Ann.Vol%", 2),
    ("sharpe", "Sharpe", 2),
    ("sortino", "Sortino", 2),
    ("max_drawdown_pct", "MaxDD%", 2),
    ("var_95_pct", "VaR95%", 2),
    ("skewness", "Skew", 2),
    ("kurtosis", "Kurt", 2),
]


def quant_md(rows: list[dict]) -> str:
    """Render per-symbol quant statistics (rows are SummaryStats.as_dict + symbol)."""
    header = "| " + " | ".join(c[1] for c in _QUANT_COLS) + " |"
    sep = "| " + " | ".join("---" for _ in _QUANT_COLS) + " |"
    out = [header, sep]
    for r in rows:
        cells = []
        for key, _label, places in _QUANT_COLS:
            v = r.get(key)
            cells.append(_md_escape(str(v)) if key == "symbol" else _fmt_num(v, places))
        out.append("| " + " | ".join(cells) + " |")
    if not rows:
        out.append("| _no symbols with enough history_ |" + " |" * (len(_QUANT_COLS) - 1))
    return "\n".join(out)


_LEADER_COLS = [
    ("symbol", "Symbol", 0),
    ("strategy", "Strategy", 0),
    ("total_return_pct", "Return%", 2),
    ("cagr_pct", "CAGR%", 2),
    ("sharpe", "Sharpe", 2),
    ("max_drawdown_pct", "MaxDD%", 2),
    ("win_rate_pct", "Win%", 2),
    ("num_trades", "Trades", 0),
    ("exposure_pct", "Expo%", 2),
]


def leaderboard_md(rows: list[dict], limit: int = 25) -> str:
    """Render a backtest leaderboard (rows are ScreenRow.as_dict)."""
    header = "| " + " | ".join(c[1] for c in _LEADER_COLS) + " |"
    sep = "| " + " | ".join("---" for _ in _LEADER_COLS) + " |"
    out = [header, sep]
    for r in rows[:limit]:
        cells = []
        for key, _label, places in _LEADER_COLS:
            v = r.get(key)
            cells.append(
                _md_escape(str(v)) if key in ("symbol", "strategy") else _fmt_num(v, places)
            )
        out.append("| " + " | ".join(cells) + " |")
    if not rows:
        out.append("| _no backtests run_ |" + " |" * (len(_LEADER_COLS) - 1))
    return "\n".join(out)
