"""Tests for the three retrievers.

The web leg is exercised entirely through respx-mocked HTTP and fixture HTML — no
test in this file reaches the network. What matters most here is the *mode*
contract: an offline run must make zero requests, and a thin local result must be
what triggers the web leg, not merely being online.
"""

from __future__ import annotations

import sqlite3
from datetime import date

import httpx
import pytest
import respx

from nepse_trader.config import Settings
from nepse_trader.ingest.base import BaseClient
from nepse_trader.rag.corpus import KIND_NEWS, KIND_PRICE, KIND_WEB, Document
from nepse_trader.rag.index import DocumentIndex
from nepse_trader.rag.retrievers import (
    HybridRetriever,
    LocalRetriever,
    WebRetriever,
    build_retriever,
    extract_result_links,
    html_to_text,
)
from nepse_trader.storage.migrations import run_pending

SEARCH_URL = "https://search.test/?q={query}"


def _settings(**kw) -> Settings:
    base = {
        "_env_file": None,
        "rag_web_search_urls": [SEARCH_URL],
        "min_request_interval": 0.0,
        "fetch_engine": "httpx",
    }
    base.update(kw)
    return Settings(**base)


def _index(docs: list[Document] | None = None) -> DocumentIndex:
    conn = sqlite3.connect(":memory:")
    run_pending(conn)
    conn.commit()
    idx = DocumentIndex(conn)
    if docs:
        idx.upsert(docs)
    return idx


def _price_docs(n: int) -> list[Document]:
    return [
        Document(
            doc_id=f"price:NABIL:2026-01-{i + 1:02d}",
            kind=KIND_PRICE,
            title=f"NABIL price on 2026-01-{i + 1:02d}",
            body=f"NABIL closed at NPR {500 + i}.00 on 2026-01-{i + 1:02d}.",
            symbol="NABIL",
            business_date=date(2026, 1, i + 1),
        )
        for i in range(n)
    ]


SEARCH_HTML = """
<html><body>
  <a href="/l/?uddg=https%3A%2F%2Fsharesansar.com%2Fnews%2F1">NABIL dividend news</a>
  <a href="/l/?uddg=https%3A%2F%2Fmerolagani.com%2Fnews%2F2">NABIL AGM notice</a>
  <a href="https://duckduckgo.com/settings">Settings</a>
  <a href="https://facebook.com/share">Share</a>
  <a href="/relative/page">Relative</a>
</body></html>
"""

PAGE_HTML = """
<html><head><title>NABIL declares 11% dividend</title></head>
<body>
  <nav>Home Markets News</nav>
  <script>var x = 1;</script>
  <article>Nabil Bank has declared an 11% cash dividend for the fiscal year.
  The book closure date is set for next month.</article>
  <footer>Copyright</footer>
</body></html>
"""


class TestExtractResultLinks:
    def test_unwraps_redirect_links(self):
        links = extract_result_links(SEARCH_HTML)
        assert "https://sharesansar.com/news/1" in links
        assert "https://merolagani.com/news/2" in links

    def test_drops_the_search_engine_and_social_hosts(self):
        links = extract_result_links(SEARCH_HTML)
        assert not any("duckduckgo" in url or "facebook" in url for url in links)

    def test_drops_relative_and_non_http_links(self):
        assert all(url.startswith("http") for url in extract_result_links(SEARCH_HTML))

    def test_preserves_result_order(self):
        links = extract_result_links(SEARCH_HTML)
        assert links.index("https://sharesansar.com/news/1") < links.index(
            "https://merolagani.com/news/2"
        )

    def test_deduplicates(self):
        html = '<a href="https://a.test/1">x</a><a href="https://a.test/1">y</a>'
        assert extract_result_links(html) == ["https://a.test/1"]

    def test_empty_html_yields_nothing(self):
        assert extract_result_links("") == []


class TestHtmlToText:
    def test_extracts_the_title(self):
        title, _ = html_to_text(PAGE_HTML)
        assert title == "NABIL declares 11% dividend"

    def test_extracts_article_prose(self):
        _, body = html_to_text(PAGE_HTML)
        assert "11% cash dividend" in body

    def test_strips_scripts_nav_and_footer(self):
        _, body = html_to_text(PAGE_HTML)
        assert "var x" not in body
        assert "Copyright" not in body

    def test_collapses_whitespace(self):
        _, body = html_to_text("<html><body><p>a\n\n   b</p></body></html>")
        assert body == "a b"

    def test_truncates_to_the_ceiling(self):
        long_html = f"<html><body><p>{'word ' * 5_000}</p></body></html>"
        _, body = html_to_text(long_html, max_chars=200)
        assert len(body) <= 210  # ceiling plus the ellipsis marker
        assert body.endswith("…")

    def test_empty_html_yields_empty_pair(self):
        assert html_to_text("") == ("", "")


