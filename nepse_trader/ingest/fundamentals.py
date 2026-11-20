"""Fundamentals data scraping from MeroLagani company detail pages."""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime

from selectolax.parser import HTMLParser

from nepse_trader.config import SourceSpec
from nepse_trader.ingest.base import BaseClient, SourceClient
from nepse_trader.models import FundamentalData


class MeroLaganiFundamentalsClient(SourceClient):
    """Fetch fundamental data for a single symbol from MeroLagani."""

    name = "merolagani_fundamentals"
    source = "merolagani"

    BASE_URL = "https://merolagani.com/CompanyDetail.aspx"

    def __init__(
        self,
        client: BaseClient | None = None,
        source_spec: SourceSpec | None = None,
    ) -> None:
        super().__init__()
        self.client = client if client is not None else BaseClient()

    def fetch_fundamentals(self, symbol: str) -> FundamentalData | None:
        """Fetch and parse fundamentals for *symbol*."""
        try:
            resp = self.client.fetch(self.BASE_URL, params={"symbol": symbol.upper()})
        except Exception:
            return None

        if resp.status_code != 200 or not resp.text:
            return None

        return self._parse_page(resp.text, symbol)

    def _parse_page(self, html: str, symbol: str) -> FundamentalData | None:
        parser = HTMLParser(html)
        data: dict[str, str] = {}

        # MeroLagani company detail: key-value pairs in styled divs.
        # Each row has a label (e.g. "Sector", "EPS") and a value.
        for row in parser.css("div.company_detail"):
            cells = list(row.iter())
            cells = [c for c in cells if c.tag == "div"]
            if len(cells) >= 2:
                key = cells[0].text(strip=True)
                val = cells[1].text(strip=True)
                data[key] = val

        # Also try the summary table at top
        for row in parser.css("table.company_summary tr"):
            tds = row.css("td")
            if len(tds) >= 2:
                key = tds[0].text(strip=True)
                val = tds[1].text(strip=True)
                data[key] = val

        # Current company pages use a th/td accordion instead of div rows.
        for row in parser.css("table#accordion tr"):
            header = row.css_first("th")
            cell = row.css_first("td")
            if header is not None and cell is not None:
                data.setdefault(header.text(strip=True), cell.text(strip=True))
        company_name = parser.css_first('span[id$="_companyName"]')
        if company_name is not None:
            data.setdefault("Company Name", company_name.text(strip=True))

        def _num(v: object) -> float | None:
            if v is None:
                return None
            s = str(v).replace(",", "").strip()
            if s == "-" or not s:
                return None
            try:
                match = re.match(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)", s)
                value = float(match.group()) if match else None
                return value if value is not None and math.isfinite(value) else None
            except ValueError:
                return None

        def _strip_label(v: str | None) -> str | None:
            if v is None:
                return None
            return v.strip().strip(":").strip()

        symbol_data = FundamentalData(
            symbol=symbol,
            company_name=_strip_label(data.get("Company Name")) or "",
            sector=_strip_label(data.get("Sector")) or "",
            shares_outstanding=_num(data.get("Shares Outstanding") or data.get("Listed Shares")),
            market_price=_num(data.get("Market Price")),
            eps=_num(data.get("EPS")),
            pe_ratio=_num(data.get("P/E Ratio")),
            book_value=_num(data.get("Book Value")),
            pbv=_num(data.get("PBV")),
            dividend_pct=_num(data.get("% Dividend") or data.get("Dividend")),
            market_cap=_num(data.get("Market Capitalization")),
            avg_volume_30d=int(_num(data.get("30-Day Avg Volume")) or 0) or None,
            fetched_at=datetime.now(UTC),
        )

        # Parse 52-week high/low from the "52 Weeks High - Low" field
        hl = _strip_label(data.get("52 Weeks High - Low"))
        if hl and "-" in hl:
            parts = hl.replace(",", "").split("-")
            if len(parts) == 2:
                symbol_data.high_52w = _num(parts[0].strip())
                symbol_data.low_52w = _num(parts[1].strip())

        return symbol_data
