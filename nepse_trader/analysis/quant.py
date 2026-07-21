"""Quantitative statistics over price/return series.

Pure, dependency-free functions (no numpy) so the math stays auditable and the
package stays light. Conventions:
  * `closes` are chronological closing prices (ascending date).
  * `returns` are simple period returns r_i = c_i/c_{i-1} - 1.
  * Annualisation uses `periods_per_year` (default 252 ~ NEPSE trading days).
Functions return None when the series is too short to be meaningful, so callers
can render "-" rather than crash.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

Number = float | None


def returns(closes: Sequence[float]) -> list[float]:
    """Simple period returns. len(returns) == len(closes) - 1."""
    out: list[float] = []
    for i in range(1, len(closes)):
        prev = closes[i - 1]
        if prev == 0:
            out.append(0.0)
        else:
            out.append(closes[i] / prev - 1.0)
    return out


def log_returns(closes: Sequence[float]) -> list[float]:
    out: list[float] = []
    for i in range(1, len(closes)):
        prev, cur = closes[i - 1], closes[i]
        if prev > 0 and cur > 0:
            out.append(math.log(cur / prev))
    return out


def mean(xs: Sequence[float]) -> Number:
    return sum(xs) / len(xs) if xs else None


def stdev(xs: Sequence[float], sample: bool = True) -> Number:
    """Standard deviation. Sample (n-1) by default; population when sample=False."""
    n = len(xs)
    if n < (2 if sample else 1):
        return None
    m = sum(xs) / n
    denom = (n - 1) if sample else n
    var = sum((x - m) ** 2 for x in xs) / denom
    return math.sqrt(var)


def annualized_return(closes: Sequence[float], periods_per_year: int = 252) -> Number:
    """Geometric annualised return from first to last close (CAGR-equivalent)."""
    if len(closes) < 2 or closes[0] <= 0 or closes[-1] <= 0:
        return None
    periods = len(closes) - 1
    growth = closes[-1] / closes[0]
    return (growth ** (periods_per_year / periods) - 1.0) * 100.0


def annualized_volatility(rets: Sequence[float], periods_per_year: int = 252) -> Number:
    sd = stdev(rets)
    if sd is None:
        return None
    return sd * math.sqrt(periods_per_year) * 100.0


def sharpe(rets: Sequence[float], risk_free: float = 0.0, periods_per_year: int = 252) -> Number:
    """Annualised Sharpe ratio. `risk_free` is an ANNUAL rate (e.g. 0.05)."""
    sd = stdev(rets)
    m = mean(rets)
    if sd is None or sd == 0 or m is None:
        return None
    excess_per_period = m - risk_free / periods_per_year
    return excess_per_period / sd * math.sqrt(periods_per_year)


def sortino(rets: Sequence[float], risk_free: float = 0.0, periods_per_year: int = 252) -> Number:
    """Annualised Sortino ratio (downside-deviation denominator)."""
    m = mean(rets)
    if m is None:
        return None
    target = risk_free / periods_per_year
    downside = [min(r - target, 0.0) ** 2 for r in rets]
    if not downside:
        return None
    dd = math.sqrt(sum(downside) / len(downside))
    if dd == 0:
        return None
    return (m - target) / dd * math.sqrt(periods_per_year)


def max_drawdown(closes: Sequence[float]) -> Number:
    """Largest peak-to-trough decline of a price series, as a positive percent."""
    if not closes:
        return None
    peak = closes[0]
    mdd = 0.0
    for c in closes:
        if c > peak:
            peak = c
        if peak > 0:
            dd = (peak - c) / peak * 100.0
            mdd = max(mdd, dd)
    return mdd


def _standardized_moment(xs: Sequence[float], power: int) -> Number:
    n = len(xs)
    if n < 3:
        return None
    m = sum(xs) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / n)  # population std for moments
    if sd == 0:
        return 0.0
    return sum(((x - m) / sd) ** power for x in xs) / n


def skewness(rets: Sequence[float]) -> Number:
    return _standardized_moment(rets, 3)


def kurtosis(rets: Sequence[float], excess: bool = True) -> Number:
    """Kurtosis of returns; excess (subtract 3) by default."""
    k = _standardized_moment(rets, 4)
    if k is None:
        return None
    return k - 3.0 if excess else k


def quantile(xs: Sequence[float], q: float) -> Number:
    """Linear-interpolation quantile (q in [0,1])."""
    if not xs:
        return None
    s = sorted(xs)
    if len(s) == 1:
        return s[0]
    pos = q * (len(s) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return s[lo]
    frac = pos - lo
    return s[lo] * (1 - frac) + s[hi] * frac


def value_at_risk(rets: Sequence[float], level: float = 0.95) -> Number:
    """Historical VaR as a POSITIVE loss fraction (percent) at `level` confidence.

    VaR_95 = -(5th percentile of returns), reported as a positive % loss.
    """
    if len(rets) < 2:
        return None
    q = quantile(rets, 1.0 - level)
    if q is None:
        return None
    return max(-q, 0.0) * 100.0


def covariance(a: Sequence[float], b: Sequence[float]) -> Number:
    n = min(len(a), len(b))
    if n < 2:
        return None
    a, b = a[:n], b[:n]
    ma, mb = sum(a) / n, sum(b) / n
    return sum((a[i] - ma) * (b[i] - mb) for i in range(n)) / (n - 1)


def correlation(a: Sequence[float], b: Sequence[float]) -> Number:
    cov = covariance(a, b)
    sa, sb = stdev(a), stdev(b)
    if cov is None or not sa or not sb:
        return None
    return cov / (sa * sb)


def beta(asset_returns: Sequence[float], market_returns: Sequence[float]) -> Number:
    """Beta of an asset vs the market = cov(asset, market) / var(market)."""
    n = min(len(asset_returns), len(market_returns))
    if n < 2:
        return None
    a, m = asset_returns[:n], market_returns[:n]
    var_m = stdev(m)
    if var_m is None or var_m == 0:
        return None
    cov = covariance(a, m)
    if cov is None:
        return None
    return cov / (var_m**2)


@dataclass
class SummaryStats:
    n: int
    last_close: float | None = None
    total_return_pct: Number = None
    annualized_return_pct: Number = None
    annualized_vol_pct: Number = None
    sharpe: Number = None
    sortino: Number = None
    max_drawdown_pct: Number = None
    skewness: Number = None
    kurtosis: Number = None
    var_95_pct: Number = None
    extras: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict:
        d = {
            "n": self.n,
            "last_close": self.last_close,
            "total_return_pct": self.total_return_pct,
            "annualized_return_pct": self.annualized_return_pct,
            "annualized_vol_pct": self.annualized_vol_pct,
            "sharpe": self.sharpe,
            "sortino": self.sortino,
            "max_drawdown_pct": self.max_drawdown_pct,
            "skewness": self.skewness,
            "kurtosis": self.kurtosis,
            "var_95_pct": self.var_95_pct,
        }
        d.update(self.extras)
        return d


def summary_stats(
    closes: Sequence[float],
    periods_per_year: int = 252,
    risk_free: float = 0.0,
) -> SummaryStats:
    """Full quantitative summary of a close-price series."""
    closes = [c for c in closes if c is not None]
    if len(closes) < 2:
        return SummaryStats(n=len(closes), last_close=closes[-1] if closes else None)
    rets = returns(closes)
    total = (closes[-1] / closes[0] - 1.0) * 100.0 if closes[0] else None
    return SummaryStats(
        n=len(closes),
        last_close=closes[-1],
        total_return_pct=total,
        annualized_return_pct=annualized_return(closes, periods_per_year),
        annualized_vol_pct=annualized_volatility(rets, periods_per_year),
        sharpe=sharpe(rets, risk_free, periods_per_year),
        sortino=sortino(rets, risk_free, periods_per_year),
        max_drawdown_pct=max_drawdown(closes),
        skewness=skewness(rets),
        kurtosis=kurtosis(rets),
        var_95_pct=value_at_risk(rets, 0.95),
    )
