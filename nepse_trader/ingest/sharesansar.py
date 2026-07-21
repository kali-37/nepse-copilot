"""ShareSansar ingestion client — the project's PRIMARY public-data source.

ShareSansar (https://www.sharesansar.com) publishes whole-market EOD OHLCV as a
server-rendered HTML table (``#headFixed`` on ``/today-share-price``) and exposes
several DataTables endpoints that return JSON when called with the
``X-Requested-With: XMLHttpRequest`` header (floorsheet, indices, top movers).

Design follows the project convention of separating PARSING from FETCHING:

  * ``parse_*`` staticmethods are pure — they take raw ``str``/``dict`` and return
    models. They never touch the network, so tests exercise them with fixtures.
  * ``fetch_*`` methods use the shared :class:`BaseClient`, then delegate to the
    pure parser, wrapping the whole thing so a fetch failure degrades to ``[]``
    rather than crashing the orchestrator.

We treat these as UNOFFICIAL front-end endpoints: a real User-Agent, polite
throttling (handled by ``BaseClient``), and no attempt to bypass auth, WAFs, or
rate limits.
"""

from __future__ import annotations

import re
from datetime import date

from selectolax.parser import HTMLParser

from nepse_trader.config import SourceSpec, load_sources
from nepse_trader.ingest.base import (
    BaseClient,
    FetchError,
    RateLimitedError,
    SourceClient,
)
from nepse_trader.ingest.htmlparse import has_header, table_rows, td_texts
from nepse_trader.models import (
    FloorsheetEntry,
    IndexValue,
    MarketStatus,
    PriceBar,
    SourceName,
)

# Fallback URLs used when the source spec / YAML does not supply an endpoint.
_DEFAULT_URLS: dict[str, str] = {
    "today_share_price": "https://www.sharesansar.com/today-share-price",
    "floorsheet": "https://www.sharesansar.com/floorsheet",
    "indices_sub_indices": "https://www.sharesansar.com/indices-sub-indices",
    "live_trading": "https://www.sharesansar.com/live-trading",
    "top_gainers": "https://www.sharesansar.com/top-gainers",
    "top_losers": "https://www.sharesansar.com/top-losers",
}

_XHR_HEADERS = {"X-Requested-With": "XMLHttpRequest"}

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(value: object) -> str:
    """Extract plain text from a value that may be an HTML anchor.

    ShareSansar's JSON endpoints embed anchors like
    ``<a href="https://www.sharesansar.com/company/khpl">KHPL</a>``; we want just
    ``KHPL``. Non-string inputs are coerced to ``str`` first.
    """
    if value is None:
        return ""
    text = _TAG_RE.sub(" ", str(value))
    return " ".join(text.split()).strip()


def _num(value: object) -> float | None:
    """Parse a possibly comma-grouped numeric cell to ``float`` (or ``None``).

    Handles ``"1,234.50"`` -> ``1234.5``, and treats ``""`` / ``"-"`` / ``"N/A"``
    (and anything non-numeric) as missing.
    """
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if text in ("", "-", "--", "N/A", "n/a"):
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _int(value: object) -> int | None:
    """Parse a possibly comma-grouped integer cell to ``int`` (or ``None``)."""
    num = _num(value)
    if num is None:
        return None
    return int(num)


