"""Pydantic contracts for LLM output.

Free models produce loose text. Everything an LLM returns is parsed into one of
these shapes before any other module sees it, so a malformed or hallucinated
response is **rejected** at this boundary rather than propagating into a report.

What is deliberately absent matters as much as what's here: **no price, stop,
target, size or date field appears in any of these models.** Those numbers come
from the deterministic engine and AI mode may not touch them. What an LLM
contributes is stance, conviction, narrative, catalysts, risks and citations —
commentary layered on top of arithmetic that already happened.

Prose is truncated rather than rejected when it's merely long, and lists are
capped, so a rambling model costs a shorter card and not a failed run.
"""

from __future__ import annotations

import json
import logging
import re
from typing import TypeVar

from pydantic import BaseModel, Field, field_validator

log = logging.getLogger("nepse_trader.ai.schemas")

# What a note may recommend. "reduce"/"avoid" are separate on purpose: trimming a
# holding and refusing a new entry are different actions.
STANCES = ("accumulate", "hold", "reduce", "avoid")

# Free models reach for trading vocabulary rather than ours. Map the obvious
# synonyms instead of failing the whole note over a word.
_STANCE_SYNONYMS = {
    "buy": "accumulate",
    "strong buy": "accumulate",
    "add": "accumulate",
    "accumulating": "accumulate",
    "neutral": "hold",
    "wait": "hold",
    "watch": "hold",
    "sell": "reduce",
    "trim": "reduce",
    "exit": "reduce",
    "strong sell": "reduce",
    "avoid": "avoid",
    "stay away": "avoid",
    "no trade": "avoid",
}

_MAX_PROSE = 1_200
_MAX_ITEMS = 6
_MAX_ITEM_CHARS = 240
_MARKER = re.compile(r"^\[?E?(\d+)\]?$", re.IGNORECASE)


def _clean(text: str, limit: int) -> str:
    flat = " ".join(str(text or "").split())
    return flat[:limit].rstrip()


def _clean_list(values: object, *, limit: int = _MAX_ITEMS) -> list[str]:
    """Normalise a bullet list: a string splits on newlines, a list is cleaned."""
    if values is None:
        return []
    if isinstance(values, str):
        parts = [p.lstrip("-•* ") for p in values.splitlines()]
    elif isinstance(values, (list, tuple)):
        parts = [str(v) for v in values]
    else:
        return []
    out = [_clean(p, _MAX_ITEM_CHARS) for p in parts]
    return [p for p in out if p][:limit]


def normalise_citations(values: object) -> list[str]:
    """Coerce whatever the model wrote into ``["[E1]", "[E3]"]`` form.

    Models write ``E1``, ``[e1]``, ``1`` and ``[E1][E2]`` interchangeably. The
    marker only means something if it matches an evidence item, so anything
    unrecognisable is dropped rather than guessed at.
    """
    if isinstance(values, str):
        raw = re.findall(r"\[?E?\d+\]?", values, re.IGNORECASE)
    elif isinstance(values, (list, tuple)):
        raw = [str(v) for v in values]
    else:
        return []

    out: list[str] = []
    for item in raw:
        match = _MARKER.match(item.strip())
        if not match:
            continue
        marker = f"[E{int(match.group(1))}]"
        if marker not in out:
            out.append(marker)
    return out[:_MAX_ITEMS]


class _Base(BaseModel):
    """Shared cleaning for every LLM-authored model."""

    citations: list[str] = Field(default_factory=list)

    @field_validator("citations", mode="before")
    @classmethod
    def _fix_citations(cls, v: object) -> list[str]:
        return normalise_citations(v)


class SymbolNote(_Base):
    """One symbol's narrative layer, sitting on top of a deterministic plan."""

    symbol: str
    stance: str
    conviction: int = Field(ge=1, le=5)
    thesis: str
    catalysts: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)

    @field_validator("symbol", mode="before")
    @classmethod
    def _upper(cls, v: object) -> str:
        return str(v or "").strip().upper()

    @field_validator("stance", mode="before")
    @classmethod
    def _fix_stance(cls, v: object) -> str:
        raw = str(v or "").strip().lower()
        mapped = _STANCE_SYNONYMS.get(raw, raw)
        if mapped not in STANCES:
            raise ValueError(f"stance must be one of {', '.join(STANCES)}, got {v!r}")
        return mapped

    @field_validator("conviction", mode="before")
    @classmethod
    def _clamp_conviction(cls, v: object) -> object:
        """Accept "4/5" and "high"-free numerics; clamp rather than reject 0 or 9."""
        if isinstance(v, str):
            match = re.search(r"\d+", v)
            if not match:
                return v
            v = int(match.group(0))
        if isinstance(v, (int, float)):
            return max(1, min(5, int(v)))
        return v

    @field_validator("thesis", mode="before")
    @classmethod
    def _trim_thesis(cls, v: object) -> str:
        return _clean(str(v or ""), _MAX_PROSE)

    @field_validator("catalysts", "risks", mode="before")
    @classmethod
    def _trim_lists(cls, v: object) -> list[str]:
        return _clean_list(v)


