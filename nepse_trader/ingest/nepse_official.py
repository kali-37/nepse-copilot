"""NEPSE official-data adapters: optional scraper library + HAR replay.

Ethics first
------------
NEPSE's ``/api/nots/`` endpoints are gated by an obfuscated WASM "Salter"
token that the official front-end mints client-side. That token exists to
restrict access to NEPSE's own UI. We DO NOT reimplement, decompile, or bypass
it, and we never POST to ``/api/authenticate``. Instead this module offers two
clean, consent-respecting paths to the same public end-of-day data:

A. :class:`NepseScraperClient` — a thin wrapper around the optional, MIT-licensed
   third-party ``nepse_scraper`` package. We import it lazily *inside* the
   method, so the dependency is genuinely optional: if it is not installed,
   :func:`is_available` is ``False`` and ``fetch_prices`` returns ``[]`` rather
   than raising. We do not vendor the library or its token logic; we only call
   its public API if the user chose to install it.

B. :class:`HarReplayClient` — replays a HAR (HTTP Archive) file that the *user*
   captured themselves from their own authenticated browser session. Nothing is
   fetched over the network; we just parse the saved responses. This keeps the
   token entirely on the user's side of the consent boundary.

The mapping logic (:func:`parse_today_price`) is a pure function over already
fetched/decoded payloads, so it is exercised in tests with fixtures and no
network.
"""

from __future__ import annotations

import base64
import binascii
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from nepse_trader.ingest.base import SourceClient
from nepse_trader.models import PriceBar, SourceName

__all__ = [
    "NepseScraperClient",
    "HarReplayClient",
    "is_available",
    "parse_today_price",
    "load_har",
    "find_entries",
    "decode_content",
]


# ---------------------------------------------------------------------------
# Optional-library availability
# ---------------------------------------------------------------------------
def is_available() -> bool:
    """Return ``True`` iff the optional ``nepse_scraper`` library is importable.

    Done with an import attempt rather than ``importlib.util.find_spec`` so the
    answer matches what :class:`NepseScraperClient` will actually experience.
    """
    try:
        import nepse_scraper  # noqa: F401
    except Exception:
        return False
    return True


# ---------------------------------------------------------------------------
# Pure helpers (no network) — safe numeric coercion
# ---------------------------------------------------------------------------
def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):  # guard: bool is an int subclass
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        # Tolerate thousands separators that some sources embed in strings.
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    f = _to_float(value)
    if f is None:
        return None
    return int(round(f))


def _first(record: dict[str, Any], *keys: str) -> Any:
    """Return the first present, non-None value among ``keys`` in ``record``."""
    for key in keys:
        if key in record and record[key] is not None:
            return record[key]
    return None


def _parse_business_date(value: Any, fallback: date | None) -> date:
    """Coerce a NEPSE-style date field to ``datetime.date``.

    Accepts ``date``/``datetime`` objects and ISO-ish strings ("2024-01-15" or
    "2024-01-15T00:00:00"). Falls back to the supplied date, then today.
    """
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        text = value.strip()
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            try:
                return datetime.fromisoformat(text).date()
            except ValueError:
                pass
    if fallback is not None:
        return fallback
    return date.today()


