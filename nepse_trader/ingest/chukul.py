"""Chukul JSON source adapter.

The public live board at ``chukul.com/api/data/v2/live-market/`` and raw history
at ``live.chukul.com/api/data/historydata/data/`` were observed in its frontend
and verified on 2026-11-19. Configured URLs take precedence. Published timestamps
are converted to Nepal dates; requested dates never relabel a current board.

Payload shapes also vary, so parsing tolerates a bare JSON list, a
``{"data": [...]}`` envelope, or a ``{"results": [...]}`` envelope, and maps
record keys flexibly (case-insensitively) across the many naming conventions
different snapshots have used.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from nepse_trader.config import SourceSpec
from nepse_trader.ingest.base import BaseClient, SourceClient
from nepse_trader.models import FloorsheetEntry, IndexValue, PriceBar, SourceName

_DEFAULT_LIVE_URL = "https://chukul.com/api/data/v2/live-market/"
_DEFAULT_STOCK_URL = _DEFAULT_LIVE_URL
_DEFAULT_INDEX_URL = None
_DEFAULT_HISTORY_URL = "https://live.chukul.com/api/data/historydata/data/"
_NPT = ZoneInfo("Asia/Kathmandu")


def _num(value: Any) -> float | None:
    """Coerce a JSON value (number or comma/percent string) to float, else None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) else None
    if isinstance(value, str):
        text = value.strip().replace(",", "").replace("%", "")
        if not text or text in {"-", "--", "N/A", "n/a", "NA"}:
            return None
        try:
            number = float(text)
            return number if math.isfinite(number) else None
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
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


class ChukulClient(SourceClient):
    """Config-driven adapter for Chukul's public prices and raw history."""

    name: SourceName = SourceName.CHUKUL

    def __init__(
        self,
        client: BaseClient | None = None,
        source_spec: SourceSpec | None = None,
    ) -> None:
        self.client = client or BaseClient()
        self.source_spec = source_spec

    # ---- URL resolution (config-driven with inferred defaults) ----

    def _endpoint_url(self, key: str, default: str | None) -> str | None:
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
        *,
        require_source_date: bool = False,
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
            timestamp = _pick(row, "timestamp", cast=_num)
            source_date = None
            try:
                if timestamp is not None:
                    source_date = datetime.fromtimestamp(timestamp / 1000 if timestamp > 1e12 else timestamp, _NPT).date()
                elif _pick(row, "business_date", "date"):
                    source_date = date.fromisoformat(str(_pick(row, "business_date", "date"))[:10])
            except (ValueError, OverflowError, OSError):
                continue
            if require_source_date and source_date is None:
                continue
            close = _pick(
                row,
                "ltp",
                "last_price",
                "lastTradedPrice",
                "last_traded_price",
                "close",
                "closing_price",
                cast=_num,
            )
            previous = _pick(row, "previous_close", "prevClose", "prev_close", "previousclose", "yesterday_price", cast=_num)
            change = _pick(row, "point_change", cast=_num)
            if previous is None and close is not None and change is not None:
                previous = close - change
            bars.append(
                PriceBar(
                    symbol=str(symbol).strip(),
                    business_date=source_date or business_date,
                    open=_pick(row, "open", "open_price", "opening_price", cast=_num),
                    high=_pick(row, "high", "high_price", "day_high", cast=_num),
                    low=_pick(row, "low", "low_price", "day_low", cast=_num),
                    close=close,
                    previous_close=previous,
                    volume=_pick(
                        row,
                        "volume",
                        "qty",
                        "quantity",
                        "totalTradedQuantity",
                        "total_traded_quantity",
                        "traded_shares",
                        cast=_int,
                    ),
                    turnover=_pick(
                        row,
                        "turnover",
                        "amount",
                        "traded_amount",
                        "total_amount",
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
                row,
                "value",
                "close",
                "current",
                "index_value",
                "ltp",
                "points",
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
                        row,
                        "change_percent",
                        "percent_change",
                        "perc_change",
                        "changePercent",
                        "percent",
                        cast=_num,
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
            bars = self.parse_prices(payload, bd, self.name, require_source_date=True)
            for bar in bars:
                bar.fetched_at = result.fetched_at
            return bars
        except Exception:
            return []

    def fetch_company_history(self, symbol: str, since: date | None = None) -> list[PriceBar]:
        """Unadjusted, published daily history from the verified public feed."""
        try:
            result = self.client.fetch(self._endpoint_url("history", _DEFAULT_HISTORY_URL), params={"symbol": symbol.upper()})
            bars = self.parse_history(result.json(), symbol)
            for bar in bars:
                bar.fetched_at = result.fetched_at
            return [bar for bar in bars if since is None or bar.business_date >= since]
        except Exception:
            return []

    @staticmethod
    def parse_history(payload: Any, symbol: str) -> list[PriceBar]:
        if not isinstance(payload, dict) or not isinstance(payload.get("t"), list):
            return []
        rows = []
        for index, timestamp in enumerate(payload["t"]):
            try:
                row = {"timestamp": timestamp, "symbol": symbol}
                for key, column in [("open", "o"), ("high", "h"), ("low", "l"), ("close", "c"), ("volume", "vol"), ("amount", "amt")]:
                    values = payload.get(column, [])
                    row[key] = values[index] if isinstance(values, list) and index < len(values) else None
                rows.extend(ChukulClient.parse_prices([row], date.min, require_source_date=True))
            except (ValueError, TypeError, OverflowError):
                continue
        by_date = {bar.business_date: bar for bar in rows if bar.close is not None and bar.close > 0}
        bars = sorted(by_date.values(), key=lambda bar: bar.business_date)
        for previous, current in zip(bars, bars[1:], strict=False):
            current.previous_close = previous.close
        return list(reversed(bars))

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

    @staticmethod
    def parse_floorsheet(payload: Any, business_date: date) -> list[FloorsheetEntry]:
        entries = []
        for row in _as_records(payload):
            contract = str(row.get("transaction") or "")
            try:
                observed = datetime.strptime(contract[:8], "%Y%m%d").date()
            except ValueError:
                continue
            quantity = _num(row.get("quantity"))
            rate = _num(row.get("rate"))
            if observed != business_date or quantity is None or quantity <= 0 or not quantity.is_integer() or rate is None or rate <= 0:
                continue
            symbol = str(row.get("symbol") or "").strip()
            if not symbol:
                continue
            entries.append(FloorsheetEntry(contract_id=contract, symbol=symbol, business_date=observed,
                buyer_broker=str(row["buyer"]) if row.get("buyer") is not None else None,
                seller_broker=str(row["seller"]) if row.get("seller") is not None else None,
                quantity=int(quantity), rate=rate, amount=_num(row.get("amount")), source=SourceName.CHUKUL))
        return entries

    def fetch_floorsheet(self, business_date: date | None = None) -> list[FloorsheetEntry]:
        bd = business_date or date.today()
        try:
            response = self.client.fetch(self._endpoint_url("floorsheet", "https://chukul.com/api/data/floorsheet/bydate/"),
                                         params={"date": bd.isoformat()})
            return self.parse_floorsheet(response.json(), bd)
        except Exception:
            return []
