"""Valuation filters over dated, locally stored fundamentals."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from nepse_trader.models import FundamentalData


def filter_symbols(symbols: Sequence[str], snapshots: Mapping[str, FundamentalData], *,
                   max_pe: float | None = None, max_pbv: float | None = None,
                   min_eps: float | None = None, sector: str | None = None) -> list[str]:
    if max_pe is None and max_pbv is None and min_eps is None and not sector:
        return list(symbols)
    if (max_pe is not None and max_pe <= 0) or (max_pbv is not None and max_pbv <= 0):
        raise ValueError("Valuation limits must be positive.")
    result = []
    for symbol in symbols:
        data = snapshots.get(symbol)
        if data is None:
            continue
        if max_pe is not None and (data.pe_ratio is None or not 0 < data.pe_ratio <= max_pe):
            continue
        if max_pbv is not None and (data.pbv is None or not 0 < data.pbv <= max_pbv):
            continue
        if min_eps is not None and (data.eps is None or data.eps < min_eps):
            continue
        if sector and data.sector.casefold() != sector.casefold():
            continue
        result.append(symbol)
    return result
