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
    "plan_cards_md",
    "sell_queue_md",
    "do_not_touch_md",
    "rashifal_md",
    "RASHIFAL_DISCLAIMER",
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
    """Pluggable alert backends: Telegram, Discord, SMTP, and generic webhook.

    Every method is **mockable**: tests monkeypatch the network call rather than
    reaching real endpoints. No new runtime dependencies beyond what's already
    installed.
    """

    def __init__(self, webhook_url: str | None = None):
        self.webhook_url = webhook_url

    def _post(self, payload: dict, url: str | None = None) -> httpx.Response:
        """Thin POST wrapper kept separate so tests can monkeypatch it."""
        return httpx.post(url or self.webhook_url, json=payload, timeout=10.0)

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

    # -- Telegram -----------------------------------------------------------

    @staticmethod
    def send_telegram(token: str, chat_id: str, text: str) -> bool:
        """Send a plain-text message via Telegram Bot API."""
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        try:
            resp = httpx.post(url, json=payload, timeout=15.0)
        except httpx.HTTPError:
            return False
        return resp.status_code == 200 and resp.json().get("ok") is True

    # -- Discord ------------------------------------------------------------

    @staticmethod
    def send_discord(webhook_url: str, text: str) -> bool:
        """Send a message to a Discord channel via webhook."""
        payload = {"content": text}
        try:
            resp = httpx.post(webhook_url, json=payload, timeout=15.0)
        except httpx.HTTPError:
            return False
        return resp.status_code in (200, 204)

    # -- SMTP / Email -------------------------------------------------------

    @staticmethod
    def send_email(
        smtp_host: str,
        smtp_port: int,
        from_addr: str,
        to_addr: str,
        subject: str,
        body: str,
        username: str | None = None,
        password: str | None = None,
        use_tls: bool = True,
    ) -> bool:
        """Send an email via SMTP. Returns True on success."""
        import smtplib
        from email.mime.text import MIMEText

        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to_addr
        try:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as server:
                if use_tls:
                    server.starttls()
                if username and password:
                    server.login(username, password)
                server.send_message(msg)
            return True
        except Exception:
            return False


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


# --------------------------------------------------------------------------
# Advisor / rashifal builders
# --------------------------------------------------------------------------

# Printed on every advisor report. The format is a horoscope; the method is not,
# and a report shaped like a horoscope has an obligation to say so out loud.
RASHIFAL_DISCLAIMER = (
    "_The daily-horoscope format is borrowed for readability only. **No astrological "
    "input feeds any number in this report.** Every price, stop, target, quantity and "
    "date is computed from reconciled price history by "
    "`nepse_trader.advisor.plan`. Commentary, where present, is written by a language "
    "model that can see those numbers but cannot change them. None of this is "
    "investment advice._"
)


def plan_cards_md(cards: list[dict]) -> str:
    """Render plan cards as one table row per symbol.

    Cards are ``PlanCard.as_dict()``. The columns are chosen so the row answers
    the question the user actually asked — what to buy, at what price, where the
    stop goes, how many shares, and the earliest date it can legally be sold.
    """
    cols = [
        ("symbol", "Symbol", 0),
        ("action", "Action", 0),
        ("conviction", "Conv", 0),
        ("reference_price", "Last", 2),
        ("entry_low", "Entry lo", 2),
        ("entry_high", "Entry hi", 2),
        ("stop", "Stop", 2),
        ("quantity", "Qty", 0),
        ("net_pnl", "Net PnL", 2),
    ]
    header = "| " + " | ".join(c[1] for c in cols) + " | T1 | T2 | Sell on/after |"
    sep = "| " + " | ".join("---" for _ in cols) + " | --- | --- | --- |"
    out = [header, sep]
    for c in cards:
        cells = []
        for key, _label, places in cols:
            v = c.get(key)
            cells.append(_md_escape(str(v)) if key in ("symbol", "action") else _fmt_num(v, places))
        targets = c.get("targets") or []
        cells.append(_fmt_num(targets[0] if targets else None))
        cells.append(_fmt_num(targets[1] if len(targets) > 1 else None))
        cells.append(_md_escape(str(c.get("earliest_sell_date", "-"))))
        out.append("| " + " | ".join(cells) + " |")
    if not cards:
        out.append("| _no actionable cards today_ |" + " |" * (len(cols) + 2))
    return "\n".join(out)


