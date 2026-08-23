"""Tests for news + announcement ingestion.

Two things carry this module and are asserted directly:

* **Conservative symbol tagging** — without a known-symbol set, tagging must
  return nothing. A wrongly tagged headline attaches real news to the wrong
  company, which is worse than an untagged (but still word-searchable) document.
* **Deterministic ids** — re-ingesting the same headline must upsert, not
  duplicate, exactly as with the DB-derived corpus.
"""

from __future__ import annotations

from datetime import date, datetime

import httpx
import pytest
import respx

from nepse_trader.config import Settings
from nepse_trader.ingest.base import BaseClient
from nepse_trader.ingest.news import NewsClient, extract_symbols
from nepse_trader.models import SourceName
from nepse_trader.rag.corpus import KIND_NEWS

KNOWN = {"NABIL", "ADBL", "NICA", "HBL", "SCB"}

NEWS_HTML = """
<html><body>
  <div class="featured-news-list">
    <div class="item">
      <h4><a href="/newsdetail/1">NABIL declares 11% cash dividend for shareholders</a></h4>
      <span class="text-org">2026-01-05</span>
    </div>
    <div class="item">
      <h4><a href="https://www.sharesansar.com/newsdetail/2">Interbank rates ease as liquidity improves in banking system</a></h4>
      <span class="text-org">2026-01-04</span>
    </div>
  </div>
  <div class="news-list">
    <a href="/tag/nepse">NEPSE</a>
    <a href="/newsdetail/3">ADBL and NICA both post double digit profit growth</a>
  </div>
</body></html>
"""

ANNOUNCEMENT_HTML = """
<html><body>
<table id="headFixed">
  <thead><tr><th>S.No</th><th>Headline</th><th>Symbol</th><th>Date</th></tr></thead>
  <tbody>
    <tr><td>1</td><td>Book closure for 11% dividend</td><td>NABIL</td><td>2026-01-05</td></tr>
    <tr><td>2</td><td>32nd AGM notice</td><td>ADBL</td><td>2026-01-04</td></tr>
    <tr><td>3</td><td>Malformed row</td><td>HBL</td></tr>
    <tr><td>4</td><td></td><td>SCB</td><td>2026-01-03</td></tr>
  </tbody>
</table>
</body></html>
"""


def _client() -> NewsClient:
    settings = Settings(_env_file=None, min_request_interval=0.0, fetch_engine="httpx")
    return NewsClient(client=BaseClient(settings, cache_raw=False), source_spec=None)


class TestExtractSymbols:
    def test_refuses_to_guess_without_a_known_set(self):
        """No known-symbol set means no tagging — mistagging is worse than nothing."""
        assert extract_symbols("NABIL declares dividend", None) == []
        assert extract_symbols("NABIL declares dividend", set()) == []

    def test_finds_known_symbols(self):
        assert extract_symbols("NABIL declares dividend", KNOWN) == ["NABIL"]

    def test_ignores_unknown_uppercase_tokens(self):
        assert extract_symbols("XYZQ declares dividend", KNOWN) == []

    def test_filters_market_acronyms(self):
        assert extract_symbols("NEPSE and SEBON meet on IPO rules", KNOWN | {"NEPSE"}) == []

    def test_first_seen_order_preserved_without_duplicates(self):
        text = "ADBL and NABIL rose; ADBL led"
        assert extract_symbols(text, KNOWN) == ["ADBL", "NABIL"]

    def test_lowercase_mentions_are_not_symbols(self):
        assert extract_symbols("nabil bank declares dividend", KNOWN) == []

    def test_empty_text_yields_nothing(self):
        assert extract_symbols("", KNOWN) == []