def parse_today_price(
    payload: dict[str, Any] | list[Any],
    source: SourceName,
    business_date: date | None = None,
) -> list[PriceBar]:
    """Map a NEPSE "today price" payload to :class:`PriceBar` objects.

    The expected shape is the NEPSE ``/api/nots/nepse-data/today-price`` JSON::

        {"content": [{"symbol": "NABIL", "openPrice": ..., "highPrice": ...,
                      "lowPrice": ..., "lastTradedPrice": ...,
                      "previousClose"/"previousDayClose": ...,
                      "totalTradedQuantity": ..., "totalTradedValue": ...,
                      "totalTrades": ..., "businessDate": "2024-01-15"}, ...]}

    Robustness contract: this is pure and never raises. A malformed top level,
    or any individual record that lacks a symbol, is skipped. ``business_date``
    overrides any per-record date when no record date is present.
    """
    records = _extract_records(payload)
    bars: list[PriceBar] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        symbol = _first(record, "symbol", "stockSymbol", "Symbol")
        if symbol is None or str(symbol).strip() == "":
            continue
        bdate = _parse_business_date(
            _first(record, "businessDate", "business_date", "tradeDate", "date"),
            business_date,
        )
        try:
            bar = PriceBar(
                symbol=str(symbol),
                business_date=bdate,
                open=_to_float(_first(record, "openPrice", "open", "openingPrice")),
                high=_to_float(_first(record, "highPrice", "high", "maxPrice")),
                low=_to_float(_first(record, "lowPrice", "low", "minPrice")),
                close=_to_float(_first(record, "lastTradedPrice", "closePrice", "close", "ltp")),
                previous_close=_to_float(
                    _first(record, "previousClose", "previousDayClose", "preClose")
                ),
                volume=_to_int(
                    _first(record, "totalTradedQuantity", "volume", "qty", "shareTraded")
                ),
                turnover=_to_float(_first(record, "totalTradedValue", "turnover", "amount")),
                trades=_to_int(_first(record, "totalTrades", "trades", "noOfTransactions")),
                source=source,
            )
        except Exception:
            # A single bad record must not poison the batch.
            continue
        bars.append(bar)
    return bars


def _extract_records(payload: dict[str, Any] | list[Any]) -> list[Any]:
    """Pull the list of per-symbol records from a variety of envelopes."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("content", "data", "rows", "result"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
            # Some envelopes nest one level deeper, e.g. {"data": {"content": [...]}}.
            if isinstance(value, dict):
                for inner in ("content", "data", "rows"):
                    nested = value.get(inner)
                    if isinstance(nested, list):
                        return nested
    return []


# ---------------------------------------------------------------------------
# A) Optional third-party scraper library
# ---------------------------------------------------------------------------
class NepseScraperClient(SourceClient):
    """Adapter over the optional MIT ``nepse_scraper`` package.

    The third-party dependency is imported lazily inside :meth:`fetch_prices`.
    When it is missing, :attr:`available` is ``False`` and fetches return ``[]``
    so the orchestrator can keep running with whatever other sources exist.
    """

    name: SourceName = SourceName.NEPSE_OFFICIAL

    def __init__(self) -> None:
        # No BaseClient/network here: the library manages its own HTTP. We only
        # record whether it is importable for callers that want to branch.
        self.available: bool = is_available()

    def fetch_prices(self, business_date: date | None = None) -> list[PriceBar]:
        """Fetch today's prices via ``nepse_scraper``; ``[]`` on any problem."""
        try:
            from nepse_scraper import Request_module  # type: ignore[import-not-found]
        except ImportError:
            self.available = False
            return []

        try:
            requester = Request_module()
            payload = requester.get_today_price()
        except Exception:
            # Network errors, library API drift, token issues — all non-fatal.
            return []

        if not isinstance(payload, (dict, list)):
            return []
        return parse_today_price(payload, self.name, business_date=business_date)


# ---------------------------------------------------------------------------
# B) HAR replay (user's own capture)
# ---------------------------------------------------------------------------
def load_har(path: str | Path) -> dict[str, Any]:
    """Load and JSON-parse a HAR file. Returns ``{}`` on any failure."""
    try:
        text = Path(path).read_text(encoding="utf-8")
        data = json.loads(text)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def find_entries(har: dict[str, Any], url_substring: str) -> list[dict[str, Any]]:
    """Return HAR log entries whose request URL contains ``url_substring``.

    Case-insensitive substring match. Tolerant of malformed entries.
    """
    needle = url_substring.lower()
    try:
        entries = har["log"]["entries"]
    except (KeyError, TypeError):
        return []
    if not isinstance(entries, list):
        return []

    matches: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        url = ""
        request = entry.get("request")
        if isinstance(request, dict):
            url = str(request.get("url", ""))
        if needle in url.lower():
            matches.append(entry)
    return matches


