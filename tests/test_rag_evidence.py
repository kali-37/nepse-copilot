"""Tests for evidence packing.

The pack is the only thing standing between a retriever and a prompt, so its two
ceilings (document count, character count) and its citation markers are what
these tests pin down. Truncation must be visible, never silent — a pack that
quietly dropped half its evidence would read as complete.
"""

from __future__ import annotations

from datetime import date

import pytest

from nepse_trader.rag.corpus import KIND_INDICATOR, KIND_NEWS, KIND_PRICE, Document
from nepse_trader.rag.evidence import EvidencePack, build_evidence
from nepse_trader.rag.index import SearchHit


def _doc(doc_id: str, kind: str = KIND_PRICE, body: str = "body text", **kw) -> Document:
    return Document(
        doc_id=doc_id,
        kind=kind,
        title=kw.pop("title", f"Title for {doc_id}"),
        body=body,
        **kw,
    )


def _hit(doc: Document, score: float = 1.0) -> SearchHit:
    return SearchHit(document=doc, score=score, matched_terms=[])


class TestMarkers:
    def test_markers_are_sequential_from_one(self):
        pack = build_evidence([_hit(_doc(f"d{i}")) for i in range(3)])
        assert pack.markers == ["[E1]", "[E2]", "[E3]"]

    def test_citation_map_ties_markers_to_document_ids(self):
        pack = build_evidence([_hit(_doc("price:NABIL:2026-01-05"))])
        assert pack.citation_map() == {"[E1]": "price:NABIL:2026-01-05"}

    def test_marker_appears_in_the_rendered_block(self):
        assert "[E1]" in build_evidence([_hit(_doc("d1"))]).render()


class TestDocumentCeiling:
    def test_never_exceeds_max_documents(self):
        pack = build_evidence([_hit(_doc(f"d{i}")) for i in range(20)], max_documents=5)
        assert len(pack) == 5

    def test_truncation_is_flagged(self):
        pack = build_evidence([_hit(_doc(f"d{i}")) for i in range(20)], max_documents=5)
        assert pack.truncated is True
        assert pack.considered == 20

    def test_no_flag_when_everything_fits(self):
        pack = build_evidence([_hit(_doc(f"d{i}")) for i in range(3)], max_documents=5)
        assert pack.truncated is False

    def test_truncation_is_stated_in_the_rendered_block(self):
        """A prompt must not be told it has all the evidence when it doesn't."""
        rendered = build_evidence(
            [_hit(_doc(f"d{i}")) for i in range(20)], max_documents=2
        ).render()
        assert "truncated" in rendered
        assert "20" in rendered


class TestCharCeiling:
    def test_stops_before_exceeding_max_chars(self):
        docs = [_hit(_doc(f"d{i}", body="x" * 500)) for i in range(20)]
        pack = build_evidence(docs, max_documents=20, max_chars=1_200)
        assert len(pack.render()) <= 1_500  # ceiling + the truncation notice
        assert len(pack) < 20

    def test_one_oversized_document_is_still_included(self):
        """Returning nothing would be worse than returning one long document."""
        pack = build_evidence([_hit(_doc("big", body="x" * 50_000))], max_chars=100)
        assert len(pack) == 1

    def test_char_ceiling_can_bind_before_document_ceiling(self):
        docs = [_hit(_doc(f"d{i}", body="y" * 400)) for i in range(10)]
        pack = build_evidence(docs, max_documents=10, max_chars=900)
        assert len(pack) < 10


