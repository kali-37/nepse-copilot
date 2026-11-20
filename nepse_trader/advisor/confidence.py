"""Confidence values with an explicit evidence basis and conservative ceilings.

Only arithmetic facts can reach 1.0. Market forecasts are capped at 0.90;
no score makes a price outcome guaranteed. Resolved prediction history uses a
Wilson lower bound with a small-sample prior, while decision-board technical
scores explicitly identify themselves as evidence strength rather than
calibrated win probabilities. Every number carries the basis and sample size
needed to judge it. A compound plan takes its weakest confidence leg.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

# A market can gap. No forecast about a price gets to be certain, so every
# market-dependent confidence is clamped here even if the arithmetic says more.
MARKET_CEILING = 0.90

# Reserved for computed facts only — see `certain`.
CERTAINTY = 1.0

# The prior a symbol with no track record is pulled toward: a coin flip, minus a
# little, because costs mean a coin-flip trade loses money on average in Nepal.
DEFAULT_PRIOR = 0.45

# (floor, band, label) descending. `band_for` walks this in order.
BANDS: tuple[tuple[float, str, str], ...] = (
    (1.00, "CERTAIN", "arithmetic, not a forecast"),
    (0.95, "NEAR_CERTAIN", "still money in the bank"),
    (0.80, "STRONG", "strongly favoured"),
    (0.60, "LIKELY", "more likely than not"),
    (0.40, "COIN_FLIP", "a coin flip — size it small"),
    (0.20, "UNLIKELY", "unlikely — do not size up"),
    (0.00, "REMOTE", "remote"),
)


class ConfidenceError(ValueError):
    """A confidence was constructed outside 0–1, or 1.0 was claimed for a forecast."""


def band_for(value: float) -> tuple[str, str]:
    """The (band, label) pair for *value*.

    Exact-1.0 is the only value that reads CERTAIN, which is why the comparison
    is ``>=`` against a descending table rather than a bucket width.
    """
    for floor, band, label in BANDS:
        if value >= floor:
            return band, label
    return "REMOTE", "remote"


@dataclass(frozen=True)
class Confidence:
    """A confidence value in 0–1, its band, and the evidence behind it.

    Frozen because a confidence should never be edited after the fact — a caller
    that wants a different number must state a different basis for it.
    """

    value: float
    basis: str
    sample_size: int = 0
    band: str = field(init=False)
    label: str = field(init=False)
    _arithmetic: bool = field(default=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        rounded = float(
            Decimal(str(self.value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        )
        if not (0.0 <= rounded <= 1.0):
            raise ConfidenceError(f"confidence must be in 0–1, got {self.value!r}")
        if rounded == CERTAINTY and not self._arithmetic:
            raise ConfidenceError("only certain() may construct confidence 1.0")
        text = (self.basis or "").strip()
        if not text:
            raise ConfidenceError("confidence basis cannot be empty")
        if self.sample_size < 0:
            raise ConfidenceError("sample_size cannot be negative")
        band, label = band_for(rounded)
        object.__setattr__(self, "value", rounded)
        object.__setattr__(self, "basis", text)
        object.__setattr__(self, "band", band)
        object.__setattr__(self, "label", label)

    @property
    def is_certain(self) -> bool:
        return self.value >= CERTAINTY

    @property
    def pct(self) -> str:
        """For display: two significant places, so 0.955 does not read as 96%."""
        return f"{self.value * 100:.1f}%"

    def describe(self) -> str:
        """One line a beginner can act on."""
        return f"{self.value:.2f} ({self.label})"

    def as_dict(self) -> dict:
        return {
            "value": self.value,
            "band": self.band,
            "label": self.label,
            "basis": self.basis,
            "sample_size": self.sample_size,
        }

    def __str__(self) -> str:  # pragma: no cover - convenience only
        return self.describe()


def certain(basis: str) -> Confidence:
    """A confidence of exactly 1.0. **The only path to it.**

    Use this for arithmetic, never for a forecast: "the DP charge on this trade
    is NPR 25", "settlement is 2026-08-27", "the breakeven price is 512.40".
    *basis* is required, not optional, because a bare 1.0 with no stated reason
    is the single most misleading value this module can emit.
    """
    text = (basis or "").strip()
    if not text:
        raise ConfidenceError("certain() requires a basis — a bare 1.0 is not auditable")
    return Confidence(CERTAINTY, text, _arithmetic=True)


def market(
    value: float,
    basis: str = "market forecast; no measured basis supplied",
    *,
    sample_size: int = 0,
) -> Confidence:
    """A market-dependent confidence, clamped to :data:`MARKET_CEILING`.

    Every forecast in this codebase should be built through here rather than by
    calling :class:`Confidence` directly, so the ceiling cannot be bypassed by
    accident.
    """
    return Confidence(
        min(max(value, 0.0), MARKET_CEILING),
        basis or "market forecast; no measured basis supplied",
        sample_size=sample_size,
    )


def wilson_lower_bound(hits: int, n: int, z: float = 1.96) -> float:
    """Lower bound of the Wilson score interval for *hits* out of *n*.

    Why not ``hits / n``: with 3 hits from 3 calls the naive rate is 1.0, which
    would claim certainty from a sample that supports nothing of the kind. The
    Wilson lower bound answers the question actually being asked — "what
    hit-rate can I defend given this much evidence" — and returns ~0.44 there.

    Returns 0.0 for an empty sample: no evidence is not weak evidence of
    success, it is no evidence.
    """
    if n <= 0:
        return 0.0
    hits = max(0, min(hits, n))
    phat = hits / n
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = phat + z2 / (2 * n)
    margin = z * (((phat * (1.0 - phat)) / n + z2 / (4 * n * n)) ** 0.5)
    lower = (centre - margin) / denom
    return max(0.0, min(1.0, lower))


def confidence_from_history(
    hits: int,
    n: int,
    *,
    prior: float = DEFAULT_PRIOR,
    prior_weight: float = 8.0,
    ceiling: float = MARKET_CEILING,
    basis: str = "",
) -> Confidence:
    """Confidence from a realised track record, shrunk toward *prior*.

    Two corrections are applied, in this order:

    1. **Shrinkage.** The raw rate is blended with *prior* using *prior_weight*
       pseudo-observations, so one lucky win out of one does not read as 100%.
       ``prior_weight=8`` means a symbol needs roughly eight real calls before
       its own record outweighs the house prior.
    2. **Wilson.** The shrunk rate is then floored by the Wilson bound on the
       *real* sample size, so a long record is trusted more than a short one
       even when both show the same percentage.

    The result is clamped to *ceiling* — a track record, however good, is still
    a forecast about a market.
    """
    if n <= 0:
        return market(
            min(max(prior, 0.0), ceiling),
            basis or "no track record; house prior",
            sample_size=0,
        )

    hits = max(0, min(hits, n))
    shrunk = (hits + prior * prior_weight) / (n + prior_weight)
    wilson = wilson_lower_bound(hits, n)

    # The Wilson bound only ever pulls *down*, toward what the sample supports —
    # it is a cap on trust, never a boost. But it is not allowed to drag below
    # the house prior on sample size alone: one win out of one is not evidence
    # of skill, and it is not evidence of incompetence either. Negative evidence
    # still bites, because `shrunk` itself falls below the prior once calls miss.
    value = min(shrunk, max(wilson, prior))
    value = min(max(value, 0.0), ceiling, MARKET_CEILING)

    detail = f"{hits}/{n} resolved calls hit; shrunk toward prior {prior:.2f}"
    return market(value, basis or detail, sample_size=n)


def blend(*parts: Confidence) -> Confidence:
    """Combine legs by **weakest link** — the minimum, not the average.

    A plan card needs the entry to fill, the target to be reached, and enough
    volume to get out again. Those are conjunctive: the plan fails if any one
    fails. Averaging would let a 0.99-certain settlement date paper over a
    0.35 edge and produce a comfortable-looking 0.67 that describes nothing.

    The returned basis names the binding constraint, since that is the leg the
    user should go and look at.
    """
    usable = [p for p in parts if p is not None]
    if not usable:
        return Confidence(0.0, "nothing to blend")
    weakest = min(usable, key=lambda p: p.value)
    others = [p for p in usable if p is not weakest]
    if not others:
        return weakest
    basis = f"weakest link: {weakest.basis or 'unnamed leg'}"
    return Confidence(weakest.value, basis, sample_size=weakest.sample_size)


def penalise(base: Confidence, factor: float, reason: str) -> Confidence:
    """Scale a confidence down by *factor*, recording *reason*.

    Used for known haircuts — a longer horizon, thin liquidity, a disputed
    reconciliation. There is deliberately no ``boost``: nothing in this system
    should be able to talk a confidence upward, only down.
    """
    if not (0.0 <= factor <= 1.0):
        raise ConfidenceError(f"penalty factor must be in 0–1, got {factor!r}")
    value = min(max(base.value * factor, 0.0), MARKET_CEILING)
    basis = f"{base.basis}; {reason}" if base.basis else reason
    return Confidence(value, basis, sample_size=base.sample_size)


__all__ = [
    "BANDS",
    "CERTAINTY",
    "DEFAULT_PRIOR",
    "MARKET_CEILING",
    "Confidence",
    "ConfidenceError",
    "band_for",
    "blend",
    "certain",
    "confidence_from_history",
    "market",
    "penalise",
    "wilson_lower_bound",
]
