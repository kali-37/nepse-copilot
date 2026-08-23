"""Retrieval-augmented generation over the local NEPSE database and the live web.

Five pieces, kept separate so each is independently testable offline:

* :mod:`nepse_trader.rag.corpus` — turns DB rows into :class:`Document` objects.
* :mod:`nepse_trader.rag.index` — SQLite FTS5 index (with a LIKE fallback).
* :mod:`nepse_trader.rag.build` — walks the DB and populates the index.
* :mod:`nepse_trader.rag.retrievers` — local / web / hybrid retrieval.
* :mod:`nepse_trader.rag.evidence` — packs retrieved hits into a size-bounded
  evidence block with stable citation ids, ready to drop into a prompt.

The local half never touches the network. The web half only runs in online mode.
"""

from nepse_trader.rag.build import IndexReport, build_corpus, index_documents
from nepse_trader.rag.corpus import Document
from nepse_trader.rag.evidence import EvidenceItem, EvidencePack, build_evidence
from nepse_trader.rag.index import DocumentIndex, SearchHit
from nepse_trader.rag.retrievers import (
    HybridRetriever,
    LocalRetriever,
    WebRetriever,
    build_retriever,
)

__all__ = [
    "Document",
    "DocumentIndex",
    "SearchHit",
    "EvidenceItem",
    "EvidencePack",
    "build_evidence",
    "IndexReport",
    "build_corpus",
    "index_documents",
    "LocalRetriever",
    "WebRetriever",
    "HybridRetriever",
    "build_retriever",
]
