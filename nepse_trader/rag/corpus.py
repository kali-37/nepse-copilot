"""Documents: the retrievable unit, plus builders that derive them from the DB.

A :class:`Document` is a short, self-contained, human-readable statement of fact
with a stable id. Prices, indicators, reconciliation quality, fundamentals,
corporate actions and news all collapse into the same shape so one index and one
retriever serve them all.

Two properties matter and are enforced here:

**Deterministic ids.** ``doc_id`` is derived from (kind, symbol, date), never from
a counter or a timestamp, so re-indexing the same day upserts rather than
duplicating.

**Text, not JSON.** Bodies are written as prose an LLM can quote and a human can
read in a report. That keeps the same corpus useful in Normal mode, where nothing
calls an LLM at all.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime

from nepse_trader.analysis import indicators as ind
from nepse_trader.analysis.quant import summary_stats
from nepse_trader.models import (
    CorporateAction,
    FundamentalData,
    PriceBar,
    ReconciledPrice,
    Signal,
)

# Document kinds. Retrieval can filter on these.
KIND_PRICE = "price"
KIND_INDICATOR = "indicator"
KIND_QUANT = "quant"
KIND_SIGNAL = "signal"
KIND_RECONCILE = "reconcile"
KIND_FUNDAMENTAL = "fundamental"
KIND_CORPORATE_ACTION = "corporate_action"
KIND_NEWS = "news"
KIND_REPORT = "report"
KIND_WEB = "web"

ALL_KINDS = (
    KIND_PRICE,
    KIND_INDICATOR,
    KIND_QUANT,
    KIND_SIGNAL,
    KIND_RECONCILE,
    KIND_FUNDAMENTAL,
    KIND_CORPORATE_ACTION,
    KIND_NEWS,
    KIND_REPORT,
    KIND_WEB,
)


@dataclass
class Document:
    """One retrievable fact or article."""

    doc_id: str
    kind: str
    title: str
    body: str
    symbol: str | None = None
    business_date: date | None = None
    url: str | None = None
    source: str | None = None
    fetched_at: datetime | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    def as_row(self) -> tuple:
        """Positional tuple matching the ``documents`` table column order."""
        return (
            self.doc_id,
            self.kind,
            self.symbol,
            self.business_date.isoformat() if self.business_date else None,
            self.title,
            self.body,
            self.url,
            self.source,
            self.fetched_at.isoformat() if self.fetched_at else None,
        )


def _doc_id(kind: str, *parts: object) -> str:
    """Stable id from the identifying parts. Re-indexing upserts, never dupes."""
    tail = ":".join(str(p) for p in parts if p is not None)
    return f"{kind}:{tail}" if tail else kind


def _fmt(value: float | int | None, places: int = 2) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:,.{places}f}"
    return f"{value:,}"


# ---------------------------------------------------------------------------
# Builders — DB rows in, Documents out. All pure.
# ---------------------------------------------------------------------------


def price_document(bar: PriceBar | ReconciledPrice) -> Document:
    """A single day's OHLCV as prose."""
    change = None
    if bar.close is not None and bar.previous_close:
        change = (bar.close - bar.previous_close) / bar.previous_close * 100.0

    body = (
        f"On {bar.business_date.isoformat()}, {bar.symbol} closed at "
        f"NPR {_fmt(bar.close)}"
    )
    if change is not None:
        direction = "up" if change > 0 else "down" if change < 0 else "flat"
        body += f", {direction} {_fmt(abs(change))}% from NPR {_fmt(bar.previous_close)}"
    body += (
        f". Open NPR {_fmt(bar.open)}, high NPR {_fmt(bar.high)}, "
        f"low NPR {_fmt(bar.low)}. Volume {_fmt(bar.volume, 0)} shares, "
        f"turnover NPR {_fmt(bar.turnover, 0)}."
    )
    if isinstance(bar, ReconciledPrice):
        body += (
            f" Cross-source confidence {_fmt(bar.confidence, 2)} from "
            f"{len(bar.sources_present)} source(s)."
        )

    return Document(
        doc_id=_doc_id(KIND_PRICE, bar.symbol, bar.business_date),
        kind=KIND_PRICE,
        title=f"{bar.symbol} price on {bar.business_date.isoformat()}",
        body=body,
        symbol=bar.symbol,
        business_date=bar.business_date,
        source=getattr(getattr(bar, "source", None), "value", None),
    )


