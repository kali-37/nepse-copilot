"""Retrievers: where evidence comes from.

Three implementations behind one small protocol, so the advisor can ask for
evidence without knowing whether the machine is online:

* :class:`LocalRetriever` — the FTS5 index over the local DB. Never touches the
  network. This is the only retriever used in offline mode, and it is enough:
  prices, indicators, quant stats, signals, data quality, fundamentals and
  corporate actions all live there.
* :class:`WebRetriever` — a live search plus page fetch, for the things a
  database cannot know (today's announcement, a policy change, a rumour).
  Online mode only.
* :class:`HybridRetriever` — local first; reaches for the web only when the local
  result set is thin. Cheap by default, thorough when it needs to be.

Web results are returned as ordinary :class:`Document` objects with ``kind="web"``
so downstream code treats a scraped page exactly like a DB-derived fact — same
citation mechanism, same size ceiling, same auditability.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, date, datetime
from typing import Protocol
from urllib.parse import parse_qs, unquote, urlparse

from nepse_trader.config import Settings, get_settings
from nepse_trader.rag.corpus import KIND_WEB, Document
from nepse_trader.rag.index import DocumentIndex, SearchHit

log = logging.getLogger("nepse_trader.rag.retrievers")

# Aggregators and social links crowd out primary sources; skip them.
_SKIP_HOSTS = (
    "duckduckgo.com",
    "google.com",
    "bing.com",
    "youtube.com",
    "facebook.com",
    "twitter.com",
    "x.com",
    "instagram.com",
    "linkedin.com",
    "pinterest.com",
)

_WS = re.compile(r"\s+")


class Retriever(Protocol):
    """Anything that can turn a query into ranked hits."""

    def retrieve(
        self,
        query: str,
        *,
        limit: int = 8,
        symbols: list[str] | None = None,
        kinds: list[str] | None = None,
        since: date | None = None,
    ) -> list[SearchHit]: ...


class LocalRetriever:
    """Retrieval from the local document index. Offline, always available."""

    def __init__(self, index: DocumentIndex) -> None:
        self.index = index

    def retrieve(
        self,
        query: str,
        *,
        limit: int = 8,
        symbols: list[str] | None = None,
        kinds: list[str] | None = None,
        since: date | None = None,
    ) -> list[SearchHit]:
        return self.index.search(
            query, limit=limit, symbols=symbols, kinds=kinds, since=since
        )


class WebRetriever:
    """Live search + page fetch. Requires online mode and a fetch client.

    The search endpoint is configurable (``rag_web_search_urls``) and defaults to
    DuckDuckGo's HTML endpoint, which needs no API key. Failures degrade to an
    empty list — a missing web leg must never break a run, since the local leg
    already carries the numbers.
    """

    def __init__(
        self,
        client=None,
        settings: Settings | None = None,
        *,
        enabled: bool | None = None,
        max_pages: int = 3,
        max_body_chars: int = 4_000,
    ) -> None:
        self.settings = settings or get_settings()
        self._client = client
        # Explicit `enabled` wins over the settings pair, so a caller that has
        # already resolved the mode (e.g. a `--online` flag) is not second-guessed.
        self.enabled = (
            (self.settings.rag_enable_web and self.settings.online)
            if enabled is None
            else enabled
        )
        self.max_pages = max_pages
        self.max_body_chars = max_body_chars

    @property
    def client(self):
        """Lazily built so constructing a WebRetriever opens no connection."""
        if self._client is None:
            from nepse_trader.ingest.base import BaseClient

            self._client = BaseClient(self.settings, cache_raw=False)
        return self._client

    def retrieve(
        self,
        query: str,
        *,
        limit: int = 8,
        symbols: list[str] | None = None,
        kinds: list[str] | None = None,
        since: date | None = None,
    ) -> list[SearchHit]:
        """Search the web and return fetched pages as hits.

        ``kinds`` and ``since`` are accepted for protocol compatibility and
        ignored — a live search has no kind taxonomy and no date index.
        """
        if not self.enabled:
            return []
        if not (query or "").strip():
            return []

        urls = self._search(query, limit=min(limit, self.max_pages))
        hits: list[SearchHit] = []
        for rank, url in enumerate(urls):
            doc = self._fetch_page(url, query)
            if doc is None:
                continue
            if symbols:
                doc.symbol = symbols[0]
            # Search-engine order is the only ranking signal available.
            hits.append(SearchHit(document=doc, score=1.0 / (rank + 1), matched_terms=[]))
        return hits

    def _search(self, query: str, *, limit: int) -> list[str]:
        """Result URLs from the configured search endpoint, best first."""
        from urllib.parse import quote_plus

        urls: list[str] = []
        for template in self.settings.rag_web_search_urls:
            if len(urls) >= limit:
                break
            try:
                search_url = template.format(query=quote_plus(query))
                result = self.client.fetch(search_url)
            except Exception as exc:  # noqa: BLE001 - web leg is best-effort
                log.warning("web search failed for %r: %s", query, exc)
                continue
            for url in extract_result_links(result.text):
                if url not in urls:
                    urls.append(url)
                if len(urls) >= limit:
                    break
        return urls

    def _fetch_page(self, url: str, query: str) -> Document | None:
        try:
            result = self.client.fetch(url)
        except Exception as exc:  # noqa: BLE001 - one dead link is not a failure
            log.debug("web fetch failed for %s: %s", url, exc)
            return None

        title, body = html_to_text(result.text, max_chars=self.max_body_chars)
        if not body:
            return None
        host = urlparse(url).netloc
        return Document(
            doc_id=f"{KIND_WEB}:{_url_key(url)}",
            kind=KIND_WEB,
            title=title or f"Web result from {host}",
            body=body,
            url=url,
            source=host,
            business_date=datetime.now(UTC).date(),
            fetched_at=result.fetched_at,
            metadata={"query": query},
        )


class HybridRetriever:
    """Local first, web only when the local result set is thin.

    ``min_local_hits`` is the threshold: at or above it, the web is never touched.
    That keeps a normal daily run entirely local even in online mode, and reserves
    network calls for genuinely under-covered queries.
    """

    def __init__(
        self,
        local: LocalRetriever,
        web: WebRetriever | None = None,
        *,
        min_local_hits: int = 3,
    ) -> None:
        self.local = local
        self.web = web
        self.min_local_hits = min_local_hits

    def retrieve(
        self,
        query: str,
        *,
        limit: int = 8,
        symbols: list[str] | None = None,
        kinds: list[str] | None = None,
        since: date | None = None,
    ) -> list[SearchHit]:
        hits = self.local.retrieve(
            query, limit=limit, symbols=symbols, kinds=kinds, since=since
        )
        if self.web is None or len(hits) >= self.min_local_hits:
            return hits

        remaining = max(limit - len(hits), 1)
        web_hits = self.web.retrieve(query, limit=remaining, symbols=symbols)
        # Local hits stay first: DB facts are verified, web text is not.
        return [*hits, *web_hits][:limit]


# ---------------------------------------------------------------------------
# Pure helpers — no network, so they're directly testable against fixtures.
# ---------------------------------------------------------------------------


def extract_result_links(html: str) -> list[str]:
    """Pull outbound result URLs from a search results page.

    DuckDuckGo's HTML endpoint wraps every result in a redirect
    (``/l/?uddg=<encoded>``), so those are unwrapped. Aggregator and social hosts
    are dropped, as are duplicates and non-http schemes.
    """
    if not html:
        return []

    from selectolax.parser import HTMLParser

    out: list[str] = []
    for node in HTMLParser(html).css("a"):
        href = node.attributes.get("href") or ""
        url = _unwrap_redirect(href)
        if not url or not url.startswith(("http://", "https://")):
            continue
        host = urlparse(url).netloc.lower().removeprefix("www.")
        if any(host == skip or host.endswith("." + skip) for skip in _SKIP_HOSTS):
            continue
        if url not in out:
            out.append(url)
    return out


def _unwrap_redirect(href: str) -> str:
    """Turn a search-engine redirect link into the destination URL."""
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if parsed.path.startswith("/l/") or "uddg" in (parsed.query or ""):
        target = parse_qs(parsed.query).get("uddg") or parse_qs(parsed.query).get("q")
        if target:
            return unquote(target[0])
    return href


def html_to_text(html: str, *, max_chars: int = 4_000) -> tuple[str, str]:
    """Reduce a page to ``(title, body_text)``, truncated to ``max_chars``.

    Script, style, nav and footer content is stripped first so the body is prose
    rather than menu labels. Truncation cuts at the last sentence boundary when
    one is nearby, so evidence never ends mid-word.
    """
    if not html:
        return ("", "")

    from selectolax.parser import HTMLParser

    tree = HTMLParser(html)
    tree.strip_tags(["script", "style", "noscript", "nav", "footer", "form", "svg"])

    title_node = tree.css_first("title")
    title = _WS.sub(" ", title_node.text(strip=True)).strip() if title_node else ""

    body_node = tree.css_first("article") or tree.css_first("main") or tree.body
    text = body_node.text(separator=" ", strip=True) if body_node else tree.text()
    text = _WS.sub(" ", text or "").strip()

    if len(text) > max_chars:
        cut = text[:max_chars]
        stop = cut.rfind(". ")
        text = (cut[: stop + 1] if stop > max_chars * 0.6 else cut).rstrip() + " …"
    return (title, text)


def _url_key(url: str) -> str:
    """Short stable id for a URL, so re-fetching the same page upserts."""
    import hashlib

    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def build_retriever(
    index: DocumentIndex,
    settings: Settings | None = None,
    *,
    online: bool | None = None,
) -> Retriever:
    """The right retriever for the current mode.

    Offline (or web disabled) gives a pure :class:`LocalRetriever`; online gives a
    :class:`HybridRetriever`. Call sites just ask for a retriever and get one that
    respects the mode, rather than each branching on ``online`` themselves.
    """
    settings = settings or get_settings()
    local = LocalRetriever(index)
    use_web = settings.rag_enable_web and (settings.online if online is None else online)
    if not use_web:
        return local
    return HybridRetriever(local, WebRetriever(settings=settings, enabled=True))