class TestLocalRetriever:
    def test_returns_matching_documents(self):
        retriever = LocalRetriever(_index(_price_docs(3)))
        assert retriever.retrieve("NABIL closed")

    def test_respects_the_limit(self):
        retriever = LocalRetriever(_index(_price_docs(10)))
        assert len(retriever.retrieve("NABIL", limit=3)) == 3

    @respx.mock
    def test_makes_no_http_request(self):
        """The whole point of the local leg: it works with the network unplugged."""
        route = respx.get(url__startswith="https://").mock(return_value=httpx.Response(200))
        LocalRetriever(_index(_price_docs(3))).retrieve("NABIL")
        assert not route.called


class TestWebRetrieverGating:
    def test_disabled_when_offline(self):
        web = WebRetriever(settings=_settings(online=False), client=object())
        assert web.retrieve("NABIL dividend") == []

    def test_disabled_when_web_is_switched_off(self):
        web = WebRetriever(settings=_settings(online=True, rag_enable_web=False), client=object())
        assert web.retrieve("NABIL dividend") == []

    def test_explicit_enabled_overrides_settings(self):
        web = WebRetriever(settings=_settings(online=False), enabled=True)
        assert web.enabled is True

    def test_empty_query_makes_no_request(self):
        web = WebRetriever(settings=_settings(online=True), client=object())
        assert web.retrieve("   ") == []

    def test_constructing_it_opens_no_client(self):
        web = WebRetriever(settings=_settings(online=True))
        assert web._client is None  # noqa: SLF001 - laziness is the property under test


class TestWebRetrieverFetch:
    @respx.mock
    def test_returns_fetched_pages_as_web_documents(self):
        respx.get(url__startswith="https://search.test").mock(
            return_value=httpx.Response(200, text=SEARCH_HTML)
        )
        respx.get(url__startswith="https://sharesansar.com").mock(
            return_value=httpx.Response(200, text=PAGE_HTML)
        )
        respx.get(url__startswith="https://merolagani.com").mock(
            return_value=httpx.Response(200, text=PAGE_HTML)
        )

        settings = _settings(online=True)
        web = WebRetriever(client=BaseClient(settings, cache_raw=False), settings=settings)
        hits = web.retrieve("NABIL dividend", limit=2)

        assert hits
        assert all(h.document.kind == KIND_WEB for h in hits)
        assert all(h.document.url for h in hits)
        assert "11% cash dividend" in hits[0].document.body

    @respx.mock
    def test_ranks_by_search_result_order(self):
        respx.get(url__startswith="https://search.test").mock(
            return_value=httpx.Response(200, text=SEARCH_HTML)
        )
        respx.get(url__startswith="https://sharesansar.com").mock(
            return_value=httpx.Response(200, text=PAGE_HTML)
        )
        respx.get(url__startswith="https://merolagani.com").mock(
            return_value=httpx.Response(200, text=PAGE_HTML)
        )
        settings = _settings(online=True)
        web = WebRetriever(client=BaseClient(settings, cache_raw=False), settings=settings)
        hits = web.retrieve("NABIL dividend", limit=2)
        assert hits[0].score > hits[1].score

    @respx.mock
    def test_a_dead_link_is_skipped_not_fatal(self):
        respx.get(url__startswith="https://search.test").mock(
            return_value=httpx.Response(200, text=SEARCH_HTML)
        )
        respx.get(url__startswith="https://sharesansar.com").mock(
            return_value=httpx.Response(404, text="gone")
        )
        respx.get(url__startswith="https://merolagani.com").mock(
            return_value=httpx.Response(200, text=PAGE_HTML)
        )
        settings = _settings(online=True)
        web = WebRetriever(client=BaseClient(settings, cache_raw=False), settings=settings)
        hits = web.retrieve("NABIL dividend", limit=2)
        assert len(hits) == 1
        assert "merolagani" in hits[0].document.url

    @respx.mock
    def test_search_failure_degrades_to_empty(self):
        """A broken search endpoint must not break the run — the local leg has the numbers."""
        respx.get(url__startswith="https://search.test").mock(
            return_value=httpx.Response(404, text="not found")
        )
        settings = _settings(online=True)
        web = WebRetriever(client=BaseClient(settings, cache_raw=False), settings=settings)
        assert web.retrieve("NABIL dividend") == []

    @respx.mock
    def test_document_id_is_stable_for_a_url(self):
        respx.get(url__startswith="https://search.test").mock(
            return_value=httpx.Response(200, text=SEARCH_HTML)
        )
        respx.get(url__startswith="https://sharesansar.com").mock(
            return_value=httpx.Response(200, text=PAGE_HTML)
        )
        respx.get(url__startswith="https://merolagani.com").mock(
            return_value=httpx.Response(200, text=PAGE_HTML)
        )
        settings = _settings(online=True)

        def _first_id():
            web = WebRetriever(client=BaseClient(settings, cache_raw=False), settings=settings)
            return web.retrieve("NABIL dividend", limit=1)[0].document.doc_id

        assert _first_id() == _first_id()


