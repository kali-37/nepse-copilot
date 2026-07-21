"""Cross-source reconciliation.

The whole point of pulling the same NEPSE data from several sites is to trust it
more: if ShareSansar, MeroLagani and Chukul all report KHPL closing at 512.00,
that's "genuine". If they disagree, we flag it rather than silently picking one.

reconcile_bars() groups PriceBars by (symbol, business_date) and, per numeric
field, finds the largest cluster of source values that agree within a relative
tolerance. The agreed value is the cluster mean; sources outside every consensus
mark the field "disputed". `confidence` is the share of present sources that
agree on the close.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from nepse_trader.models import CorporateAction, PriceBar, ReconciledPrice, SourceName

_NUMERIC_FIELDS = ("open", "high", "low", "close", "previous_close", "volume", "turnover")


def _consensus(
    values: list[tuple[SourceName, float]], tolerance: float
) -> tuple[float | None, list[SourceName], bool]:
    """Return (agreed_value, agreeing_sources, disputed).

    Greedy clustering: for each candidate value, gather all values within
    `tolerance` relative distance; the largest such cluster wins. `disputed` is
    True when at least one present value falls outside the winning cluster.
    """
    present = [(s, v) for s, v in values if v is not None]
    if not present:
        return None, [], False
    if len(present) == 1:
        return present[0][1], [present[0][0]], False

    best_cluster: list[tuple[SourceName, float]] = []
    for _, anchor in present:
        cluster = [(s, v) for s, v in present if _within(anchor, v, tolerance)]
        if len(cluster) > len(best_cluster):
            best_cluster = cluster

    agreed = sum(v for _, v in best_cluster) / len(best_cluster)
    agreeing = [s for s, _ in best_cluster]
    disputed = len(best_cluster) < len(present)
    return agreed, agreeing, disputed


def _within(a: float, b: float, tolerance: float) -> bool:
    if a == b:
        return True
    denom = max(abs(a), abs(b), 1e-9)
    return abs(a - b) / denom <= tolerance


def reconcile_bars(bars: Iterable[PriceBar], tolerance: float = 0.005) -> list[ReconciledPrice]:
    grouped: dict[tuple[str, object], list[PriceBar]] = defaultdict(list)
    for b in bars:
        grouped[(b.symbol, b.business_date)].append(b)

    out: list[ReconciledPrice] = []
    for (symbol, business_date), group in grouped.items():
        present_sources = sorted({b.source for b in group}, key=lambda s: s.value)
        field_values: dict[str, float | None] = {}
        disputed_fields: list[str] = []
        close_agreeing: list[SourceName] = []

        for field in _NUMERIC_FIELDS:
            pairs = [(b.source, getattr(b, field)) for b in group if getattr(b, field) is not None]
            agreed, agreeing, disputed = _consensus(pairs, tolerance)
            field_values[field] = agreed
            if disputed:
                disputed_fields.append(field)
            if field == "close":
                close_agreeing = agreeing

        # Deduplicate agreeing sources — a source cannot agree more than once.
        close_agreeing = sorted({s for s in close_agreeing}, key=lambda s: s.value)
        confidence = len(close_agreeing) / len(present_sources) if present_sources else 0.0
        out.append(
            ReconciledPrice(
                symbol=symbol,
                business_date=business_date,  # type: ignore[arg-type]
                open=field_values["open"],
                high=field_values["high"],
                low=field_values["low"],
                close=field_values["close"],
                previous_close=field_values["previous_close"],
                volume=int(field_values["volume"]) if field_values["volume"] is not None else None,
                turnover=field_values["turnover"],
                sources_agreeing=close_agreeing,
                sources_present=present_sources,
                disputed_fields=disputed_fields,
                confidence=round(confidence, 4),
            )
        )
    out.sort(key=lambda r: (r.symbol, r.business_date))
    return out


def adjust_prices(
    prices: list[ReconciledPrice],
    actions: list[CorporateAction],
) -> list[ReconciledPrice]:
    """Back-adjust reconciled closes by corporate action factors.

    For each symbol, walks chronological prices and applies cumulative
    adjustment factors from corporate actions (Yahoo Finance convention:
    pre-event prices are multiplied by the factor so the series is
    continuous at the ex-date).
    """
    if not actions:
        for p in prices:
            p.adjusted_close = p.close
        return prices

    actions_by_symbol: dict[str, list[CorporateAction]] = {}
    for ca in actions:
        actions_by_symbol.setdefault(ca.symbol, []).append(ca)

    for symbol in {p.symbol for p in prices}:
        cas = sorted(
            actions_by_symbol.get(symbol, []),
            key=lambda ca: ca.ex_date,
        )
        if not cas:
            for p in prices:
                if p.symbol == symbol:
                    p.adjusted_close = p.close
            continue

        sym_prices = sorted(
            [p for p in prices if p.symbol == symbol],
            key=lambda p: p.business_date,
        )
        idx = 0
        for p in sym_prices:
            while idx < len(cas) and p.business_date >= cas[idx].ex_date:
                idx += 1
            factor = 1.0
            for j in range(idx, len(cas)):
                factor *= float(cas[j].factor)
            p.adjusted_close = round(p.close * factor, 2) if p.close is not None else None

    return prices