class ShareSansarClient(SourceClient):
    """Adapter for ShareSansar public market data."""

    name: SourceName = SourceName.SHARESANSAR

    def __init__(
        self,
        client: BaseClient | None = None,
        source_spec: SourceSpec | None = None,
    ):
        self.client = client if client is not None else BaseClient()
        if source_spec is None:
            source_spec = load_sources().get("sharesansar")
        self.source_spec = source_spec

    # -- endpoint resolution -------------------------------------------------

    def _url(self, key: str) -> str:
        """Resolve an endpoint URL from the source spec, else the fallback."""
        if self.source_spec is not None:
            ep = self.source_spec.endpoints.get(key)
            if ep is not None and ep.url:
                return ep.url
        return _DEFAULT_URLS[key]

    # -- pure parsers --------------------------------------------------------

    @staticmethod
    def parse_today_share_price(
        html: str,
        business_date: date,
        source: SourceName = SourceName.SHARESANSAR,
    ) -> list[PriceBar]:
        """Parse the ``#headFixed`` EOD price table into :class:`PriceBar` rows.

        Column order (0-indexed):
            0 S.No, 1 Symbol, 2 Conf., 3 Open, 4 High, 5 Low, 6 Close, 7 LTP,
            8 Close-LTP, 9 Close-LTP%, 10 VWAP, 11 Vol, 12 Prev.Close,
            13 Turnover, 14 Trans., 15 Diff, 16 Range, 17 Diff%, 18 Range%,
            19 VWAP%, 20 120/180Days.

        ``close`` falls back to LTP when the Close cell is blank/``-``. Rows
        without a usable symbol (header/blank/total rows) are skipped.
        """
        bars: list[PriceBar] = []
        for row in table_rows(html or "", "table#headFixed"):
            # Skip header rows (those whose cells are <th>).
            if has_header(row):
                continue
            texts = td_texts(row)
            if len(texts) < 13:
                continue

            symbol = _strip_html(texts[1])
            if not symbol or symbol == "-":
                continue

            open_ = _num(texts[3])
            high = _num(texts[4])
            low = _num(texts[5])
            close = _num(texts[6])
            ltp = _num(texts[7])
            volume = _int(texts[11])
            if close is None:
                close = ltp  # fall back to LTP

            # Skip totals/footer rows: a label in the symbol column but no
            # usable price or volume anywhere.
            if (
                open_ is None
                and high is None
                and low is None
                and close is None
                and ltp is None
                and volume is None
            ):
                continue

            bars.append(
                PriceBar(
                    symbol=symbol,
                    business_date=business_date,
                    open=open_,
                    high=high,
                    low=low,
                    close=close,
                    previous_close=_num(texts[12]),
                    volume=volume,
                    turnover=_num(texts[13]) if len(texts) > 13 else None,
                    trades=_int(texts[14]) if len(texts) > 14 else None,
                    source=source,
                )
            )
        return bars

    @staticmethod
    def parse_floorsheet(
        payload: dict,
        business_date: date,
        source: SourceName = SourceName.SHARESANSAR,
    ) -> list[FloorsheetEntry]:
        """Parse a floorsheet DataTables JSON payload into entries.

        Each row carries ``symbol`` (possibly an HTML anchor), ``contract_no``,
        ``buyer``, ``seller``, ``quantity``, ``rate``, ``amount`` and ``date_``.
        """
        rows = (payload or {}).get("data") or []
        entries: list[FloorsheetEntry] = []
        for row in rows:
            symbol = _strip_html(row.get("symbol"))
            if not symbol:
                continue
            quantity = _int(row.get("quantity"))
            rate = _num(row.get("rate"))
            if quantity is None or rate is None:
                continue
            entries.append(
                FloorsheetEntry(
                    contract_id=_strip_html(row.get("contract_no")) or None,
                    symbol=symbol,
                    business_date=business_date,
                    buyer_broker=_strip_html(row.get("buyer")) or None,
                    seller_broker=_strip_html(row.get("seller")) or None,
                    quantity=quantity,
                    rate=rate,
                    amount=_num(row.get("amount")),
                    source=source,
                )
            )
        return entries

    @staticmethod
    def parse_indices(
        payload: dict,
        index_name: str = "NEPSE",
        source: SourceName = SourceName.SHARESANSAR,
    ) -> list[IndexValue]:
        """Parse an indices/sub-indices DataTables payload into index values.

        Maps ``current`` -> value, ``change_`` -> change, ``per_change`` ->
        change_percent, keyed by ``published_date``.
        """
        rows = (payload or {}).get("data") or []
        values: list[IndexValue] = []
        for row in rows:
            published = row.get("published_date")
            bdate = _parse_date(published)
            value = _num(row.get("current"))
            if bdate is None or value is None:
                continue
            values.append(
                IndexValue(
                    name=index_name,
                    business_date=bdate,
                    value=value,
                    change=_num(row.get("change_")),
                    change_percent=_num(row.get("per_change")),
                    source=source,
                )
            )
        return values

    @staticmethod
    def parse_market_status(
        html: str,
        source: SourceName = SourceName.SHARESANSAR,
    ) -> MarketStatus:
        """Scan the live-trading HTML for market status + an 'As of' timestamp."""
        text = HTMLParser(html or "").text() if html else ""
        lowered = text.lower()

        is_open = "market open" in lowered
        if not is_open and "market closed" in lowered:
            is_open = False

        as_of = None
        match = re.search(r"as of[:\s]+([0-9A-Za-z:,\-/ ]+)", text, re.IGNORECASE)
        if match:
            as_of = _parse_datetime(match.group(1).strip())

        return MarketStatus(is_open=is_open, as_of=as_of, session=None, source=source)

    @staticmethod
    def parse_top_movers(payload: dict) -> list[dict]:
        """Parse a top-gainers/top-losers JSON payload into cleaned dict rows.

        Symbol and company name may be HTML anchors; numeric fields are coerced
        to floats. Used by reports, not the core price pipeline.
        """
        rows = (payload or {}).get("data") or []
        cleaned: list[dict] = []
        for row in rows:
            symbol = _strip_html(row.get("symbol"))
            if not symbol:
                continue
            cleaned.append(
                {
                    "symbol": symbol,
                    "company": _strip_html(row.get("companyname")),
                    "ltp": _num(row.get("ltp")),
                    "point_change": _num(row.get("point_change")),
                    "change_percent": _num(row.get("change_percent")),
                }
            )
        return cleaned

    # -- fetchers (network; failures degrade to []) --------------------------

    def fetch_prices(self, business_date: date | None = None) -> list[PriceBar]:
        params = {"date": business_date.isoformat()} if business_date else None
        try:
            result = self.client.fetch(self._url("today_share_price"), params=params)
        except (FetchError, RateLimitedError, ValueError):
            return []
        bdate = business_date or _today()
        bars = self.parse_today_share_price(result.text, bdate, self.name)
        for bar in bars:
            bar.fetched_at = result.fetched_at
        return bars

    def fetch_floorsheet(self, business_date: date | None = None) -> list[FloorsheetEntry]:
        params = {"date": business_date.isoformat()} if business_date else None
        try:
            result = self.client.fetch(
                self._url("floorsheet"), params=params, headers=dict(_XHR_HEADERS)
            )
            payload = result.json()
        except (FetchError, RateLimitedError, ValueError):
            return []
        bdate = business_date or _today()
        return self.parse_floorsheet(payload, bdate, self.name)

    def fetch_indices(self, business_date: date | None = None) -> list[IndexValue]:
        params = {"date": business_date.isoformat()} if business_date else None
        try:
            result = self.client.fetch(
                self._url("indices_sub_indices"),
                params=params,
                headers=dict(_XHR_HEADERS),
            )
            payload = result.json()
        except (FetchError, RateLimitedError, ValueError):
            # ValueError covers an empty/non-JSON body (e.g. the HTTP 202 the
            # endpoint returns when no index_id filter is supplied).
            return []
        return self.parse_indices(payload, "NEPSE", self.name)

    def market_status(self) -> MarketStatus | None:
        try:
            result = self.client.fetch(self._url("live_trading"))
        except (FetchError, RateLimitedError, ValueError):
            return None
        return self.parse_market_status(result.text, self.name)

    def top_gainers(self) -> list[dict]:
        try:
            result = self.client.fetch(self._url("top_gainers"), headers=dict(_XHR_HEADERS))
            payload = result.json()
        except (FetchError, RateLimitedError, ValueError):
            return []
        return self.parse_top_movers(payload)

    def top_losers(self) -> list[dict]:
        try:
            result = self.client.fetch(self._url("top_losers"), headers=dict(_XHR_HEADERS))
            payload = result.json()
        except (FetchError, RateLimitedError, ValueError):
            return []
        return self.parse_top_movers(payload)


# -- small date/time helpers (kept local to avoid widening the public API) ----


def _today() -> date:
    from datetime import datetime

    return datetime.now().date()


def _parse_date(value: object) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in ("-", "--"):
        return None
    try:
        from dateutil import parser as _dtparser

        return _dtparser.parse(text).date()
    except (ValueError, OverflowError, TypeError):
        return None


def _parse_datetime(value: object):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        from dateutil import parser as _dtparser

        return _dtparser.parse(text, fuzzy=True)
    except (ValueError, OverflowError, TypeError):
        return None