class TestHybridRetriever:
    @respx.mock
    def test_web_untouched_when_local_results_suffice(self):
        """Online mode must still be free for ordinary queries the DB can answer."""
        route = respx.get(url__startswith="https://").mock(return_value=httpx.Response(200))
        settings = _settings(online=True)
        hybrid = HybridRetriever(
            LocalRetriever(_index(_price_docs(10))),
            WebRetriever(client=BaseClient(settings, cache_raw=False), settings=settings),
            min_local_hits=3,
        )
        hits = hybrid.retrieve("NABIL", limit=8)
        assert len(hits) >= 3
        assert not route.called

    @respx.mock
    def test_web_consulted_when_local_results_are_thin(self):
        respx.get(url__startswith="https://search.test").mock(
            return_value=httpx.Response(200, text=SEARCH_HTML)
        )
        respx.get(url__startswith="https://sharesansar.com").mock(
            return_value=httpx.Response(200, text=PAGE_HTML)
        )
        respx.get(url__startswith="https://merolagani.com").mock(
            return_value=httpx.Response(200, text=PAGE_HTML)
        )
        settings = _settings(online=True)
        hybrid = HybridRetriever(
            LocalRetriever(_index(_price_docs(1))),
            WebRetriever(client=BaseClient(settings, cache_raw=False), settings=settings),
            min_local_hits=3,
        )
        hits = hybrid.retrieve("NABIL dividend", limit=5)
        assert any(h.document.kind == KIND_WEB for h in hits)

    @respx.mock
    def test_local_hits_rank_above_web_hits(self):
        """DB facts are verified; scraped page text is not."""
        respx.get(url__startswith="https://search.test").mock(
            return_value=httpx.Response(200, text=SEARCH_HTML)
        )
        respx.get(url__startswith="https://sharesansar.com").mock(
            return_value=httpx.Response(200, text=PAGE_HTML)
        )
        respx.get(url__startswith="https://merolagani.com").mock(
            return_value=httpx.Response(200, text=PAGE_HTML)
        )
        settings = _settings(online=True)
        docs = [
            Document(
                doc_id="news:1",
                kind=KIND_NEWS,
                title="NABIL dividend announced",
                body="NABIL announces dividend.",
                symbol="NABIL",
                business_date=date(2026, 1, 5),
            )
        ]
        hybrid = HybridRetriever(
            LocalRetriever(_index(docs)),
            WebRetriever(client=BaseClient(settings, cache_raw=False), settings=settings),
            min_local_hits=3,
        )
        hits = hybrid.retrieve("NABIL dividend", limit=5)
        kinds = [h.document.kind for h in hits]
        assert kinds[0] == KIND_NEWS
        assert KIND_WEB in kinds

    def test_no_web_leg_configured_is_fine(self):
        hybrid = HybridRetriever(LocalRetriever(_index(_price_docs(1))), None)
        assert len(hybrid.retrieve("NABIL")) == 1

    def test_limit_holds_across_both_legs(self):
        local = LocalRetriever(_index(_price_docs(10)))
        hybrid = HybridRetriever(local, None, min_local_hits=3)
        assert len(hybrid.retrieve("NABIL", limit=4)) == 4


class TestBuildRetriever:
    def test_offline_gives_a_local_only_retriever(self):
        r = build_retriever(_index(), _settings(online=False))
        assert isinstance(r, LocalRetriever)

    def test_online_gives_a_hybrid_retriever(self):
        r = build_retriever(_index(), _settings(online=True))
        assert isinstance(r, HybridRetriever)

    def test_explicit_offline_overrides_online_settings(self):
        r = build_retriever(_index(), _settings(online=True), online=False)
        assert isinstance(r, LocalRetriever)

    def test_web_disabled_gives_local_even_when_online(self):
        r = build_retriever(_index(), _settings(online=True, rag_enable_web=False))
        assert isinstance(r, LocalRetriever)

    @pytest.mark.parametrize("online", [True, False])
    def test_always_returns_something_usable(self, online: bool):
        r = build_retriever(_index(_price_docs(3)), _settings(online=online), online=False)
        assert r.retrieve("NABIL")