class WeeklyThesis(_Base):
    """The expensive weekly pass: market posture plus where to look.

    Cached by ISO week, which is what makes daily AI runs cheap — the day only
    pays for the delta against this.
    """

    week: str = ""
    regime: str = ""
    summary: str
    focus_symbols: list[str] = Field(default_factory=list)
    avoid_symbols: list[str] = Field(default_factory=list)
    key_risks: list[str] = Field(default_factory=list)

    @field_validator("summary", "regime", mode="before")
    @classmethod
    def _trim_prose(cls, v: object) -> str:
        return _clean(str(v or ""), _MAX_PROSE)

    @field_validator("focus_symbols", "avoid_symbols", mode="before")
    @classmethod
    def _upper_symbols(cls, v: object) -> list[str]:
        return [s.upper() for s in _clean_list(v, limit=12)]

    @field_validator("key_risks", mode="before")
    @classmethod
    def _trim_risks(cls, v: object) -> list[str]:
        return _clean_list(v)


class Critique(_Base):
    """A devil's-advocate pass over the deterministic plan.

    It cannot change a number — it can only say what the numbers might be missing,
    which is then printed beside the plan for the human to weigh.
    """

    verdict: str
    concerns: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)

    @field_validator("verdict", mode="before")
    @classmethod
    def _fix_verdict(cls, v: object) -> str:
        raw = str(v or "").strip().lower()
        if raw in ("agree", "agrees", "concur", "supported"):
            return "agree"
        if raw in ("disagree", "disagrees", "opposed", "reject"):
            return "disagree"
        if raw in ("mixed", "partial", "partially agree", "neutral", "unclear"):
            return "mixed"
        raise ValueError(f"verdict must be agree, disagree or mixed, got {v!r}")

    @field_validator("concerns", "missing_evidence", mode="before")
    @classmethod
    def _trim_lists(cls, v: object) -> list[str]:
        return _clean_list(v)


# ---------------------------------------------------------------------------
# Turning model text into one of the above
# ---------------------------------------------------------------------------

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)

T = TypeVar("T", bound=BaseModel)


def extract_json(text: str) -> dict | list | None:
    """Find the JSON payload in a model's reply, or None.

    Three shapes, tried in order: the whole reply is JSON; it's inside a fenced
    code block; or it's prose with an object embedded. Anything else returns None,
    which the caller treats as a failed pass — not as an empty result.
    """
    raw = (text or "").strip()
    if not raw:
        return None

    for candidate in _json_candidates(raw):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, (dict, list)):
            return parsed
    return None


def _json_candidates(raw: str) -> list[str]:
    candidates = [raw]
    fenced = _FENCE.search(raw)
    if fenced:
        candidates.append(fenced.group(1).strip())
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = raw.find(opener), raw.rfind(closer)
        if 0 <= start < end:
            candidates.append(raw[start : end + 1])
    return candidates


def parse_into(model: type[T], text: str, **defaults: object) -> T | None:
    """Parse *text* into *model*, or return None and log why.

    ``defaults`` fill fields the prompt didn't ask the model to repeat (the symbol,
    the ISO week) — values we already know and shouldn't trust a model to echo.
    Returning None rather than raising is the contract: a failed pass costs
    narrative, never numbers.
    """
    payload = extract_json(text)
    if payload is None:
        log.warning("%s: no JSON found in the response", model.__name__)
        return None
    if isinstance(payload, list):
        payload = next((p for p in payload if isinstance(p, dict)), None)
        if payload is None:
            log.warning("%s: JSON array held no object", model.__name__)
            return None

    merged = {**payload, **{k: v for k, v in defaults.items() if v is not None}}
    try:
        return model.model_validate(merged)
    except Exception as exc:  # noqa: BLE001 - pydantic raises several types
        log.warning("%s: rejected LLM output — %s", model.__name__, exc)
        return None
