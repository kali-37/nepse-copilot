"""The searchable document index: SQLite FTS5, with a LIKE fallback.

``DocumentIndex`` wraps the ``documents`` table and its FTS5 shadow. Two search
paths exist and both return the same :class:`SearchHit` shape:

* **FTS5** — bm25-ranked, stemmed, phrase- and prefix-capable. The normal path.
* **LIKE** — used only when the SQLite build has no FTS5. Ranks by how many of
  the query terms a document matches, tie-broken by recency. Cruder, but it means
  RAG never hard-fails on an unusual Python build.

Everything here is local and offline: no network, no embeddings, no extra deps.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime

from nepse_trader.rag.corpus import Document
from nepse_trader.storage.migrations import has_fts5

log = logging.getLogger("nepse_trader.rag.index")

# FTS5 treats these as syntax; strip them from user input so a stray quote or
# hyphen can't turn a search into a syntax error.
_FTS_SPECIAL = re.compile(r'["\'()*:^\-{}\[\]~]')
_WORD = re.compile(r"[0-9A-Za-z_ऀ-ॿ]+")


@dataclass
class SearchHit:
    """One retrieved document plus why it matched."""

    document: Document
    score: float
    matched_terms: list[str]

    @property
    def citation(self) -> str:
        return self.document.doc_id


def _tokens(query: str) -> list[str]:
    """Extract searchable words (Latin + Devanagari) from a raw query."""
    return [t for t in _WORD.findall(query or "") if len(t) > 1 or t.isdigit()]


def to_match_query(query: str) -> str:
    """Turn free text into a safe FTS5 MATCH expression.

    Terms are OR-ed with a prefix wildcard on each, so "NABIL momentum" also
    matches "momentums". Returns an empty string when nothing is searchable.
    """
    cleaned = _FTS_SPECIAL.sub(" ", query or "")
    terms = _tokens(cleaned)
    if not terms:
        return ""
    return " OR ".join(f'"{t}"*' for t in terms)


class DocumentIndex:
    """Read/write access to the document corpus and its search index."""

    def __init__(self, conn: sqlite3.Connection, *, use_fts: bool | None = None) -> None:
        self._conn = conn
        self._conn.row_factory = sqlite3.Row
        available = has_fts5(conn) and self._fts_table_exists()
        # `use_fts=False` forces the LIKE path on a build that has FTS5 — how the
        # fallback gets tested on ordinary machines. It can never force FTS5 on.
        self._fts = available if use_fts is None else (available and use_fts)

    def _fts_table_exists(self) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='documents_fts'"
        ).fetchone()
        return row is not None

    @property
    def uses_fts(self) -> bool:
        """True when bm25 ranking is available; False means the LIKE fallback."""
        return self._fts

    # ------------------------------------------------------------------ write
    def upsert(self, documents: list[Document]) -> int:
        """Insert or replace documents by ``doc_id``. Returns the count written.

        Uses DELETE-then-INSERT rather than INSERT..ON CONFLICT so the FTS5
        delete/insert triggers both fire and the shadow index stays consistent.
        """
        docs = [d for d in documents if d is not None]
        if not docs:
            return 0
        rows = [d.as_row() for d in docs]
        ids = [(d.doc_id,) for d in docs]
        try:
            self._conn.executemany("DELETE FROM documents WHERE doc_id = ?", ids)
            self._conn.executemany(
                """INSERT INTO documents
                   (doc_id, kind, symbol, business_date, title, body, url, source, fetched_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                rows,
            )
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        return len(rows)

    def delete_kind(self, kind: str) -> int:
        """Remove every document of one kind (used when rebuilding a slice)."""
        cur = self._conn.execute("DELETE FROM documents WHERE kind = ?", (kind,))
        self._conn.commit()
        return cur.rowcount

    def count(self, kind: str | None = None) -> int:
        if kind:
            row = self._conn.execute(
                "SELECT COUNT(*) AS n FROM documents WHERE kind = ?", (kind,)
            ).fetchone()
        else:
            row = self._conn.execute("SELECT COUNT(*) AS n FROM documents").fetchone()
        return int(row["n"])

    def kinds(self) -> dict[str, int]:
        """Document count per kind — what the corpus actually holds."""
        return {
            r["kind"]: r["n"]
            for r in self._conn.execute(
                "SELECT kind, COUNT(*) AS n FROM documents GROUP BY kind ORDER BY kind"
            )
        }

    def get(self, doc_id: str) -> Document | None:
        row = self._conn.execute(
            "SELECT * FROM documents WHERE doc_id = ?", (doc_id,)
        ).fetchone()
        return _row_to_document(row) if row else None

    # ----------------------------------------------------------------- search
    def search(
        self,
        query: str,
        *,
        limit: int = 8,
        symbols: list[str] | None = None,
        kinds: list[str] | None = None,
        since: date | None = None,
    ) -> list[SearchHit]:
        """Best-matching documents for *query*, most relevant first.

        ``symbols``/``kinds``/``since`` narrow the candidate set before ranking.
        An empty or unsearchable query falls back to "most recent matching the
        filters", which is the right answer for "just show me today".
        """
        if self._fts:
            hits = self._search_fts(query, limit=limit, symbols=symbols, kinds=kinds, since=since)
            if hits or to_match_query(query):
                return hits
            # Empty query with FTS available: fall through to the recency listing.
        return self._search_like(query, limit=limit, symbols=symbols, kinds=kinds, since=since)

    def _filters(
        self,
        symbols: list[str] | None,
        kinds: list[str] | None,
        since: date | None,
        column_prefix: str = "d.",
    ) -> tuple[str, list]:
        clauses: list[str] = []
        params: list = []
        if symbols:
            marks = ",".join("?" for _ in symbols)
            clauses.append(f"{column_prefix}symbol IN ({marks})")
            params.extend(s.strip().upper() for s in symbols)
        if kinds:
            marks = ",".join("?" for _ in kinds)
            clauses.append(f"{column_prefix}kind IN ({marks})")
            params.extend(kinds)
        if since:
            clauses.append(
                f"({column_prefix}business_date IS NULL OR {column_prefix}business_date >= ?)"
            )
            params.append(since.isoformat())
        return (" AND ".join(clauses), params)

    def _search_fts(
        self,
        query: str,
        *,
        limit: int,
        symbols: list[str] | None,
        kinds: list[str] | None,
        since: date | None,
    ) -> list[SearchHit]:
        match = to_match_query(query)
        if not match:
            return []
        where, params = self._filters(symbols, kinds, since)
        sql = (
            "SELECT d.*, bm25(documents_fts, 4.0, 1.0, 8.0, 2.0) AS rank "
            "FROM documents_fts JOIN documents d ON d.rowid = documents_fts.rowid "
            "WHERE documents_fts MATCH ?"
        )
        args: list = [match]
        if where:
            sql += f" AND {where}"
            args.extend(params)
        # bm25() returns a NEGATIVE score in SQLite; lower is a better match.
        sql += " ORDER BY rank LIMIT ?"
        args.append(limit)

        try:
            rows = self._conn.execute(sql, args).fetchall()
        except sqlite3.OperationalError as exc:
            log.warning("FTS5 search failed (%s); using LIKE fallback", exc)
            return self._search_like(query, limit=limit, symbols=symbols, kinds=kinds, since=since)

        terms = _tokens(query)
        return [
            SearchHit(
                document=_row_to_document(r),
                score=-float(r["rank"]),  # flip so bigger == better, like LIKE path
                matched_terms=_matched(r, terms),
            )
            for r in rows
        ]

    def _search_like(
        self,
        query: str,
        *,
        limit: int,
        symbols: list[str] | None,
        kinds: list[str] | None,
        since: date | None,
    ) -> list[SearchHit]:
        """Term-overlap ranking. Correct, just less clever than bm25."""
        where, params = self._filters(symbols, kinds, since)
        sql = "SELECT d.* FROM documents d"
        args: list = []
        terms = _tokens(query)
        if terms:
            term_clause = " OR ".join(
                "(LOWER(d.title) LIKE ? OR LOWER(d.body) LIKE ?)" for _ in terms
            )
            clauses = [f"({term_clause})"]
            for t in terms:
                like = f"%{t.lower()}%"
                args.extend([like, like])
            if where:
                clauses.append(where)
                args.extend(params)
            sql += " WHERE " + " AND ".join(clauses)
        elif where:
            sql += f" WHERE {where}"
            args.extend(params)

        # `NULLS LAST` needs SQLite 3.30+; this form works on every build.
        sql += " ORDER BY d.business_date IS NULL, d.business_date DESC LIMIT ?"
        args.append(max(limit * 4, limit))
        rows = self._conn.execute(sql, args).fetchall()

        hits: list[SearchHit] = []
        for r in rows:
            matched = _matched(r, terms)
            # Title matches count double — a title hit is a stronger signal.
            title = (r["title"] or "").lower()
            score = float(len(matched)) + sum(0.5 for t in matched if t.lower() in title)
            hits.append(
                SearchHit(document=_row_to_document(r), score=score, matched_terms=matched)
            )
        # Best score first; newest first within a score. Rows already arrive
        # newest-first, and Python's sort is stable, so one key is enough.
        hits.sort(key=lambda h: -h.score)
        return hits[:limit]

    def recent(
        self,
        *,
        limit: int = 8,
        symbols: list[str] | None = None,
        kinds: list[str] | None = None,
    ) -> list[Document]:
        """Newest documents matching the filters, ignoring relevance."""
        where, params = self._filters(symbols, kinds, None)
        sql = "SELECT d.* FROM documents d"
        if where:
            sql += f" WHERE {where}"
        sql += " ORDER BY d.business_date IS NULL, d.business_date DESC, d.doc_id LIMIT ?"
        rows = self._conn.execute(sql, [*params, limit]).fetchall()
        return [_row_to_document(r) for r in rows]


def _matched(row: sqlite3.Row, terms: list[str]) -> list[str]:
    haystack = f"{row['title']} {row['body']}".lower()
    return [t for t in terms if t.lower() in haystack]


def _row_to_document(row: sqlite3.Row) -> Document:
    return Document(
        doc_id=row["doc_id"],
        kind=row["kind"],
        title=row["title"],
        body=row["body"],
        symbol=row["symbol"],
        business_date=date.fromisoformat(row["business_date"]) if row["business_date"] else None,
        url=row["url"],
        source=row["source"],
        fetched_at=datetime.fromisoformat(row["fetched_at"]) if row["fetched_at"] else None,
    )
