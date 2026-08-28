"""MeroLagani HTML source adapter.

MeroLagani (https://merolagani.com) is an ASP.NET WebForms site that serves
server-rendered HTML. We parse two pages:

  * StockQuote.aspx  -> whole-market daily share-price table (OHLCV + LTP)
  * Indices.aspx     -> the index / sub-index table

Parsing is fully separated from fetching: ``parse_stock_quote`` and
``parse_indices`` are pure staticmethods that take raw HTML plus context and
return models, so tests exercise them with fixtures and NO network. Fetching
uses the shared :class:`BaseClient` and is wrapped so any failure yields ``[]``.
"""

from __future__ import annotations

import logging
import re
from datetime import date

from selectolax.parser import HTMLParser, Node

from nepse_trader.config import SourceSpec
from nepse_trader.ingest.base import BaseClient, SourceClient
from nepse_trader.models import IndexValue, PriceBar, SourceName

_DEFAULT_STOCK_QUOTE_URL = "https://merolagani.com/StockQuote.aspx"
_DEFAULT_INDICES_URL = "https://merolagani.com/Indices.aspx"

log = logging.getLogger("nepse_trader.ingest.merolagani")

# ``As of 2026/08/27 03:00:00`` in the page header. MeroLagani's market table
# cannot be date-filtered over GET, so this label is the only statement of
# which trading day the rows belong to.
_AS_OF_RE = re.compile(r"as\s*of\s*:?\s*(\d{4})/(\d{2})/(\d{2})", re.IGNORECASE)


def parse_as_of_date(html: str) -> date | None:
    """The trading date the page itself says it is showing, or ``None``."""
    match = _AS_OF_RE.search(html or "")
    if match is None:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None

# Header-name fragments (lower-cased, "contains" match) -> logical column key.
# Order matters within a key: the first matching fragment wins per cell.
_PRICE_COLUMN_MATCHERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("symbol", ("symbol",)),
    ("close", ("ltp", "last")),
    ("change_percent", ("% change", "change %", "%change", "diff %", "% diff")),
    ("open", ("open",)),
    ("high", ("high",)),
    ("low", ("low",)),
    ("volume", ("qty", "volume", "vol", "shares")),
    ("turnover", ("turnover", "amount", "value")),
    ("previous_close", ("prev", "previous")),
)