class TestParseNewsList:
    def test_extracts_headlines(self):
        docs = NewsClient.parse_news_list(NEWS_HTML, known_symbols=KNOWN)
        titles = [d.title for d in docs]
        assert "NABIL declares 11% cash dividend for shareholders" in titles

    def test_skips_short_nav_links(self):
        docs = NewsClient.parse_news_list(NEWS_HTML, known_symbols=KNOWN)
        assert "NEPSE" not in [d.title for d in docs]

    def test_makes_relative_urls_absolute(self):
        docs = NewsClient.parse_news_list(NEWS_HTML, known_symbols=KNOWN)
        assert all(d.url.startswith("https://") for d in docs if d.url)

    def test_absolute_urls_are_left_alone(self):
        docs = NewsClient.parse_news_list(NEWS_HTML, known_symbols=KNOWN)
        urls = [d.url for d in docs]
        assert "https://www.sharesansar.com/newsdetail/2" in urls

    def test_tags_the_primary_symbol(self):
        docs = NewsClient.parse_news_list(NEWS_HTML, known_symbols=KNOWN)
        nabil = next(d for d in docs if d.title.startswith("NABIL"))
        assert nabil.symbol == "NABIL"

    def test_secondary_mentions_are_recorded_in_the_body(self):
        docs = NewsClient.parse_news_list(NEWS_HTML, known_symbols=KNOWN)
        multi = next(d for d in docs if d.title.startswith("ADBL"))
        assert multi.symbol == "ADBL"
        assert "NICA" in multi.body

    def test_untagged_headline_has_no_symbol(self):
        docs = NewsClient.parse_news_list(NEWS_HTML, known_symbols=KNOWN)
        general = next(d for d in docs if d.title.startswith("Interbank"))
        assert general.symbol is None

    def test_reads_the_adjacent_date(self):
        docs = NewsClient.parse_news_list(NEWS_HTML, known_symbols=KNOWN)
        nabil = next(d for d in docs if d.title.startswith("NABIL"))
        assert nabil.business_date == date(2026, 1, 5)

    def test_a_percentage_in_the_headline_is_not_read_as_a_date(self):
        """Fuzzy date parsing would turn "11% dividend" into the 11th of this month."""
        html = """
        <html><body><div class="news-list">
          <h4><a href="/newsdetail/9">NABIL declares 11% cash dividend for shareholders</a></h4>
        </div></body></html>
        """
        docs = NewsClient.parse_news_list(html, known_symbols=KNOWN)
        assert docs
        assert docs[0].business_date is None

    def test_undated_headline_stays_undated(self):
        html = '<html><body><h4><a href="/x">Market commentary on liquidity trends</a></h4></body></html>'
        docs = NewsClient.parse_news_list(html)
        assert docs
        assert docs[0].business_date is None

    def test_deduplicates_repeated_links(self):
        doubled = NEWS_HTML + NEWS_HTML
        once = len(NewsClient.parse_news_list(NEWS_HTML, known_symbols=KNOWN))
        assert len(NewsClient.parse_news_list(doubled, known_symbols=KNOWN)) == once

    def test_documents_are_news_kind(self):
        docs = NewsClient.parse_news_list(NEWS_HTML, known_symbols=KNOWN)
        assert docs
        assert {d.kind for d in docs} == {KIND_NEWS}

    def test_empty_html_yields_nothing(self):
        assert NewsClient.parse_news_list("") == []


