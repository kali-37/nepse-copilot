"""Tests for the FTS5 document index and its LIKE fallback.

The suite runs the *same* assertions against both search paths via the
``index`` fixture, which is parametrised over FTS5 and the fallback. That's the
point: a machine without FTS5 must still get correct — if less finely ranked —
results, and the only way to know that is to test both.
"""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from nepse_trader.rag.corpus import (
    KIND_INDICATOR,
    KIND_NEWS,
    KIND_PRICE,
    Document,
)
from nepse_trader.rag.index import DocumentIndex, to_match_query
from nepse_trader.storage.migrations import has_fts5, run_pending


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    run_pending(conn)
    conn.commit()
    return conn


def _conn_without_fts() -> sqlite3.Connection:
    """A DB in exactly the state migration 0003 leaves on a build lacking FTS5.

    The migration returns early there, so neither ``documents_fts`` nor its sync
    triggers exist. Dropping only the table would leave orphan triggers — a state
    that is unreachable in production and would test the wrong thing.
    """
    conn = _conn()
    conn.executescript("""
        DROP TRIGGER IF EXISTS documents_ai;
        DROP TRIGGER IF EXISTS documents_ad;
        DROP TRIGGER IF EXISTS documents_au;
        DROP TABLE IF EXISTS documents_fts;
    """)
    conn.commit()
    return conn


@pytest.fixture(params=["fts5", "like"])
def index(request: pytest.FixtureRequest) -> DocumentIndex:
    """A populated index, once with FTS5 and once forced onto the fallback."""
    conn = _conn()
    if request.param == "fts5" and not has_fts5(conn):
        pytest.skip("this SQLite build has no FTS5")

    idx = DocumentIndex(conn, use_fts=request.param == "fts5")
    idx.upsert(_corpus())
    return idx


def _corpus() -> list[Document]:
    return [
        Document(
            doc_id="price:NABIL:2026-01-05",
            kind=KIND_PRICE,
            title="NABIL price on 2026-01-05",
            body="On 2026-01-05, NABIL closed at NPR 512.00, up 1.20% from NPR 505.94.",
            symbol="NABIL",
            business_date=date(2026, 1, 5),
        ),
        Document(
            doc_id="price:ADBL:2026-01-05",
            kind=KIND_PRICE,
            title="ADBL price on 2026-01-05",
            body="On 2026-01-05, ADBL closed at NPR 310.00, down 0.80% from NPR 312.50.",
            symbol="ADBL",
            business_date=date(2026, 1, 5),
        ),
        Document(
            doc_id="indicator:NABIL:2026-01-05",
            kind=KIND_INDICATOR,
            title="NABIL indicators on 2026-01-05",
            body="RSI(14) 68.50 — neutral. MACD histogram positive, bullish momentum.",
            symbol="NABIL",
            business_date=date(2026, 1, 5),
        ),
        Document(
            doc_id="news:abc123",
            kind=KIND_NEWS,
            title="NABIL announces 11% dividend for shareholders",
            body="NABIL: NABIL announces 11% dividend for shareholders. Published 2026-01-04.",
            symbol="NABIL",
            business_date=date(2026, 1, 4),
            url="https://example.test/news/1",
            source="sharesansar",
        ),
        Document(
            doc_id="news:def456",
            kind=KIND_NEWS,
            title="Undated market commentary on liquidity",
            body="Interbank liquidity remains ample; lending rates unchanged.",
        ),
    ]


class TestMatchQuery:
    def test_terms_are_or_ed_with_prefix_wildcards(self):
        assert to_match_query("NABIL dividend") == '"NABIL"* OR "dividend"*'

    @pytest.mark.parametrize("raw", ['NABIL "quoted"', "NABIL (paren)", "NABIL -minus", "NABIL*"])
    def test_fts_syntax_characters_cannot_leak_through(self, raw: str):
        """A stray quote or hyphen must not become a MATCH syntax error."""
        built = to_match_query(raw)
        assert "NABIL" in built
        for ch in '()-':
            assert ch not in built.replace('"', "")

    def test_empty_input_yields_empty_expression(self):
        assert to_match_query("") == ""
        assert to_match_query("   ") == ""
        assert to_match_query("!!!") == ""

    def test_devanagari_terms_survive(self):
        assert "राशिफल" in to_match_query("राशिफल")


