"""News and company announcements — the RAG corpus the database cannot derive.

Prices, indicators and quant stats are all computable from what's already stored.
Why a stock moved is not. This module pulls ShareSansar's news and announcement
listings and turns them into :class:`~nepse_trader.rag.corpus.Document` objects.

Same split as every other ingest module: ``parse_*`` staticmethods are pure and
fixture-testable, ``fetch_*`` wraps them with the polite HTTP client and degrades
to ``[]`` on failure. A missing news leg costs commentary, never numbers.

Symbol tagging is deliberately conservative: a headline is only tagged with a
symbol when that symbol appears as a standalone uppercase token *and* is in the
known-symbol set. Guessing here would attach real news to the wrong company,
which is worse than leaving it untagged.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime

from nepse_trader.config import SourceSpec, load_sources
from nepse_trader.ingest.base import BaseClient, FetchError, RateLimitedError
from nepse_trader.ingest.htmlparse import table_rows, td_texts
from nepse_trader.models import SourceName
from nepse_trader.rag.corpus import KIND_NEWS, Document

log = logging.getLogger("nepse_trader.ingest.news")

_DEFAULT_URLS: dict[str, str] = {
    "news": "https://www.sharesansar.com/category/latest",
    "announcements": "https://www.sharesansar.com/announcements",
}

# A standalone all-caps token, 3–10 chars — the shape of a NEPSE symbol.
_SYMBOL_TOKEN = re.compile(r"\b([A-Z][A-Z0-9]{2,9})\b")
_WS = re.compile(r"\s+")

# Date shapes worth handing to dateutil. Anything else stays undated rather than
# being fuzzy-guessed out of prose — see _parse_date.
_DATE_LIKE = re.compile(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{4}")
_MONTH_NAME_DATE = re.compile(
    r"(?:\d{1,2}\s+)?"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"
    r"\.?\s+\d{1,2},?\s+\d{4}|"
    r"\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}",
    re.IGNORECASE,
)

# Words that look like symbols but never are.
_NOT_SYMBOLS = frozenset(
    {
        "NEPSE", "SEBON", "CDSC", "NRB", "AGM", "SGM", "EPS", "IPO", "FPO",
        "NPR", "USD", "CEO", "CFO", "MD", "LTD", "PVT", "AND", "THE", "FOR",
        "NEW", "ALL", "NOT", "GDP", "GST", "VAT", "ATM", "DP", "TMS", "ASBA",
        "BFI", "BFIS", "MF", "NAV", "QTR", "FY", "PDF", "NEWS",
    }
)


class NewsClient:
    """ShareSansar news + announcement listings as retrievable documents."""

    name: SourceName = SourceName.SHARESANSAR

    def __init__(
        self,
        client: BaseClient | None = None,
        source_spec: SourceSpec | None = None,
    ) -> None:
        self.client = client if client is not None else BaseClient()
        if source_spec is None:
            source_spec = load_sources().get("sharesansar")
        self.source_spec = source_spec

    def _url(self, key: str) -> str:
        if self.source_spec is not None:
            ep = self.source_spec.endpoints.get(key)
            if ep is not None and ep.url:
                return ep.url
        return _DEFAULT_URLS[key]

    # -- pure parsers --------------------------------------------------------

    @staticmethod
    def parse_news_list(
        html: str,
        *,
        known_symbols: set[str] | None = None,
        source: SourceName = SourceName.SHARESANSAR,
        fetched_at: datetime | None = None,
    ) -> list[Document]:
        """Parse a ShareSansar news listing page into news documents.

        The listing is a repeated card structure rather than a table, so this
        walks anchors inside the featured/news blocks and reads the headline text
        plus any adjacent date.
        """
        if not html:
            return []

        from selectolax.parser import HTMLParser

        tree = HTMLParser(html)
        tree.strip_tags(["script", "style", "noscript"])

        docs: list[Document] = []
        seen: set[str] = set()

        for node in tree.css("h4 a, h3 a, .featured-news-list a, .news-list a"):
            headline = _clean(node.text(strip=True))
            if len(headline) < 20:  # nav links and tags, not headlines
                continue
            url = node.attributes.get("href") or None
            if url and url.startswith("/"):
                url = "https://www.sharesansar.com" + url

            published = _nearby_date(node)
            key = url or headline
            if key in seen:
                continue
            seen.add(key)

            docs.append(
                _news_document(
                    headline=headline,
                    body=headline,
                    url=url,
                    published=published,
                    known_symbols=known_symbols,
                    source=source,
                    fetched_at=fetched_at,
                )
            )
        return docs

    @staticmethod
    def parse_announcements(
        html: str,
        *,
        known_symbols: set[str] | None = None,
        source: SourceName = SourceName.SHARESANSAR,
        fetched_at: datetime | None = None,
    ) -> list[Document]:
        """Parse the announcements table into documents.

        Columns are ``S.No | Headline | Symbol | Date``. The symbol column is
        authoritative here, so no headline guessing is needed.
        """
        rows = table_rows(html or "", "#headFixed") or table_rows(html or "", "table")
        docs: list[Document] = []
        seen: set[str] = set()

        for row in rows:
            cells = td_texts(row)
            if len(cells) < 4:
                continue
            headline = _clean(cells[1])
            symbol = re.sub(r"[^A-Z0-9]", "", cells[2].strip().upper())
            published = _parse_date(cells[3])
            if not headline or not symbol or symbol == "SNO":
                continue

            key = f"{symbol}:{published}:{headline[:60]}"
            if key in seen:
                continue
            seen.add(key)

            docs.append(
                _news_document(
                    headline=headline,
                    body=f"{symbol}: {headline}",
                    url=None,
                    published=published,
                    symbol=symbol,
                    known_symbols=known_symbols,
                    source=source,
                    fetched_at=fetched_at,
                )
            )
        return docs

    # -- fetchers (network; failures degrade to []) --------------------------

    def fetch_news(self, known_symbols: set[str] | None = None) -> list[Document]:
        try:
            result = self.client.fetch(self._url("news"))
        except (FetchError, RateLimitedError, ValueError) as exc:
            log.warning("news fetch failed: %s", exc)
            return []
        return self.parse_news_list(
            result.text,
            known_symbols=known_symbols,
            source=self.name,
            fetched_at=result.fetched_at,
        )

    def fetch_announcements(self, known_symbols: set[str] | None = None) -> list[Document]:
        try:
            result = self.client.fetch(self._url("announcements"), params={"tag": "all"})
        except (FetchError, RateLimitedError, ValueError) as exc:
            log.warning("announcement fetch failed: %s", exc)
            return []
        return self.parse_announcements(
            result.text,
            known_symbols=known_symbols,
            source=self.name,
            fetched_at=result.fetched_at,
        )

    def fetch_all(self, known_symbols: set[str] | None = None) -> list[Document]:
        """News plus announcements, deduplicated by ``doc_id``."""
        docs = [
            *self.fetch_announcements(known_symbols),
            *self.fetch_news(known_symbols),
        ]
        out: dict[str, Document] = {}
        for doc in docs:
            out.setdefault(doc.doc_id, doc)
        return list(out.values())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def extract_symbols(text: str, known_symbols: set[str] | None) -> list[str]:
    """Symbols mentioned in *text*, in first-seen order.

    Without a ``known_symbols`` set this returns nothing rather than guessing —
    an untagged document is still searchable by its words, but a wrongly tagged
    one attaches real news to the wrong company.
    """
    if not text or not known_symbols:
        return []
    found: list[str] = []
    for token in _SYMBOL_TOKEN.findall(text):
        if token in _NOT_SYMBOLS or token not in known_symbols:
            continue
        if token not in found:
            found.append(token)
    return found


def _news_document(
    *,
    headline: str,
    body: str,
    url: str | None,
    published: date | None,
    known_symbols: set[str] | None,
    source: SourceName,
    fetched_at: datetime | None,
    symbol: str | None = None,
) -> Document:
    tagged = [symbol] if symbol else extract_symbols(headline, known_symbols)
    primary = tagged[0] if tagged else None

    full_body = body
    if len(tagged) > 1:
        full_body += f" (also mentions {', '.join(tagged[1:])})"
    if published:
        full_body += f" Published {published.isoformat()}."

    return Document(
        doc_id=f"{KIND_NEWS}:{_headline_key(headline, published)}",
        kind=KIND_NEWS,
        title=headline,
        body=full_body,
        symbol=primary,
        business_date=published,
        url=url,
        source=source.value,
        fetched_at=fetched_at,
        metadata={"symbols": tagged},
    )


def _headline_key(headline: str, published: date | None) -> str:
    """Stable id from the headline text, so re-ingesting upserts."""
    import hashlib

    seed = f"{published.isoformat() if published else ''}|{headline.strip().lower()}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _clean(text: str) -> str:
    return _WS.sub(" ", text or "").strip()


def _nearby_date(node) -> date | None:
    """Look for a date in the node's siblings and enclosing card."""
    parent = node.parent
    for _ in range(3):
        if parent is None:
            return None
        found = _parse_date(_clean(parent.text(strip=True))[:200])
        if found:
            return found
        parent = parent.parent
    return None


def _parse_date(value: str) -> date | None:
    """Parse a date out of *value*, or None.

    Only a substring that actually looks like a date is handed to the parser.
    Fuzzy-parsing raw prose would hallucinate: "11% cash dividend" yields day 11
    with the month and year silently defaulted to today, which would date a
    headline wrongly rather than leave it undated.
    """
    text = (value or "").strip()
    if not text or text in ("-", "--"):
        return None
    match = _DATE_LIKE.search(text) or _MONTH_NAME_DATE.search(text)
    if not match:
        return None
    try:
        from dateutil import parser as _dtparser

        return _dtparser.parse(match.group(0)).date()
    except (ValueError, OverflowError, TypeError):
        return None