class TestDiversity:
    def test_kinds_are_interleaved(self):
        """Top-k on one noisy kind must not crowd out the others."""
        hits = [
            *[_hit(_doc(f"p{i}", KIND_PRICE), score=10 - i) for i in range(5)],
            _hit(_doc("i1", KIND_INDICATOR), score=1.0),
            _hit(_doc("n1", KIND_NEWS), score=0.5),
        ]
        pack = build_evidence(hits, max_documents=3, diversify=True)
        assert set(pack.kinds) == {KIND_PRICE, KIND_INDICATOR, KIND_NEWS}

    def test_best_of_each_kind_comes_first(self):
        hits = [
            _hit(_doc("p1", KIND_PRICE), score=10.0),
            _hit(_doc("p2", KIND_PRICE), score=9.0),
            _hit(_doc("n1", KIND_NEWS), score=1.0),
        ]
        pack = build_evidence(hits, max_documents=3, diversify=True)
        ids = [i.document.doc_id for i in pack.items]
        assert ids.index("p1") < ids.index("p2")

    def test_diversify_off_preserves_retriever_order(self):
        hits = [
            *[_hit(_doc(f"p{i}", KIND_PRICE)) for i in range(3)],
            _hit(_doc("n1", KIND_NEWS)),
        ]
        pack = build_evidence(hits, max_documents=3, diversify=False)
        assert pack.kinds == [KIND_PRICE]

    def test_no_document_is_lost_when_everything_fits(self):
        hits = [
            *[_hit(_doc(f"p{i}", KIND_PRICE)) for i in range(3)],
            _hit(_doc("n1", KIND_NEWS)),
        ]
        pack = build_evidence(hits, max_documents=10, diversify=True)
        assert len(pack) == 4


class TestDeduplication:
    def test_same_document_twice_is_included_once(self):
        doc = _doc("dup")
        pack = build_evidence([_hit(doc), _hit(doc)], max_documents=5)
        assert len(pack) == 1


class TestRender:
    def test_metadata_line_carries_provenance(self):
        doc = _doc(
            "news:1",
            KIND_NEWS,
            body="NABIL announces dividend.",
            symbol="NABIL",
            business_date=date(2026, 1, 5),
            url="https://example.test/1",
            source="sharesansar",
        )
        rendered = build_evidence([_hit(doc)]).render()
        for token in ("NABIL", "2026-01-05", "https://example.test/1", "sharesansar", "news"):
            assert token in rendered

    def test_body_text_is_present(self):
        rendered = build_evidence([_hit(_doc("d1", body="the actual fact"))]).render()
        assert "the actual fact" in rendered

    def test_empty_pack_says_so_rather_than_rendering_blank(self):
        assert build_evidence([]).render() == "(no evidence available)"

    def test_source_list_is_one_line_per_document(self):
        pack = build_evidence([_hit(_doc("d1")), _hit(_doc("d2"))])
        assert len(pack.render_sources().splitlines()) == 2

    def test_undated_document_renders_a_placeholder_date(self):
        assert "—" in build_evidence([_hit(_doc("d1"))]).render_sources()


class TestPackProperties:
    def test_symbols_are_distinct_and_first_seen_ordered(self):
        hits = [
            _hit(_doc("d1", symbol="NABIL")),
            _hit(_doc("d2", symbol="ADBL")),
            _hit(_doc("d3", symbol="NABIL")),
        ]
        assert build_evidence(hits, diversify=False).symbols == ["NABIL", "ADBL"]

    def test_falsy_when_empty(self):
        assert not build_evidence([])
        assert build_evidence([_hit(_doc("d1"))])

    def test_query_is_carried_through(self):
        assert build_evidence([_hit(_doc("d1"))], query="why did NABIL move").query == (
            "why did NABIL move"
        )


class TestPlainDocumentInput:
    def test_accepts_documents_without_scores(self):
        """Callers with a plain document list shouldn't have to fake SearchHits."""
        pack = build_evidence([_doc("d1"), _doc("d2")])
        assert len(pack) == 2
        assert pack.items[0].score == 0.0


@pytest.mark.parametrize("max_documents", [1, 2, 5, 8])
def test_length_never_exceeds_the_limit(max_documents: int):
    pack = build_evidence([_hit(_doc(f"d{i}")) for i in range(30)], max_documents=max_documents)
    assert len(pack) == max_documents


def test_empty_pack_has_no_markers():
    assert EvidencePack().markers == []
