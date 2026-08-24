"""CSV / pasted-export importer — the no-credentials path.

Some users will not store a MeroShare password anywhere, and that is a
reasonable position. This module gets them the same holdings model from a file
they exported or a block they pasted, so every downstream feature (sync,
real-vs-paper, the API) works identically whether the data arrived over HTTP or
through a clipboard.

Real exports are messy, so parsing is liberal in the ways that actually occur:
a UTF-8 BOM, CRLF, blank rows, ``1,234`` thousands separators, ``Rs.``/``NPR``
prefixes, a trailing ``Total`` row, and header spellings that differ between the
portal, a broker's own export, and a hand-made spreadsheet.

It is strict in exactly one place: **a file whose columns cannot be identified
is rejected**, never imported as zeros. Silently importing an empty portfolio
would be read as "you own nothing", which is worse than an error.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import UTC, datetime

from nepse_trader.meroshare.models import MeroShareHolding, MeroSharePortfolio

# Header aliases, matched after lowercasing and stripping non-alphanumerics.
# "scrip" also matches "scripname"/"scripsymbol" via the prefix pass below.
SYMBOL_ALIASES = ("scrip", "symbol", "stock", "company", "scripname", "scripsymbol")
BALANCE_ALIASES = (
    "currentbalance",
    "balance",
    "quantity",
    "qty",
    "units",
    "shares",
    "totalquantity",
    "kitta",
)
WACC_ALIASES = (
    "wacc",
    "waccrate",
    "weightedaveragecost",
    "avgcost",
    "averagecost",
    "averagebuyrate",
    "costpershare",
    "purchaseprice",
    "rate",
)
PREV_CLOSE_ALIASES = (
    "previousclosingprice",
    "prevclose",
    "previousclose",
    "ltp",
    "lasttradedprice",
    "closingprice",
    "marketprice",
)
ISIN_ALIASES = ("isin", "isinnumber")
DEMAT_ALIASES = ("demat", "dematnumber", "dematno", "boid")
DESC_ALIASES = ("scripdesc", "companyname", "description", "scripdescription")

# Values in a first column that mark a footer/total row rather than a holding.
_TOTAL_MARKERS = ("total", "grandtotal", "sum", "subtotal", "")

_NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


class ImportError_(Exception):
    """Raised when an export cannot be understood. Named to avoid shadowing
    the builtin ``ImportError``; exported as ``MeroShareImportError``."""


MeroShareImportError = ImportError_


def _norm(text: str) -> str:
    """Header key: lowercase, alphanumerics only. ``"Current Balance"`` -> ``currentbalance``."""
    return re.sub(r"[^a-z0-9]", "", (text or "").strip().lower())


def _to_int(raw: str) -> int | None:
    match = _NUMBER.search((raw or "").strip())
    if match is None:
        return None
    try:
        return int(float(match.group().replace(",", "")))
    except ValueError:
        return None


def _to_float(raw: str) -> float | None:
    match = _NUMBER.search((raw or "").strip())
    if match is None:
        return None
    try:
        return float(match.group().replace(",", ""))
    except ValueError:
        return None


def _match_column(headers: list[str], aliases: tuple[str, ...]) -> str | None:
    """Find the header matching any alias: exact first, then prefix, then
    substring. Exact-first stops "rate" from stealing the "wacc rate" column."""
    normed = {_norm(h): h for h in headers}
    for alias in aliases:
        if alias in normed:
            return normed[alias]
    for alias in aliases:
        for key, original in normed.items():
            if key.startswith(alias):
                return original
    for alias in aliases:
        for key, original in normed.items():
            if alias in key:
                return original
    return None


def _sniff_dialect(text: str) -> type[csv.Dialect] | csv.Dialect:
    """Detect the delimiter. Falls back to comma, which is the common case."""
    sample = "\n".join(text.splitlines()[:5])
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        return csv.excel


def parse_holdings_csv(text: str, *, source: str = "csv_import") -> list[MeroShareHolding]:
    """Parse a CSV/pasted holdings export into holdings.

    Raises :class:`MeroShareImportError` when the text is empty, has no header
    row, or has no identifiable symbol *and* balance column.
    """
    if not text or not text.strip():
        raise ImportError_("nothing to import: the input is empty")

    # BOM, CRLF and stray leading blank lines, in that order.
    text = text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")

    reader = csv.reader(io.StringIO(text), dialect=_sniff_dialect(text))
    rows = [r for r in reader if any((c or "").strip() for c in r)]
    if not rows:
        raise ImportError_("nothing to import: no non-blank rows found")

    headers = [(c or "").strip() for c in rows[0]]
    symbol_col = _match_column(headers, SYMBOL_ALIASES)
    balance_col = _match_column(headers, BALANCE_ALIASES)
    if symbol_col is None or balance_col is None:
        missing = []
        if symbol_col is None:
            missing.append(f"a symbol column (any of: {', '.join(SYMBOL_ALIASES[:4])}…)")
        if balance_col is None:
            missing.append(f"a balance column (any of: {', '.join(BALANCE_ALIASES[:4])}…)")
        raise ImportError_(
            "could not identify " + " and ".join(missing) + ". "
            f"Header row seen: {headers!r}. Refusing to import rather than "
            "recording zero balances."
        )

    wacc_col = _match_column(headers, WACC_ALIASES)
    prev_col = _match_column(headers, PREV_CLOSE_ALIASES)
    isin_col = _match_column(headers, ISIN_ALIASES)
    demat_col = _match_column(headers, DEMAT_ALIASES)
    desc_col = _match_column(headers, DESC_ALIASES)
    index = {h: i for i, h in enumerate(headers)}

    def cell(row: list[str], col: str | None) -> str:
        if col is None:
            return ""
        i = index[col]
        return (row[i] or "").strip() if i < len(row) else ""

    out: list[MeroShareHolding] = []
    for row in rows[1:]:
        symbol = cell(row, symbol_col)
        # Footer/total rows: a "total"-ish or empty symbol cell.
        if _norm(symbol) in _TOTAL_MARKERS:
            continue
        balance = _to_int(cell(row, balance_col))
        if balance is None:
            continue
        out.append(
            MeroShareHolding(
                symbol=symbol,
                current_balance=balance,
                wacc=_to_float(cell(row, wacc_col)),
                previous_closing_price=_to_float(cell(row, prev_col)),
                isin=cell(row, isin_col) or None,
                demat_number=cell(row, demat_col),
                script_desc=cell(row, desc_col) or None,
                source=source,
            )
        )

    if not out:
        raise ImportError_(
            "the export was understood but contained no holding rows "
            f"(header row seen: {headers!r})"
        )
    return out


def parse_holdings_file(path, *, source: str = "csv_import") -> list[MeroShareHolding]:
    """Read a file and parse it. ``utf-8-sig`` handles an Excel-written BOM."""
    from pathlib import Path

    p = Path(path)
    if not p.exists():
        raise ImportError_(f"no such file: {p}")
    try:
        text = p.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        text = p.read_text(encoding="latin-1")
    return parse_holdings_csv(text, source=source)


def import_portfolio(text_or_path, *, is_path: bool = False) -> MeroSharePortfolio:
    """Import from pasted text or a file into a :class:`MeroSharePortfolio`."""
    holdings = (
        parse_holdings_file(text_or_path) if is_path else parse_holdings_csv(str(text_or_path))
    )
    return MeroSharePortfolio(
        holdings=holdings, fetched_at=datetime.now(UTC), source="csv_import"
    )
