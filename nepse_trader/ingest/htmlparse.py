"""Resilient HTML table extraction with a pluggable backend.

Two backends produce identical output, so parsers can stay backend-agnostic:
  * **Scrapling** (`scrapling.parser.Selector`) — adaptive, tolerant of layout
    drift; preferred when installed.
  * **selectolax** — the always-available fallback.

`table_rows()` returns, for a table, one entry per ``<tr>`` as a list of
``(tag, text)`` cell tuples (``tag`` is ``"th"``/``"td"``), with recursively
extracted, stripped text. That's exactly what the ShareSansar / MeroLagani
parsers need at the low level, while the column-mapping logic lives in them.

This module reads and parses only — it performs NO network I/O and contains no
stealth / anti-bot logic.
"""

from __future__ import annotations

import functools

from nepse_trader.config import get_settings

Row = list[tuple[str, str]]


@functools.lru_cache(maxsize=1)
def _scrapling_selector():
    """Return the Scrapling Selector class, or None if unavailable."""
    try:
        from scrapling.parser import Selector  # type: ignore

        return Selector
    except Exception:  # pragma: no cover - import guard
        return None


def scrapling_available() -> bool:
    return _scrapling_selector() is not None


def resolve_engine(engine: str | None = None) -> str:
    """Resolve the effective parse engine name ('scrapling' or 'selectolax')."""
    choice = (engine or get_settings().parse_engine or "auto").lower()
    if choice == "scrapling":
        return "scrapling" if scrapling_available() else "selectolax"
    if choice == "selectolax":
        return "selectolax"
    # auto
    return "scrapling" if scrapling_available() else "selectolax"


def table_rows(html: str, table_css: str, engine: str | None = None) -> list[Row]:
    """Return rows of (tag, text) cell tuples for the first table matching
    ``table_css``. Empty list if the table is absent."""
    if not html:
        return []
    if resolve_engine(engine) == "scrapling":
        return _rows_scrapling(html, table_css)
    return _rows_selectolax(html, table_css)


def _rows_scrapling(html: str, table_css: str) -> list[Row]:
    Selector = _scrapling_selector()
    if Selector is None:  # pragma: no cover - guarded by resolve_engine
        return _rows_selectolax(html, table_css)
    sel = Selector(html)
    tables = sel.css(table_css)
    if not tables:
        return []
    out: list[Row] = []
    for tr in tables[0].css("tr"):
        cells: Row = []
        for cell in tr.css("th, td"):
            text = cell.get_all_text(strip=True) if hasattr(cell, "get_all_text") else str(cell.text)
            cells.append((str(cell.tag).lower(), str(text)))
        out.append(cells)
    return out


def _rows_selectolax(html: str, table_css: str) -> list[Row]:
    from selectolax.parser import HTMLParser

    tree = HTMLParser(html)
    table = tree.css_first(table_css)
    if table is None:
        return []
    out: list[Row] = []
    for tr in table.css("tr"):
        cells: Row = []
        for cell in tr.css("th, td"):
            cells.append((cell.tag.lower(), cell.text(strip=True)))
        out.append(cells)
    return out


def td_texts(row: Row) -> list[str]:
    """The text of the ``<td>`` cells in a row (ignoring header ``<th>`` cells)."""
    return [text for tag, text in row if tag == "td"]


def has_header(row: Row) -> bool:
    return any(tag == "th" for tag, _ in row)
