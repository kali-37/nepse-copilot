"""NepseAlpha ingestion client — TradingView UDF format.

NepseAlpha (https://www.nepsealpha.com) exposes a TradingView-compatible UDF
(Unified Data Feed) JSON backend. Historical price data is fetched via the
``/api/tradingview/history`` endpoint and parsed into PriceBar records.

Endpoint URLs are config-driven (``source_spec.endpoints``) with a fallback.
Design follows the project convention: pure ``parse_*`` staticmethods + thin
``fetch_*`` wrappers that degrade to ``[]`` on error.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import httpx

from nepse_trader.ingest.base import BaseClient, FetchError, RateLimitedError, SourceClient
from nepse_trader.models import PriceBar, SourceName

_DEFAULT_HISTORY_URL = "https://www.nepsealpha.com/api/tradingview/history"
_DEFAULT_SYMBOL_URL = "https://www.nepsealpha.com/api/tradingview/symbols"
_DEFAULT_CONFIG_URL = "https://www.nepsealpha.com/api/tradingview/config"


class NepseAlphaClient(SourceClient):
    """Client for NepseAlpha's TradingView UDF datafeed."""

    name = SourceName.NEPSEALPHA

    def __init__(
        self,
        client: BaseClient | None = None,
        source_spec: Any | None = None,
    ):
        self.client = client if client is not None else BaseClient()
        self.source_spec = source_spec
        self._history_url = self._endpoint_url("history", _DEFAULT_HISTORY_URL)
        self._symbol_url = self._endpoint_url("symbols", _DEFAULT_SYMBOL_URL)

    def _endpoint_url(self, key: str, fallback: str) -> str:
        if self.source_spec is not None:
            eps = getattr(self.source_spec, "endpoints", {})
            if key in eps:
                return eps[key].url
        return fallback

    # -- parsers (pure) -----------------------------------------------------

    @staticmethod
    def parse_bars(payload: dict, source: SourceName = SourceName.NEPSEALPHA) -> list[PriceBar]:
        """Parse TradingView UDF history JSON into PriceBar records.

        Expected payload shape (UDF format)::

            {"s": "ok", "t": [ts, ...], "o": [...], "h": [...],
             "l": [...], "c": [...], "v": [...]}

        Each index across arrays corresponds to one bar.  ``t`` values are
        Unix seconds (or milliseconds — handled either way).
        """
        if not isinstance(payload, dict) or payload.get("s") != "ok":
            return []
        timestamps = payload.get("t") or []
        opens = payload.get("o") or []
        highs = payload.get("h") or []
        lows = payload.get("l") or []
        closes = payload.get("c") or []
        volumes = payload.get("v") or []

        if not timestamps:
            return []

        bars: list[PriceBar] = []
        n = len(timestamps)
        for i in range(n):
            ts = timestamps[i]
            # Normalise seconds vs milliseconds.
            if isinstance(ts, (int, float)):
                if ts > 1e12:
                    ts = ts / 1000.0
                bdate = datetime.fromtimestamp(ts, tz=UTC).date()
            else:
                continue

            bars.append(
                PriceBar(
                    symbol="",
                    business_date=bdate,
                    open=opens[i] if i < len(opens) else None,
                    high=highs[i] if i < len(highs) else None,
                    low=lows[i] if i < len(lows) else None,
                    close=closes[i] if i < len(closes) else None,
                    volume=int(volumes[i]) if i < len(volumes) and volumes[i] is not None else None,
                    source=source,
                )
            )
        return bars

    # -- fetchers (network; failures degrade to []) -------------------------

    def fetch_bars(self, symbol: str, resolution: str = "D") -> list[PriceBar]:
        """Fetch daily price bars for *symbol* from the UDF history endpoint.

        The endpoint expects ``symbol``, ``resolution`` (``"D"`` for daily),
        and optional ``from`` / ``to`` Unix timestamps.  By default we let
        the server return all available history.
        """
        params: dict[str, Any] = {"symbol": symbol, "resolution": resolution}
        try:
            result = self.client.fetch(self._history_url, params=params)
            payload = result.json()
        except (FetchError, RateLimitedError, ValueError, httpx.TransportError):
            return []
        bars = self.parse_bars(payload, self.name)
        for bar in bars:
            bar.symbol = symbol.upper()
            bar.fetched_at = result.fetched_at if hasattr(result, "fetched_at") else None
        return bars

    def fetch_prices(self, business_date: date | None = None) -> list[PriceBar]:
        """NepseAlpha is supplementary and doesn't support whole-market fetch.

        Returns an empty list — use ``fetch_bars(symbol)`` for per-symbol data
        or rely on ShareSansar for the full daily market snapshot.
        """
        return []