def indicator_document(symbol: str, bars: Sequence[PriceBar]) -> Document | None:
    """Latest reading of every indicator, with its interpretation stated."""
    closes = [b.close for b in bars if b.close is not None]
    if len(closes) < 2:
        return None
    highs = [b.high if b.high is not None else b.close for b in bars if b.close is not None]
    lows = [b.low if b.low is not None else b.close for b in bars if b.close is not None]
    as_of = bars[-1].business_date

    last = closes[-1]
    sma20 = ind.latest(ind.sma(closes, 20))
    sma50 = ind.latest(ind.sma(closes, 50))
    sma200 = ind.latest(ind.sma(closes, 200))
    rsi14 = ind.latest(ind.rsi(closes, 14))
    macd_line, signal_line, hist = ind.macd(closes)
    atr14 = ind.latest(ind.atr(highs, lows, closes, 14))
    upper, middle, lower = ind.bollinger_bands(closes)

    parts = [
        f"{symbol} technical readings as of {as_of.isoformat()} "
        f"(close NPR {_fmt(last)}):"
    ]
    if sma20 is not None:
        parts.append(
            f"SMA20 {_fmt(sma20)} — price is "
            f"{'above' if last > sma20 else 'below'} it."
        )
    if sma50 is not None:
        parts.append(
            f"SMA50 {_fmt(sma50)} — price is "
            f"{'above' if last > sma50 else 'below'} it."
        )
    if sma200 is not None:
        parts.append(
            f"SMA200 {_fmt(sma200)} — long-term trend is "
            f"{'up' if last > sma200 else 'down'}."
        )
    if sma20 is not None and sma50 is not None:
        parts.append(
            "SMA20 is above SMA50 (bullish alignment)."
            if sma20 > sma50
            else "SMA20 is below SMA50 (bearish alignment)."
        )
    if rsi14 is not None:
        zone = "overbought" if rsi14 >= 70 else "oversold" if rsi14 <= 30 else "neutral"
        parts.append(f"RSI(14) {_fmt(rsi14)} — {zone}.")
    m, s, h = ind.latest(macd_line), ind.latest(signal_line), ind.latest(hist)
    if m is not None and s is not None:
        parts.append(
            f"MACD {_fmt(m)} vs signal {_fmt(s)}, histogram {_fmt(h)} — "
            f"{'bullish' if h is not None and h > 0 else 'bearish'} momentum."
        )
    if atr14 is not None:
        atr_pct = atr14 / last * 100.0 if last else None
        parts.append(
            f"ATR(14) {_fmt(atr14)} ({_fmt(atr_pct)}% of price) — "
            "this is the daily range to size stops against."
        )
    ub, lb = ind.latest(upper), ind.latest(lower)
    if ub is not None and lb is not None:
        parts.append(f"Bollinger band {_fmt(lb)}–{_fmt(ub)} (mid {_fmt(ind.latest(middle))}).")

    return Document(
        doc_id=_doc_id(KIND_INDICATOR, symbol, as_of),
        kind=KIND_INDICATOR,
        title=f"{symbol} indicators on {as_of.isoformat()}",
        body=" ".join(parts),
        symbol=symbol,
        business_date=as_of,
    )


def quant_document(
    symbol: str, bars: Sequence[PriceBar], periods_per_year: int = 244
) -> Document | None:
    """Risk/return profile over the available history."""
    closes = [b.close for b in bars if b.close is not None]
    if len(closes) < 2:
        return None
    as_of = bars[-1].business_date
    stats = summary_stats(closes, periods_per_year=periods_per_year)
    body = (
        f"{symbol} risk and return over {stats.n} trading days to "
        f"{as_of.isoformat()}: total return {_fmt(stats.total_return_pct)}%, "
        f"annualised return {_fmt(stats.annualized_return_pct)}%, "
        f"annualised volatility {_fmt(stats.annualized_vol_pct)}%, "
        f"Sharpe {_fmt(stats.sharpe)}, Sortino {_fmt(stats.sortino)}, "
        f"maximum drawdown {_fmt(stats.max_drawdown_pct)}%, "
        f"95% one-day VaR {_fmt(stats.var_95_pct)}%, "
        f"return skew {_fmt(stats.skewness)}, excess kurtosis {_fmt(stats.kurtosis)}."
    )
    return Document(
        doc_id=_doc_id(KIND_QUANT, symbol, as_of),
        kind=KIND_QUANT,
        title=f"{symbol} risk profile to {as_of.isoformat()}",
        body=body,
        symbol=symbol,
        business_date=as_of,
    )


def signal_document(signal: Signal) -> Document:
    """One strategy's verdict for one symbol on one day."""
    body = (
        f"Strategy '{signal.strategy}' says {signal.action.value} on "
        f"{signal.symbol} for {signal.business_date.isoformat()} at "
        f"NPR {_fmt(signal.price)}, conviction {_fmt(signal.strength)} of 1.0."
    )
    if signal.reason:
        body += f" Reason: {signal.reason}."
    if signal.indicators:
        readings = ", ".join(f"{k}={_fmt(v)}" for k, v in sorted(signal.indicators.items()))
        body += f" Inputs: {readings}."
    return Document(
        doc_id=_doc_id(KIND_SIGNAL, signal.symbol, signal.business_date, signal.strategy),
        kind=KIND_SIGNAL,
        title=f"{signal.symbol} {signal.strategy} signal {signal.business_date.isoformat()}",
        body=body,
        symbol=signal.symbol,
        business_date=signal.business_date,
    )