class TestParseAnnouncements:
    def test_reads_every_complete_row(self):
        docs = NewsClient.parse_announcements(ANNOUNCEMENT_HTML)
        assert [d.symbol for d in docs] == ["NABIL", "ADBL"]

    def test_symbol_column_is_authoritative(self):
        """No known-symbol set needed here — the table states the symbol."""
        docs = NewsClient.parse_announcements(ANNOUNCEMENT_HTML, known_symbols=None)
        assert docs[0].symbol == "NABIL"

    def test_body_carries_symbol_and_headline(self):
        docs = NewsClient.parse_announcements(ANNOUNCEMENT_HTML)
        assert docs[0].body.startswith("NABIL: Book closure for 11% dividend")

    def test_date_is_parsed(self):
        docs = NewsClient.parse_announcements(ANNOUNCEMENT_HTML)
        assert docs[0].business_date == date(2026, 1, 5)

    @pytest.mark.parametrize(
        ("cell", "expected"),
        [
            ("2026-01-05", date(2026, 1, 5)),
            ("2026/01/05", date(2026, 1, 5)),
            ("Jan 5, 2026", date(2026, 1, 5)),
            ("5 Jan 2026", date(2026, 1, 5)),
            ("-", None),
            ("", None),
            ("11% dividend", None),
            ("Q2 results", None),
        ],
    )
    def test_date_column_shapes(self, cell: str, expected: date | None):
        html = ANNOUNCEMENT_HTML.replace(
            "<td>2026-01-05</td>", f"<td>{cell}</td>", 1
        )
        docs = NewsClient.parse_announcements(html)
        assert docs[0].business_date == expected

    def test_short_rows_are_skipped(self):
        docs = NewsClient.parse_announcements(ANNOUNCEMENT_HTML)
        assert "HBL" not in [d.symbol for d in docs]

    def test_rows_without_a_headline_are_skipped(self):
        docs = NewsClient.parse_announcements(ANNOUNCEMENT_HTML)
        assert "SCB" not in [d.symbol for d in docs]

    def test_records_the_source(self):
        docs = NewsClient.parse_announcements(ANNOUNCEMENT_HTML, source=SourceName.SHARESANSAR)
        assert docs[0].source == SourceName.SHARESANSAR.value

    def test_fetched_at_is_carried_through(self):
        stamp = datetime(2026, 1, 5, 9, 30)
        docs = NewsClient.parse_announcements(ANNOUNCEMENT_HTML, fetched_at=stamp)
        assert docs[0].fetched_at == stamp

    def test_empty_html_yields_nothing(self):
        assert NewsClient.parse_announcements("") == []


class TestDeterministicIds:
    def test_reparsing_gives_identical_ids(self):
        """Daily re-ingestion must upsert, not accumulate."""
        first = [d.doc_id for d in NewsClient.parse_announcements(ANNOUNCEMENT_HTML)]
        second = [d.doc_id for d in NewsClient.parse_announcements(ANNOUNCEMENT_HTML)]
        assert first == second

    def test_ids_are_unique_within_a_page(self):
        ids = [d.doc_id for d in NewsClient.parse_news_list(NEWS_HTML, known_symbols=KNOWN)]
        assert len(ids) == len(set(ids))

    def test_different_headlines_get_different_ids(self):
        docs = NewsClient.parse_announcements(ANNOUNCEMENT_HTML)
        assert docs[0].doc_id != docs[1].doc_id

    def test_id_is_case_insensitive_on_the_headline(self):
        """Sites reflow capitalisation; that must not spawn a duplicate document."""
        upper = ANNOUNCEMENT_HTML.replace(
            "Book closure for 11% dividend", "BOOK CLOSURE FOR 11% DIVIDEND"
        )
        a = NewsClient.parse_announcements(ANNOUNCEMENT_HTML)[0].doc_id
        b = NewsClient.parse_announcements(upper)[0].doc_id
        assert a == b


class TestFetch:
    @respx.mock
    def test_fetch_announcements_parses_the_response(self):
        respx.get(url__startswith="https://www.sharesansar.com/announcements").mock(
            return_value=httpx.Response(200, text=ANNOUNCEMENT_HTML)
        )
        docs = _client().fetch_announcements()
        assert [d.symbol for d in docs] == ["NABIL", "ADBL"]

    @respx.mock
    def test_fetch_news_parses_the_response(self):
        respx.get(url__startswith="https://www.sharesansar.com/category/latest").mock(
            return_value=httpx.Response(200, text=NEWS_HTML)
        )
        assert _client().fetch_news(KNOWN)

    @respx.mock
    def test_fetch_failure_degrades_to_empty(self):
        """A missing news leg costs commentary, never numbers — it must not raise."""
        respx.get(url__startswith="https://www.sharesansar.com").mock(
            return_value=httpx.Response(404, text="nope")
        )
        assert _client().fetch_announcements() == []

    @respx.mock
    def test_fetch_all_merges_both_listings(self):
        respx.get(url__startswith="https://www.sharesansar.com/announcements").mock(
            return_value=httpx.Response(200, text=ANNOUNCEMENT_HTML)
        )
        respx.get(url__startswith="https://www.sharesansar.com/category/latest").mock(
            return_value=httpx.Response(200, text=NEWS_HTML)
        )
        docs = _client().fetch_all(KNOWN)
        ids = [d.doc_id for d in docs]
        assert len(ids) == len(set(ids))
        assert len(docs) > 2
