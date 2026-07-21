"""Technical indicators as pure functions over float series.

Dependency-free (no numpy/pandas) so the engine stays lightweight and the math
is auditable. Each function returns a list aligned to the input length, with
None where the indicator is undefined (warm-up period). This alignment makes it
safe to zip indicators with dated price bars.
"""

from __future__ import annotations

from collections.abc import Sequence

Number = float | None


def sma(values: Sequence[float], period: int) -> list[Number]:
    if period <= 0:
        raise ValueError("period must be positive")
    out: list[Number] = [None] * len(values)
    if len(values) < period:
        return out
    window_sum = sum(values[:period])
    out[period - 1] = window_sum / period
    for i in range(period, len(values)):
        window_sum += values[i] - values[i - period]
        out[i] = window_sum / period
    return out


def ema(values: Sequence[float], period: int) -> list[Number]:
    if period <= 0:
        raise ValueError("period must be positive")
    out: list[Number] = [None] * len(values)
    if len(values) < period:
        return out
    k = 2.0 / (period + 1)
    # Seed EMA with the SMA of the first `period` values.
    prev = sum(values[:period]) / period
    out[period - 1] = prev
    for i in range(period, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def rsi(values: Sequence[float], period: int = 14) -> list[Number]:
    """Wilder's RSI. Returns 0..100, None during warm-up."""
    out: list[Number] = [None] * len(values)
    if len(values) <= period:
        return out
    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        delta = values[i] - values[i - 1]
        gains += max(delta, 0.0)
        losses += max(-delta, 0.0)
    avg_gain = gains / period
    avg_loss = losses / period
    out[period] = _rsi_from_avgs(avg_gain, avg_loss)
    for i in range(period + 1, len(values)):
        delta = values[i] - values[i - 1]
        gain = max(delta, 0.0)
        loss = max(-delta, 0.0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        out[i] = _rsi_from_avgs(avg_gain, avg_loss)
    return out


def _rsi_from_avgs(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0
    if avg_gain == 0:
        return 0.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def macd(
    values: Sequence[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[list[Number], list[Number], list[Number]]:
    """Returns (macd_line, signal_line, histogram)."""
    fast_ema = ema(values, fast)
    slow_ema = ema(values, slow)
    macd_line: list[Number] = [
        (f - s) if (f is not None and s is not None) else None
        for f, s in zip(fast_ema, slow_ema, strict=True)
    ]
    # Signal line is an EMA over the defined portion of the MACD line.
    defined = [(i, v) for i, v in enumerate(macd_line) if v is not None]
    signal_line: list[Number] = [None] * len(values)
    hist: list[Number] = [None] * len(values)
    if len(defined) >= signal:
        sub_vals = [v for _, v in defined]
        sub_signal = ema(sub_vals, signal)
        for (idx, _), sig in zip(defined, sub_signal, strict=True):
            signal_line[idx] = sig
        for i in range(len(values)):
            if macd_line[i] is not None and signal_line[i] is not None:
                hist[i] = macd_line[i] - signal_line[i]
    return macd_line, signal_line, hist


def bollinger_bands(
    values: Sequence[float], period: int = 20, num_std: float = 2.0
) -> tuple[list[Number], list[Number], list[Number]]:
    """Returns (lower, middle, upper)."""
    middle = sma(values, period)
    lower: list[Number] = [None] * len(values)
    upper: list[Number] = [None] * len(values)
    for i in range(period - 1, len(values)):
        window = values[i - period + 1 : i + 1]
        mean = middle[i]
        if mean is None:
            continue
        variance = sum((x - mean) ** 2 for x in window) / period
        std = variance**0.5
        lower[i] = mean - num_std * std
        upper[i] = mean + num_std * std
    return lower, middle, upper


def atr(
    highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int = 14
) -> list[Number]:
    """Average True Range (Wilder). Requires aligned high/low/close series."""
    n = len(closes)
    out: list[Number] = [None] * n
    if n <= period:
        return out
    trs: list[float] = [highs[0] - lows[0]]
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    prev = sum(trs[1 : period + 1]) / period
    out[period] = prev
    for i in range(period + 1, n):
        prev = (prev * (period - 1) + trs[i]) / period
        out[i] = prev
    return out


def latest(series: Sequence[Number]) -> Number:
    """Return the last non-None value, or None."""
    for v in reversed(series):
        if v is not None:
            return v
    return None