def sell_queue_md(rows: list[dict]) -> str:
    """Render the exit queue: what to sell, why, and the earliest legal date."""
    out = [
        "| Symbol | Qty | Price | Reason | Sell on/after |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        out.append(
            f"| {_md_escape(str(r.get('symbol', '')))} "
            f"| {_fmt_num(r.get('quantity'), 0)} "
            f"| {_fmt_num(r.get('reference_price'))} "
            f"| {_md_escape(str(r.get('reason', '')))} "
            f"| {_md_escape(str(r.get('earliest_sell_date', '-')))} |"
        )
    if not rows:
        out.append("| _nothing to exit_ |  |  |  |  |")
    return "\n".join(out)


def do_not_touch_md(rows: list[dict]) -> str:
    """Render the excluded symbols with their reasons.

    A symbol missing from the report without explanation looks like an oversight;
    a symbol listed here with "only 8 bars" is a fact the user can act on.
    """
    out = ["| Symbol | Why it was skipped |", "| --- | --- |"]
    for r in rows:
        out.append(
            f"| {_md_escape(str(r.get('symbol', '')))} | {_md_escape(str(r.get('reason', '')))} |"
        )
    if not rows:
        out.append("| _none — every requested symbol got a card_ |  |")
    return "\n".join(out)


def rashifal_md(result: dict) -> str:
    """Render a whole advisor run as Markdown.

    *result* is ``Rashifal.as_dict()``. Deliberately ordered worst-news-first for
    the banner: if the AI layer degraded, the reader learns that before reading
    anything it wrote.
    """
    cards = result.get("cards") or []
    buys = [c for c in cards if c.get("action") == "accumulate"]
    sections: list[str] = []

    if result.get("banner"):
        sections.append(f"> ⚠️ {_md_escape(str(result['banner']))}")

    header_rows = [
        ("Run date", str(result.get("run_date", "-"))),
        ("Mode", str(result.get("mode", "-"))),
        ("Connectivity", "online" if result.get("online") else "offline"),
        ("Horizon", str(result.get("horizon", "-"))),
        ("Market regime", str(result.get("regime", "-"))),
        ("Sector of the day", str(result.get("sector_of_the_day", "-"))),
        ("Equity assumed (NPR)", _fmt_num(result.get("equity"), 0)),
        ("Cards", _fmt_num(len(cards), 0)),
    ]
    sections.append(
        "\n".join(
            ["| Field | Value |", "| --- | --- |"]
            + [f"| {k} | {_md_escape(str(v))} |" for k, v in header_rows]
        )
    )

    if result.get("thesis"):
        sections.append("### This week's thesis\n\n" + str(result["thesis"]))

    sections.append("### Buy candidates\n\n" + plan_cards_md(buys))

    others = [c for c in cards if c.get("action") != "accumulate"]
    if others:
        sections.append("### Hold / reduce\n\n" + plan_cards_md(others))

    sections.append("### Sell queue\n\n" + sell_queue_md(result.get("sell_queue") or []))
    sections.append("### Do not touch\n\n" + do_not_touch_md(result.get("do_not_touch") or []))

    notes = [c for c in cards if c.get("note")]
    if notes:
        body = "\n\n".join(
            f"**{_md_escape(str(c.get('symbol', '')))}** — {str(c['note'])}" for c in notes
        )
        sections.append("### Commentary\n\n" + body)

    sections.append(RASHIFAL_DISCLAIMER)
    return "\n\n".join(sections)
