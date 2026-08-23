"""Turning retrieved documents into a bounded, citable evidence block.

An :class:`EvidencePack` is what gets pasted into a prompt. It exists to enforce
three things the retriever itself doesn't care about:

**A hard character ceiling.** Free OpenRouter models have small context windows and
the token budget is finite, so evidence is truncated to a configured size rather
than "whatever came back".

**Stable citation ids.** Each included document gets a short marker (``[E1]``,
``[E2]``…). The LLM is told to cite them, which makes its claims checkable against
the source document instead of taken on faith.

**Diversity over depth.** A naive top-k on a price query returns ten price
documents for the same symbol. Packing round-robins across document kinds first,
so indicators, quality and news all survive the cut.

Nothing here needs an LLM — the same pack renders into the Normal-mode report as a
plain "what this is based on" section.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field

from nepse_trader.rag.corpus import Document
from nepse_trader.rag.index import SearchHit


@dataclass
class EvidenceItem:
    """One document admitted into the pack, with its citation marker."""

    marker: str
    document: Document
    score: float

    def render(self) -> str:
        head = f"{self.marker} {self.document.title}"
        meta = [f"kind={self.document.kind}"]
        if self.document.symbol:
            meta.append(f"symbol={self.document.symbol}")
        if self.document.business_date:
            meta.append(f"date={self.document.business_date.isoformat()}")
        if self.document.source:
            meta.append(f"source={self.document.source}")
        if self.document.url:
            meta.append(f"url={self.document.url}")
        return f"{head}\n({'; '.join(meta)})\n{self.document.body}"


@dataclass
class EvidencePack:
    """A size-bounded, ordered, citable set of documents."""

    items: list[EvidenceItem] = field(default_factory=list)
    query: str = ""
    truncated: bool = False
    considered: int = 0

    def __len__(self) -> int:
        return len(self.items)

    def __bool__(self) -> bool:
        return bool(self.items)

    @property
    def markers(self) -> list[str]:
        return [i.marker for i in self.items]

    @property
    def symbols(self) -> list[str]:
        """Distinct symbols appearing in the evidence, in first-seen order."""
        return list(
            OrderedDict.fromkeys(i.document.symbol for i in self.items if i.document.symbol)
        )

    @property
    def kinds(self) -> list[str]:
        return list(OrderedDict.fromkeys(i.document.kind for i in self.items))

    def citation_map(self) -> dict[str, str]:
        """``{"[E1]": "price:NABIL:2026-08-20", ...}`` — for auditing an answer."""
        return {i.marker: i.document.doc_id for i in self.items}

    def render(self) -> str:
        """The block to embed in a prompt."""
        if not self.items:
            return "(no evidence available)"
        body = "\n\n".join(i.render() for i in self.items)
        if self.truncated:
            body += (
                f"\n\n(evidence truncated: {len(self.items)} of {self.considered} "
                "retrieved documents shown)"
            )
        return body

    def render_sources(self) -> str:
        """A compact source list for the human-facing report."""
        lines = []
        for item in self.items:
            doc = item.document
            when = doc.business_date.isoformat() if doc.business_date else "—"
            line = f"- {item.marker} {doc.title} ({when})"
            if doc.url:
                line += f" — {doc.url}"
            lines.append(line)
        return "\n".join(lines)


def build_evidence(
    hits: list[SearchHit] | list[Document],
    *,
    query: str = "",
    max_documents: int = 8,
    max_chars: int = 12_000,
    diversify: bool = True,
) -> EvidencePack:
    """Pack hits into an :class:`EvidencePack` under both ceilings.

    ``max_documents`` and ``max_chars`` are both hard limits — whichever binds
    first stops the pack. When ``diversify`` is set, candidates are interleaved
    across document kinds so one noisy kind can't crowd out the rest; relative
    order within each kind is preserved, so the best hit of each kind lands first.
    """
    candidates = _as_scored(hits)
    considered = len(candidates)
    if diversify:
        candidates = _round_robin_by_kind(candidates)

    items: list[EvidenceItem] = []
    used = 0
    seen: set[str] = set()
    for doc, score in candidates:
        if len(items) >= max_documents:
            break
        if doc.doc_id in seen:
            continue
        marker = f"[E{len(items) + 1}]"
        candidate = EvidenceItem(marker=marker, document=doc, score=score)
        cost = len(candidate.render()) + 2  # +2 for the blank line between items
        if items and used + cost > max_chars:
            break  # keep at least one item even if it alone exceeds the ceiling
        items.append(candidate)
        seen.add(doc.doc_id)
        used += cost

    return EvidencePack(
        items=items,
        query=query,
        truncated=len(items) < considered,
        considered=considered,
    )


def _as_scored(hits: list[SearchHit] | list[Document]) -> list[tuple[Document, float]]:
    """Normalise either input shape to (document, score) pairs."""
    out: list[tuple[Document, float]] = []
    for h in hits:
        if isinstance(h, SearchHit):
            out.append((h.document, h.score))
        else:
            out.append((h, 0.0))
    return out


def _round_robin_by_kind(
    candidates: list[tuple[Document, float]],
) -> list[tuple[Document, float]]:
    """Interleave across kinds, preserving each kind's internal ranking."""
    buckets: OrderedDict[str, list[tuple[Document, float]]] = OrderedDict()
    for doc, score in candidates:
        buckets.setdefault(doc.kind, []).append((doc, score))

    ordered: list[tuple[Document, float]] = []
    while buckets:
        for kind in list(buckets):
            ordered.append(buckets[kind].pop(0))
            if not buckets[kind]:
                del buckets[kind]
    return ordered