class TestUpsert:
    def test_count_reflects_written_documents(self, index: DocumentIndex):
        assert index.count() == 5
        assert index.count(KIND_PRICE) == 2

    def test_reupsert_updates_in_place(self, index: DocumentIndex):
        """Same id twice must not double-count — this is what daily re-indexing does."""
        before = index.count()
        index.upsert(_corpus())
        assert index.count() == before

    def test_body_change_is_visible_after_reupsert(self, index: DocumentIndex):
        updated = Document(
            doc_id="price:NABIL:2026-01-05",
            kind=KIND_PRICE,
            title="NABIL price on 2026-01-05",
            body="Revised: NABIL closed at NPR 999.00.",
            symbol="NABIL",
            business_date=date(2026, 1, 5),
        )
        index.upsert([updated])
        assert "999.00" in index.get("price:NABIL:2026-01-05").body

    def test_stale_terms_are_not_still_searchable(self, index: DocumentIndex):
        """The FTS shadow must be rewritten, not appended to, on update."""
        index.upsert(
            [
                Document(
                    doc_id="news:abc123",
                    kind=KIND_NEWS,
                    title="Replaced headline about buyback",
                    body="NABIL announces a share buyback.",
                    symbol="NABIL",
                    business_date=date(2026, 1, 4),
                )
            ]
        )
        hits = index.search("dividend", limit=10)
        assert "news:abc123" not in [h.document.doc_id for h in hits]

    def test_empty_list_is_a_no_op(self, index: DocumentIndex):
        assert index.upsert([]) == 0

    def test_kinds_returns_per_kind_counts(self, index: DocumentIndex):
        kinds = index.kinds()
        assert kinds[KIND_PRICE] == 2
        assert kinds[KIND_NEWS] == 2

    def test_delete_kind_removes_only_that_kind(self, index: DocumentIndex):
        index.delete_kind(KIND_NEWS)
        assert index.count(KIND_NEWS) == 0
        assert index.count(KIND_PRICE) == 2

    def test_get_missing_id_returns_none(self, index: DocumentIndex):
        assert index.get("nope:1") is None

    def test_roundtrip_preserves_every_field(self, index: DocumentIndex):
        doc = index.get("news:abc123")
        assert doc.kind == KIND_NEWS
        assert doc.symbol == "NABIL"
        assert doc.business_date == date(2026, 1, 4)
        assert doc.url == "https://example.test/news/1"
        assert doc.source == "sharesansar"


class TestSearch:
    def test_finds_the_relevant_document(self, index: DocumentIndex):
        hits = index.search("dividend")
        assert hits
        assert hits[0].document.doc_id == "news:abc123"

    def test_reports_which_terms_matched(self, index: DocumentIndex):
        hits = index.search("dividend")
        assert "dividend" in hits[0].matched_terms

    def test_scores_are_bigger_is_better(self, index: DocumentIndex):
        """Both paths must agree on score direction, or ranking silently inverts."""
        hits = index.search("NABIL")
        assert len(hits) > 1
        assert hits[0].score >= hits[-1].score

    def test_limit_is_respected(self, index: DocumentIndex):
        assert len(index.search("NABIL", limit=2)) <= 2

    def test_no_match_returns_empty(self, index: DocumentIndex):
        assert index.search("zzzznonexistentzzzz") == []

    def test_symbol_filter_excludes_other_symbols(self, index: DocumentIndex):
        hits = index.search("closed", symbols=["NABIL"])
        assert hits
        assert {h.document.symbol for h in hits} == {"NABIL"}

    def test_kind_filter_excludes_other_kinds(self, index: DocumentIndex):
        hits = index.search("NABIL", kinds=[KIND_INDICATOR])
        assert hits
        assert {h.document.kind for h in hits} == {KIND_INDICATOR}

    def test_since_filter_excludes_older_documents(self, index: DocumentIndex):
        hits = index.search("NABIL", since=date(2026, 1, 5))
        ids = [h.document.doc_id for h in hits]
        assert "news:abc123" not in ids  # dated 2026-01-04

    def test_since_keeps_undated_documents(self, index: DocumentIndex):
        """An undated document has no date to fail the filter with."""
        hits = index.search("liquidity", since=date(2026, 1, 5))
        assert [h.document.doc_id for h in hits] == ["news:def456"]

    def test_empty_query_falls_back_to_recency(self, index: DocumentIndex):
        hits = index.search("", limit=3)
        assert hits
        assert hits[0].document.business_date == date(2026, 1, 5)

    def test_citation_is_the_document_id(self, index: DocumentIndex):
        assert index.search("dividend")[0].citation == "news:abc123"


class TestRecent:
    def test_newest_first(self, index: DocumentIndex):
        docs = index.recent(limit=3)
        dates = [d.business_date for d in docs if d.business_date]
        assert dates == sorted(dates, reverse=True)

    def test_undated_documents_sort_last(self, index: DocumentIndex):
        docs = index.recent(limit=10)
        assert docs[-1].doc_id == "news:def456"

    def test_symbol_filter_applies(self, index: DocumentIndex):
        docs = index.recent(limit=10, symbols=["ADBL"])
        assert [d.symbol for d in docs] == ["ADBL"]


class TestFtsDetection:
    def test_uses_fts_when_the_table_exists(self):
        conn = _conn()
        if not has_fts5(conn):
            pytest.skip("this SQLite build has no FTS5")
        assert DocumentIndex(conn).uses_fts is True

    def test_falls_back_when_the_fts_table_is_missing(self):
        """Migration 0003 skips documents_fts on a build without FTS5."""
        assert DocumentIndex(_conn_without_fts()).uses_fts is False

    def test_fallback_index_still_searches(self):
        idx = DocumentIndex(_conn_without_fts())
        idx.upsert(_corpus())
        assert idx.search("dividend")[0].document.doc_id == "news:abc123"