def reconcile_document(price: ReconciledPrice) -> Document:
    """Data-quality statement: how much to trust this price."""
    agreeing = ", ".join(s.value for s in price.sources_agreeing) or "none"
    present = ", ".join(s.value for s in price.sources_present) or "none"
    verdict = "trustworthy" if price.is_trustworthy else "NOT trustworthy — treat with caution"
    body = (
        f"Data quality for {price.symbol} on {price.business_date.isoformat()}: "
        f"confidence {_fmt(price.confidence, 2)}, judged {verdict}. "
        f"Sources present: {present}. Sources agreeing on close: {agreeing}."
    )
    if price.disputed_fields:
        body += f" Disputed fields: {', '.join(price.disputed_fields)}."
    return Document(
        doc_id=_doc_id(KIND_RECONCILE, price.symbol, price.business_date),
        kind=KIND_RECONCILE,
        title=f"{price.symbol} data quality {price.business_date.isoformat()}",
        body=body,
        symbol=price.symbol,
        business_date=price.business_date,
    )


def fundamental_document(data: FundamentalData, as_of: date | None = None) -> Document:
    """Valuation snapshot."""
    body = f"{data.symbol}"
    if data.company_name:
        body += f" ({data.company_name})"
    if data.sector:
        body += f", sector {data.sector}"
    body += (
        f": market price NPR {_fmt(data.market_price)}, EPS {_fmt(data.eps)}, "
        f"P/E {_fmt(data.pe_ratio)}, book value {_fmt(data.book_value)}, "
        f"P/BV {_fmt(data.pbv)}, dividend {_fmt(data.dividend_pct)}%, "
        f"market cap NPR {_fmt(data.market_cap, 0)}, "
        f"52-week range {_fmt(data.low_52w)}–{_fmt(data.high_52w)}, "
        f"30-day average volume {_fmt(data.avg_volume_30d, 0)}."
    )
    when = as_of or (data.fetched_at.date() if data.fetched_at else None)
    return Document(
        doc_id=_doc_id(KIND_FUNDAMENTAL, data.symbol, when),
        kind=KIND_FUNDAMENTAL,
        title=f"{data.symbol} fundamentals",
        body=body,
        symbol=data.symbol,
        business_date=when,
        fetched_at=data.fetched_at,
    )


def corporate_action_document(action: CorporateAction) -> Document:
    """A bonus/rights/split/dividend event and its price effect."""
    body = (
        f"{action.symbol} {action.action_type.value} "
        f"{action.ratio_numerator}:{action.ratio_denominator} with ex-date "
        f"{action.ex_date.isoformat()}. Prices before the ex-date are multiplied "
        f"by {action.factor} to stay comparable."
    )
    if action.notes:
        body += f" Note: {action.notes}."
    return Document(
        doc_id=_doc_id(
            KIND_CORPORATE_ACTION, action.symbol, action.ex_date, action.action_type.value
        ),
        kind=KIND_CORPORATE_ACTION,
        title=f"{action.symbol} {action.action_type.value} ex-{action.ex_date.isoformat()}",
        body=body,
        symbol=action.symbol,
        business_date=action.ex_date,
        source=action.source.value,
    )


def breadth_document(breadth: dict) -> Document | None:
    """Whole-market tone for a date."""
    bd = breadth.get("business_date")
    if not bd:
        return None
    when = date.fromisoformat(bd) if isinstance(bd, str) else bd
    adv = breadth.get("advancers") or 0
    dec = breadth.get("decliners") or 0
    tone = "broadly positive" if adv > dec else "broadly negative" if dec > adv else "mixed"
    body = (
        f"Market breadth on {when.isoformat()} was {tone}: {adv} advancers versus "
        f"{dec} decliners and {breadth.get('unchanged') or 0} unchanged across "
        f"{breadth.get('symbols') or 0} symbols. Total turnover NPR "
        f"{_fmt(breadth.get('total_turnover'), 0)}. Average cross-source "
        f"confidence {_fmt(breadth.get('avg_confidence'), 3)} with "
        f"{breadth.get('disputed') or 0} low-confidence or disputed rows."
    )
    return Document(
        doc_id=_doc_id("breadth", when),
        kind=KIND_REPORT,
        title=f"Market breadth {when.isoformat()}",
        body=body,
        business_date=when,
    )


def build_symbol_documents(
    symbol: str,
    bars: Sequence[PriceBar],
    *,
    recent_days: int = 10,
    periods_per_year: int = 244,
) -> list[Document]:
    """Every document derivable for one symbol from its bar history.

    Only the most recent ``recent_days`` price documents are emitted — older
    prices add index weight without adding decision value, and the quant document
    already summarises the full history.
    """
    docs: list[Document] = []
    if not bars:
        return docs

    for bar in bars[-recent_days:]:
        docs.append(price_document(bar))

    doc = indicator_document(symbol, bars)
    if doc:
        docs.append(doc)
    doc = quant_document(symbol, bars, periods_per_year=periods_per_year)
    if doc:
        docs.append(doc)
    return docs


def iter_documents(docs: Iterable[Document | None]) -> list[Document]:
    """Drop the ``None`` results that builders return for thin data."""
    return [d for d in docs if d is not None]