def _num(raw: str | None) -> float | None:
    """Parse a possibly comma-grouped numeric string to float, else None."""
    if raw is None:
        return None
    text = raw.strip().replace(",", "").replace("%", "")
    if not text or text in {"-", "--", "N/A", "n/a", "NA"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _int(raw: str | None) -> int | None:
    """Parse a possibly comma-grouped integer string to int, else None."""
    value = _num(raw)
    if value is None:
        return None
    return int(value)


def _cell_text(node: Node) -> str:
    return node.text(deep=True, separator=" ", strip=True)


def _cell_at(cells: list[Node], idx: int | None) -> str | None:
    """Safely read a cell's text by index; None if missing/out-of-range."""
    if idx is None or idx < 0 or idx >= len(cells):
        return None
    return _cell_text(cells[idx])


def _table_header_cells(table: Node) -> list[str]:
    """Return lower-cased header texts for a table.

    Prefers an explicit ``<thead>`` row; otherwise falls back to the first row
    that contains any ``<th>`` or, failing that, the first ``<tr>``.
    """
    header_row: Node | None = None
    thead = table.css_first("thead")
    if thead is not None:
        header_row = thead.css_first("tr")
    if header_row is None:
        for row in table.css("tr"):
            if row.css_first("th") is not None:
                header_row = row
                break
    if header_row is None:
        header_row = table.css_first("tr")
    if header_row is None:
        return []
    cells = header_row.css("th") or header_row.css("td")
    return [_cell_text(c).lower() for c in cells]


def _first_match(headers: list[str], fragments: tuple[str, ...]) -> int | None:
    for idx, header in enumerate(headers):
        if any(frag in header for frag in fragments):
            return idx
    return None


def _build_column_map(headers: list[str]) -> dict[str, int]:
    """Map logical keys to column indices using header-name contains matching."""
    mapping: dict[str, int] = {}
    for idx, header in enumerate(headers):
        for key, fragments in _PRICE_COLUMN_MATCHERS:
            if key in mapping:
                continue
            if any(frag in header for frag in fragments):
                mapping[key] = idx
                break
    return mapping


def _select_price_table(tree: HTMLParser) -> Node | None:
    """Pick the largest table whose header row mentions Symbol and LTP/Last."""
    best: Node | None = None
    best_rows = -1
    for table in tree.css("table"):
        headers = _table_header_cells(table)
        joined = " ".join(headers)
        has_symbol = "symbol" in joined
        has_price = "ltp" in joined or "last" in joined
        if not (has_symbol and has_price):
            continue
        row_count = len(table.css("tr"))
        if row_count > best_rows:
            best = table
            best_rows = row_count
    return best


def _data_rows(table: Node) -> list[Node]:
    """Return body rows (skip rows that are headers / have no data cells)."""
    tbody = table.css_first("tbody")
    rows = tbody.css("tr") if tbody is not None else table.css("tr")
    out: list[Node] = []
    for row in rows:
        if row.css_first("th") is not None and row.css_first("td") is None:
            continue
        if row.css_first("td") is None:
            continue
        out.append(row)
    return out


class MeroLaganiClient(SourceClient):
    """Fetch daily prices and indices from MeroLagani's server-rendered HTML."""

    name: SourceName = SourceName.MEROLAGANI

    def __init__(
        self,
        client: BaseClient | None = None,
        source_spec: SourceSpec | None = None,
    ) -> None:
        self.client = client or BaseClient()
        self.source_spec = source_spec

    # ---- URL resolution (config-driven with sensible defaults) ----

    def _endpoint_url(self, key: str, default: str) -> str:
        if self.source_spec is not None:
            ep = self.source_spec.endpoints.get(key)
            if ep is not None and ep.url:
                return ep.url
        return default

    @property
    def stock_quote_url(self) -> str:
        return self._endpoint_url("stock_quote", _DEFAULT_STOCK_QUOTE_URL)

    @property
    def indices_url(self) -> str:
        return self._endpoint_url("indices", _DEFAULT_INDICES_URL)

    # ---- Pure parsers (no network) ----

    @staticmethod
    def parse_stock_quote(
        html: str,
        business_date: date,
        source: SourceName = SourceName.MEROLAGANI,
    ) -> list[PriceBar]:
        """Parse the StockQuote.aspx market table into PriceBars.

        Columns are mapped by HEADER NAME (case-insensitive ``contains``), so the
        adapter survives column reordering. ``close`` is taken from the LTP/Last
        column. Rows without a symbol are skipped.
        """
        tree = HTMLParser(html or "")
        table = _select_price_table(tree)
        if table is None:
            return []
        headers = _table_header_cells(table)
        col = _build_column_map(headers)
        sym_idx = col.get("symbol")
        if sym_idx is None:
            return []

        bars: list[PriceBar] = []
        for row in _data_rows(table):
            cells = row.css("td")
            if not cells or sym_idx >= len(cells):
                continue

            symbol = (_cell_at(cells, sym_idx) or "").strip()
            if not symbol:
                continue
            bars.append(
                PriceBar(
                    symbol=symbol,
                    business_date=business_date,
                    open=_num(_cell_at(cells, col.get("open"))),
                    high=_num(_cell_at(cells, col.get("high"))),
                    low=_num(_cell_at(cells, col.get("low"))),
                    close=_num(_cell_at(cells, col.get("close"))),
                    previous_close=_num(_cell_at(cells, col.get("previous_close"))),
                    volume=_int(_cell_at(cells, col.get("volume"))),
                    turnover=_num(_cell_at(cells, col.get("turnover"))),
                    source=source,
                )
            )
        return bars

    @staticmethod
    def parse_indices(
        html: str,
        source: SourceName = SourceName.MEROLAGANI,
        business_date: date | None = None,
    ) -> list[IndexValue]:
        """Parse the Indices.aspx table into IndexValues.

        Expects a table whose header mentions an index/name column and a value
        column. Change and percent-change columns are optional.
        """
        bd = business_date or date.today()
        tree = HTMLParser(html or "")
        target: Node | None = None
        target_col: dict[str, int] = {}
        best_rows = -1
        for table in tree.css("table"):
            headers = _table_header_cells(table)
            name_idx = _first_match(headers, ("index", "indices", "name", "title"))
            value_idx = _first_match(headers, ("value", "current", "ltp", "close", "points"))
            if name_idx is None or value_idx is None:
                continue
            row_count = len(table.css("tr"))
            if row_count > best_rows:
                best_rows = row_count
                target = table
                target_col = {
                    "name": name_idx,
                    "value": value_idx,
                    "change": _first_match(headers, ("change",)) or -1,
                    "change_percent": _first_match(
                        headers, ("% change", "change %", "%change", "% diff")
                    )
                    or -1,
                }
        if target is None:
            return []

        out: list[IndexValue] = []
        for row in _data_rows(target):
            cells = row.css("td")
            if not cells:
                continue

            name = (_cell_at(cells, target_col["name"]) or "").strip()
            value = _num(_cell_at(cells, target_col["value"]))
            if not name or value is None:
                continue
            # An index is never called "2,557.31". When the table this picked is
            # not really an index table, the "name" column lands on a numeric
            # cell and every row becomes a junk index whose name is its own
            # price — poison for anything that groups index_values by name.
            if _num(name) is not None:
                continue
            out.append(
                IndexValue(
                    name=name,
                    business_date=bd,
                    value=value,
                    change=_num(_cell_at(cells, target_col["change"])),
                    change_percent=_num(_cell_at(cells, target_col["change_percent"])),
                    source=source,
                )
            )
        return out

    # ---- Fetchers (network; failures -> []) ----

    def fetch_prices(self, business_date: date | None = None) -> list[PriceBar]:
        try:
            result = self.client.fetch(self.stock_quote_url)
        except Exception:
            return []
        as_of = parse_as_of_date(result.text)
        if business_date is not None and as_of is not None and as_of != business_date:
            log.warning(
                "merolagani served the %s board for a request for %s; the table is "
                "not date-filterable over GET, so these rows are dropped rather "
                "than stamped with the wrong date",
                as_of.isoformat(),
                business_date.isoformat(),
            )
            return []
        bd = as_of or business_date or date.today()
        try:
            return self.parse_stock_quote(result.text, bd, self.name)
        except Exception:
            return []

    def fetch_indices(self, business_date: date | None = None) -> list[IndexValue]:
        bd = business_date or date.today()
        try:
            result = self.client.fetch(self.indices_url)
        except Exception:
            return []
        try:
            return self.parse_indices(result.text, self.name, bd)
        except Exception:
            return []
