"""Chukul JSON source adapter.

Chukul (https://chukul.com) is powered by a versioned JSON backend at
``api.chukul.com/v1/``. The exact endpoint paths are UNVERIFIED, so this client
is fully CONFIG-DRIVEN: endpoint URLs come from ``source_spec.endpoints``
(``live`` / ``stock`` / ``index``) when provided, falling back to inferred
defaults otherwise.

Payload shapes also vary, so parsing tolerates a bare JSON list, a
``{"data": [...]}`` envelope, or a ``{"results": [...]}`` envelope, and maps
record keys flexibly (case-insensitively) across the many naming conventions
different snapshots have used.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

from nepse_trader.config import SourceSpec
from nepse_trader.ingest.base import BaseClient, SourceClient
from nepse_trader.models import IndexValue, PriceBar, SourceName

_DEFAULT_LIVE_URL = "https://api.chukul.com/v1/market/live/"
_DEFAULT_STOCK_URL = "https://api.chukul.com/v1/stock/"
_DEFAULT_INDEX_URL = "https://api.chukul.com/v1/market/index/"


def _num(value: Any) -> float | None:
    """Coerce a JSON value (number or comma/percent string) to float, else None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip().replace(",", "").replace("%", "")
        if not text or text in {"-", "--", "N/A", "n/a", "NA"}:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _int(value: Any) -> int | None:
    parsed = _num(value)
    if parsed is None:
        return None
    return int(parsed)


def _pick(d: dict[str, Any], *keys: str, cast: Callable[[Any], Any] | None = None) -> Any:
    """Return the first present key's value (case-insensitive), optionally cast.

    Keys are matched case-insensitively against the dict's keys. ``None`` values
    are treated as absent so a later alias can win.
    """
    lowered = {k.lower(): k for k in d if isinstance(k, str)}
    for key in keys:
        actual = lowered.get(key.lower())
        if actual is None:
            continue
        raw = d[actual]
        if raw is None:
            continue
        return cast(raw) if cast is not None else raw
    return None


def _as_records(payload: Any) -> list[dict[str, Any]]:
    """Normalise list / {data:[...]} / {results:[...]} into a list of dicts."""
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = payload.get("data")
        if rows is None:
            rows = payload.get("results")
        if rows is None:
            rows = []
    else:
        rows = []
    return [r for r in rows if isinstance(r, dict)]


class ChukulClient(SourceClient):
    """Config-driven Chukul JSON adapter (paths inferred; verify via HAR)."""

    name: SourceName = SourceName.CHUKUL

    def __init__(
        self,
        client: BaseClient | None = None,
        source_spec: SourceSpec | None = None,
    ) -> None:
        self.client = client or BaseClient()
        self.source_spec = source_spec

    # ---- URL resolution (config-driven with inferred defaults) ----

    def _endpoint_url(self, key: str, default: str) -> str | None:
        if self.source_spec is not None:
            ep = self.source_spec.endpoints.get(key)
            if ep is not None and ep.url:
                return ep.url
        return default

    @property
    def prices_url(self) -> str | None:
        # Prefer the configured/inferred live board; fall back to the stock endpoint.
        live = None
        stock = None
        if self.source_spec is not None:
            live_ep = self.source_spec.endpoints.get("live")
            stock_ep = self.source_spec.endpoints.get("stock")
            live = live_ep.url if live_ep and live_ep.url else None
            stock = stock_ep.url if stock_ep and stock_ep.url else None
        return live or stock or _DEFAULT_LIVE_URL or _DEFAULT_STOCK_URL

    @property
    def index_url(self) -> str | None:
        return self._endpoint_url("index", _DEFAULT_INDEX_URL)

    # ---- Pure parsers (no network) ----

    @staticmethod
    def parse_prices(
        payload: Any,
        business_date: date,
        source: SourceName = SourceName.CHUKUL,
    ) -> list[PriceBar]:
        """Map a flexible JSON payload into PriceBars.

        Accepts a list, ``{"data": [...]}`` or ``{"results": [...]}``. Record
        keys are matched case-insensitively across known aliases. Rows without a
        symbol are skipped. Returns ``[]`` if the shape is unexpected.
        """
        bars: list[PriceBar] = []
        for row in _as_records(payload):
            symbol = _pick(row, "symbol", "ticker", "scrip", "stock", "scrip_name")
            if symbol is None or not str(symbol).strip():
                continue
            close = _pick(
                row, "ltp", "last_price", "lastTradedPrice", "last_traded_price",
                "close", "closing_price", cast=_num,
            )
            bars.append(
                PriceBar(
                    symbol=str(symbol).strip(),
                    business_date=business_date,
                    open=_pick(row, "open", "open_price", "opening_price", cast=_num),
                    high=_pick(row, "high", "high_price", "day_high", cast=_num),
                    low=_pick(row, "low", "low_price", "day_low", cast=_num),
                    close=close,
                    previous_close=_pick(
                        row, "previous_close", "prevClose", "prev_close",
                        "previousclose", "yesterday_price", cast=_num,
                    ),
                    volume=_pick(
                        row, "volume", "qty", "quantity", "totalTradedQuantity",
                        "total_traded_quantity", "traded_shares", cast=_int,
                    ),
                    turnover=_pick(
                        row, "turnover", "amount", "traded_amount", "total_amount",
                        cast=_num,
                    ),
                    source=source,
                )
            )
        return bars

    @staticmethod
    def parse_indices(
        payload: Any,
        business_date: date,
        source: SourceName = SourceName.CHUKUL,
    ) -> list[IndexValue]:
        """Map a flexible JSON payload into IndexValues (name + value)."""
        out: list[IndexValue] = []
        for row in _as_records(payload):
            name = _pick(row, "name", "index", "index_name", "title", "label")
            value = _pick(
                row, "value", "close", "current", "index_value", "ltp", "points",
                cast=_num,
            )
            if name is None or not str(name).strip() or value is None:
                continue
            out.append(
                IndexValue(
                    name=str(name).strip(),
                    business_date=business_date,
                    value=value,
                    change=_pick(row, "change", "point_change", "diff", cast=_num),
                    change_percent=_pick(
                        row, "change_percent", "percent_change", "perc_change",
                        "changePercent", "percent", cast=_num,
                    ),
                    source=source,
                )
            )
        return out

    # ---- Fetchers (network; failures -> []) ----

    def fetch_prices(self, business_date: date | None = None) -> list[PriceBar]:
        bd = business_date or date.today()
        url = self.prices_url
        if not url:
            return []
        try:
            result = self.client.fetch(url)
            payload = result.json()
        except Exception:
            return []
        try:
            return self.parse_prices(payload, bd, self.name)
        except Exception:
            return []

    def fetch_indices(self, business_date: date | None = None) -> list[IndexValue]:
        bd = business_date or date.today()
        url = self.index_url
        if not url:
            return []
        try:
            result = self.client.fetch(url)
            payload = result.json()
        except Exception:
            return []
        try:
            return self.parse_indices(payload, bd, self.name)
        except Exception:
            return []