def decode_content(entry: dict[str, Any]) -> str:
    """Decode an entry's response body to text.

    Honours ``response.content.encoding == "base64"`` (browser-exported HARs
    base64 the body); otherwise returns the plain ``text`` field. Returns ``""``
    when there is no usable body.
    """
    if not isinstance(entry, dict):
        return ""
    response = entry.get("response")
    if not isinstance(response, dict):
        return ""
    content = response.get("content")
    if not isinstance(content, dict):
        return ""

    text = content.get("text")
    if not isinstance(text, str) or text == "":
        return ""

    if str(content.get("encoding", "")).lower() == "base64":
        try:
            return base64.b64decode(text).decode("utf-8")
        except (binascii.Error, ValueError, UnicodeDecodeError):
            return ""
    return text


def _parse_sharesansar_like(
    records: list[Any], source: SourceName, business_date: date | None
) -> list[PriceBar]:
    """Map a ShareSansar-style today-price JSON list to PriceBars.

    ShareSansar's JSON uses friendlier keys (``Symbol``, ``Open``, ``High``,
    ``Low``, ``Close``/``LTP``, ``PreviousClose``, ``Volume``/``Vol``,
    ``Turnover``, ``Trans``). We funnel each record through ``parse_today_price``
    by aliasing those keys onto the NEPSE field names it already understands.
    """
    aliased: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        aliased.append(
            {
                "symbol": _first(record, "Symbol", "symbol", "SYMBOL"),
                "openPrice": _first(record, "Open", "open", "OpenPrice"),
                "highPrice": _first(record, "High", "high", "HighPrice"),
                "lowPrice": _first(record, "Low", "low", "LowPrice"),
                "lastTradedPrice": _first(record, "Close", "LTP", "Ltp", "close", "ClosePrice"),
                "previousClose": _first(record, "PreviousClose", "PrevClose", "previousClose"),
                "totalTradedQuantity": _first(record, "Volume", "Vol", "volume"),
                "totalTradedValue": _first(record, "Turnover", "turnover", "Amount"),
                "totalTrades": _first(record, "Trans", "Trades", "trades"),
                "businessDate": _first(record, "BusinessDate", "Date", "businessDate"),
            }
        )
    return parse_today_price(aliased, source, business_date=business_date)


class HarReplayClient(SourceClient):
    """Replays a user-captured HAR file to produce PriceBars with no network."""

    name: SourceName = SourceName.HAR_REPLAY

    # URL fragments we recognise as "today price" payloads.
    _PRICE_URL_SUBSTRINGS = ("today-price", "today-share-price", "todayprice")

    def __init__(self, har_path: str | Path) -> None:
        self.har_path = Path(har_path)

    def fetch_prices(self, business_date: date | None = None) -> list[PriceBar]:
        """Scan the HAR for a today-price response and map it. ``[]`` on miss."""
        try:
            har = load_har(self.har_path)
            if not har:
                return []
            for substring in self._PRICE_URL_SUBSTRINGS:
                for entry in find_entries(har, substring):
                    bars = self._bars_from_entry(entry, business_date)
                    if bars:
                        return bars
        except Exception:
            return []
        return []

    def _bars_from_entry(self, entry: dict[str, Any], business_date: date | None) -> list[PriceBar]:
        body = decode_content(entry)
        if not body:
            return []
        try:
            payload = json.loads(body)
        except ValueError:
            return []

        records = _extract_records(payload)
        if not records:
            return []

        # Heuristic: NEPSE records carry camelCase keys like ``lastTradedPrice``;
        # ShareSansar exports use TitleCase (``Symbol``/``LTP``). Detect and route.
        sample = next((r for r in records if isinstance(r, dict)), None)
        if sample is not None and _looks_sharesansar(sample):
            return _parse_sharesansar_like(records, self.name, business_date)
        return parse_today_price(payload, self.name, business_date=business_date)


def _looks_sharesansar(record: dict[str, Any]) -> bool:
    """True when a record uses ShareSansar-style keys rather than NEPSE's."""
    nepse_keys = {"lastTradedPrice", "openPrice", "totalTradedQuantity"}
    if any(key in record for key in nepse_keys):
        return False
    sharesansar_keys = {"Symbol", "LTP", "Ltp", "Close", "Open", "PreviousClose"}
    return any(key in record for key in sharesansar_keys)
