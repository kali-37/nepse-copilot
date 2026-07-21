"""Long-only technical trading strategies producing dated :class:`Signal`s.

Each strategy consumes a chronological (ascending by ``business_date``) list of
:class:`PriceBar` and returns one :class:`Signal` per *valid* bar. A bar is valid
when, after carrying the previous good close forward, we have a usable close to
feed the indicators. Strategies emit ``BUY``/``SELL`` only on a **state change**
(a crossover), and ``HOLD`` on every other valid day. This keeps signals sparse
and event-driven, which is what a backtester/ledger expects.

Parsing of indicators is delegated entirely to
:mod:`nepse_trader.analysis.indicators` (pure, list-aligned). Strategies never
touch the network.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from nepse_trader.analysis import indicators as ind
from nepse_trader.models import PriceBar, Signal, SignalAction


def _clamp01(x: float) -> float:
    """Clamp ``x`` into [0, 1] (Signal.strength is validated ``0 <= s <= 1``)."""
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def _clean_indicators(raw: dict[str, float | None]) -> dict[str, float]:
    """Drop None entries; Signal.indicators is ``dict[str, float]``."""
    return {k: float(v) for k, v in raw.items() if v is not None}


class Strategy(ABC):
    """Abstract base for all strategies.

    Subclasses implement :meth:`generate`. The base provides:
      * :meth:`_closes` — close series with previous-valid-close carried forward
        (and a parallel mask of which bars actually had a close), and
      * :meth:`_emit` — a small helper to build a :class:`Signal` for a bar.
    """

    name: str = "strategy"

    @abstractmethod
    def generate(self, bars: list[PriceBar]) -> list[Signal]:
        """Return signals for ``bars`` (chronological ascending)."""
        raise NotImplementedError

    def _closes(self, bars: list[PriceBar]) -> tuple[list[float], list[bool]]:
        """Return (closes, has_close).

        ``closes`` carries the last valid close forward over None-close days so
        indicator math stays continuous; ``has_close[i]`` is True only when the
        bar itself reported a close (i.e. we may emit a signal on day ``i``).
        Leading None closes (before any valid close) are filled with 0.0 but
        masked False.
        """
        closes: list[float] = []
        has_close: list[bool] = []
        prev: float | None = None
        for bar in bars:
            if bar.close is not None:
                prev = bar.close
                closes.append(bar.close)
                has_close.append(True)
            else:
                # The bar itself reported no close: carry the last valid close
                # forward for indicator continuity, but mask it so no signal is
                # emitted on this day.
                closes.append(prev if prev is not None else 0.0)
                has_close.append(False)
        return closes, has_close

    def _emit(
        self,
        bar: PriceBar,
        action: SignalAction,
        strength: float,
        reason: str,
        inds: dict[str, float | None],
    ) -> Signal:
        return Signal(
            symbol=bar.symbol,
            business_date=bar.business_date,
            action=action,
            strategy=self.name,
            strength=_clamp01(strength),
            reason=reason,
            price=bar.close,
            indicators=_clean_indicators(inds),
        )

    def latest_signal(self, bars: list[PriceBar]) -> Signal | None:
        """Convenience: the signal for the last day, or None if none produced."""
        signals = self.generate(bars)
        return signals[-1] if signals else None


class SmaCrossStrategy(Strategy):
    """Fast/slow simple-moving-average crossover."""

    name = "sma_cross"

    def __init__(self, fast: int = 20, slow: int = 50) -> None:
        if fast <= 0 or slow <= 0:
            raise ValueError("periods must be positive")
        if fast >= slow:
            raise ValueError("fast period must be smaller than slow period")
        self.fast = fast
        self.slow = slow

    def generate(self, bars: list[PriceBar]) -> list[Signal]:
        closes, has_close = self._closes(bars)
        fast = ind.sma(closes, self.fast)
        slow = ind.sma(closes, self.slow)
        out: list[Signal] = []
        # Track which side fast sits relative to slow. The first bar where fast
        # is above slow opens a long (BUY); the first bar it drops below closes
        # it (SELL). This treats the initial trend as a state change, matching
        # how a crossover system actually enters/exits.
        prev_sign: int | None = None
        for i, bar in enumerate(bars):
            f, s = fast[i], slow[i]
            if not has_close[i] or f is None or s is None or s == 0:
                continue
            diff = f - s
            sign = 1 if diff > 0 else (-1 if diff < 0 else 0)
            action = SignalAction.HOLD
            if sign == 1 and prev_sign != 1:
                action = SignalAction.BUY
            elif sign == -1 and prev_sign != -1:
                action = SignalAction.SELL
            strength = _clamp01(abs(f - s) / s)
            out.append(
                self._emit(
                    bar,
                    action,
                    strength,
                    f"sma{self.fast}={f:.2f} vs sma{self.slow}={s:.2f}",
                    {"sma_fast": f, "sma_slow": s},
                )
            )
            if sign != 0:
                prev_sign = sign
        return out


class RsiStrategy(Strategy):
    """RSI mean-reversion: buy crossing up out of oversold, sell crossing down."""

    name = "rsi"

    def __init__(self, period: int = 14, oversold: float = 30.0, overbought: float = 70.0) -> None:
        if period <= 0:
            raise ValueError("period must be positive")
        if not (0 <= oversold < overbought <= 100):
            raise ValueError("require 0 <= oversold < overbought <= 100")
        self.period = period
        self.oversold = oversold
        self.overbought = overbought

    def generate(self, bars: list[PriceBar]) -> list[Signal]:
        closes, has_close = self._closes(bars)
        rsi = ind.rsi(closes, self.period)
        out: list[Signal] = []
        prev_rsi: float | None = None
        for i, bar in enumerate(bars):
            r = rsi[i]
            if not has_close[i] or r is None:
                continue
            action = SignalAction.HOLD
            if prev_rsi is not None:
                if prev_rsi <= self.oversold < r:
                    action = SignalAction.BUY
                elif prev_rsi >= self.overbought > r:
                    action = SignalAction.SELL
            # Strength grows with distance from the neutral 50 line.
            strength = _clamp01(abs(r - 50.0) / 50.0)
            out.append(
                self._emit(
                    bar,
                    action,
                    strength,
                    f"rsi={r:.1f} (os={self.oversold}, ob={self.overbought})",
                    {"rsi": r},
                )
            )
            prev_rsi = r
        return out


class MacdStrategy(Strategy):
    """MACD line zero-line crossover.

    Goes long when the MACD line (fast EMA − slow EMA) turns positive and exits
    when it turns negative. The signal line and histogram are computed for
    reporting only — a pure signal-line crossover is degenerate on a
    constant-slope series (the histogram is identically zero there).
    """

    name = "macd"

    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9) -> None:
        if fast <= 0 or slow <= 0 or signal <= 0:
            raise ValueError("periods must be positive")
        if fast >= slow:
            raise ValueError("fast period must be smaller than slow period")
        self.fast = fast
        self.slow = slow
        self.signal = signal

    def generate(self, bars: list[PriceBar]) -> list[Signal]:
        closes, has_close = self._closes(bars)
        macd_line, signal_line, hist = ind.macd(closes, self.fast, self.slow, self.signal)
        out: list[Signal] = []
        # Zero-line cross of the MACD line: MACD > 0 means the fast EMA leads the
        # slow EMA (uptrend) -> open long; MACD < 0 (downtrend) -> exit. We wait
        # until the signal line is also defined so the histogram is reportable.
        # (A pure signal-line cross is degenerate on a constant-slope ramp, where
        # the histogram is identically zero.)
        prev_sign: int | None = None
        for i, bar in enumerate(bars):
            m, s, h = macd_line[i], signal_line[i], hist[i]
            if not has_close[i] or m is None or s is None or h is None:
                continue
            sign = 1 if m > 0 else (-1 if m < 0 else 0)
            action = SignalAction.HOLD
            if sign == 1 and prev_sign != 1:
                action = SignalAction.BUY
            elif sign == -1 and prev_sign != -1:
                action = SignalAction.SELL
            # Strength from the MACD line magnitude, normalised by price.
            denom = bar.close if (bar.close not in (None, 0)) else 1.0
            strength = _clamp01(abs(m) / abs(denom))
            out.append(
                self._emit(
                    bar,
                    action,
                    strength,
                    f"macd={m:.3f} signal={s:.3f} hist={h:.3f}",
                    {"macd": m, "signal": s, "hist": h},
                )
            )
            if sign != 0:
                prev_sign = sign
        return out


class BollingerStrategy(Strategy):
    """Bollinger-band reversion: buy below lower band, sell above upper band."""

    name = "bollinger"

    def __init__(self, period: int = 20, num_std: float = 2.0) -> None:
        if period <= 0:
            raise ValueError("period must be positive")
        if num_std <= 0:
            raise ValueError("num_std must be positive")
        self.period = period
        self.num_std = num_std

    def generate(self, bars: list[PriceBar]) -> list[Signal]:
        closes, has_close = self._closes(bars)
        lower, middle, upper = ind.bollinger_bands(closes, self.period, self.num_std)
        out: list[Signal] = []
        # Track which side of the bands the previous valid close sat on.
        prev_state: int | None = None  # -1 below lower, +1 above upper, 0 inside
        for i, bar in enumerate(bars):
            lo, mid, up = lower[i], middle[i], upper[i]
            if not has_close[i] or lo is None or mid is None or up is None:
                continue
            close = closes[i]
            if close < lo:
                state = -1
            elif close > up:
                state = 1
            else:
                state = 0
            action = SignalAction.HOLD
            if prev_state is not None:
                # Cross *below* lower band -> BUY; cross *above* upper -> SELL.
                if state == -1 and prev_state != -1:
                    action = SignalAction.BUY
                elif state == 1 and prev_state != 1:
                    action = SignalAction.SELL
            band_width = up - lo
            if band_width > 0:
                # Distance outside the nearer band, scaled by band width.
                if state == -1:
                    strength = (lo - close) / band_width
                elif state == 1:
                    strength = (close - up) / band_width
                else:
                    strength = 0.0
            else:
                strength = 0.0
            out.append(
                self._emit(
                    bar,
                    action,
                    _clamp01(strength),
                    f"close={close:.2f} lower={lo:.2f} upper={up:.2f}",
                    {"lower": lo, "middle": mid, "upper": up, "close": close},
                )
            )
            prev_state = state
        return out


class CompositeStrategy(Strategy):
    """Ensemble vote over sub-strategies, aligned by ``business_date``."""

    name = "composite"

    def __init__(
        self,
        strategies: list[Strategy],
        buy_threshold: float = 0.5,
        sell_threshold: float = 0.5,
    ) -> None:
        if not strategies:
            raise ValueError("composite requires at least one sub-strategy")
        self.strategies = list(strategies)
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold

    def generate(self, bars: list[PriceBar]) -> list[Signal]:
        if not bars:
            return []
        # Per-strategy: map business_date -> its Signal for that date.
        per_strategy: list[dict[date, Signal]] = []
        for strat in self.strategies:
            by_date = {sig.business_date: sig for sig in strat.generate(bars)}
            per_strategy.append(by_date)

        n = len(self.strategies)
        out: list[Signal] = []
        # Iterate dates in bar order; only emit where we have a usable close.
        seen: set[date] = set()
        closes, has_close = self._closes(bars)
        for i, bar in enumerate(bars):
            bd = bar.business_date
            if bd in seen:
                continue
            seen.add(bd)
            if not has_close[i]:
                continue
            buys: list[str] = []
            sells: list[str] = []
            for strat, by_date in zip(self.strategies, per_strategy, strict=True):
                sig = by_date.get(bd)
                if sig is None:
                    continue
                if sig.action is SignalAction.BUY:
                    buys.append(strat.name)
                elif sig.action is SignalAction.SELL:
                    sells.append(strat.name)
            net = (len(buys) - len(sells)) / n
            if net >= self.buy_threshold:
                action = SignalAction.BUY
            elif net <= -self.sell_threshold:
                action = SignalAction.SELL
            else:
                action = SignalAction.HOLD
            parts: list[str] = []
            if buys:
                parts.append(f"BUY:{','.join(buys)}")
            if sells:
                parts.append(f"SELL:{','.join(sells)}")
            reason = f"net={net:+.2f}" + ((" " + " ".join(parts)) if parts else "")
            out.append(
                self._emit(
                    bar,
                    action,
                    _clamp01(abs(net)),
                    reason,
                    {"net": net, "buy_votes": float(len(buys)), "sell_votes": float(len(sells))},
                )
            )
        return out


class SupertrendStrategy(Strategy):
    """Trend-following using Supertrend as a trailing stop/reversal signal."""

    name = "supertrend"

    def __init__(self, period: int = 10, multiplier: float = 3.0) -> None:
        if period <= 0:
            raise ValueError("period must be positive")
        self.period = period
        self.multiplier = multiplier

    def generate(self, bars: list[PriceBar]) -> list[Signal]:
        if not bars:
            return []
        highs = [b.high if b.high is not None else 0.0 for b in bars]
        lows = [b.low if b.low is not None else 0.0 for b in bars]
        closes, has_close = self._closes(bars)
        band, direction = ind.supertrend(highs, lows, closes, self.period, self.multiplier)
        out: list[Signal] = []
        prev_dir: int = 0
        for i, bar in enumerate(bars):
            if not has_close[i] or band[i] is None:
                continue
            d = direction[i]
            action = SignalAction.HOLD
            reason = f"band={band[i]:.2f}"
            strength = abs(closes[i] - band[i]) / band[i] if band[i] else 0.0
            if d == +1 and prev_dir == -1:
                action = SignalAction.BUY
                reason = f"uptrend flip band={band[i]:.2f}"
            elif d == -1 and prev_dir == +1:
                action = SignalAction.SELL
                reason = f"downtrend flip band={band[i]:.2f}"
            out.append(
                self._emit(bar, action, _clamp01(strength), reason, {"band": band[i], "direction": float(d)})
            )
            prev_dir = d
        return out


class IchimokuStrategy(Strategy):
    """Ichimoku Cloud: TK cross, price vs cloud, and Chikou confirmation."""

    name = "ichimoku"

    def __init__(
        self,
        tenkan_period: int = 9,
        kijun_period: int = 26,
        senkou_period: int = 52,
        displacement: int = 26,
    ) -> None:
        self.tenkan_period = tenkan_period
        self.kijun_period = kijun_period
        self.senkou_period = senkou_period
        self.displacement = displacement

    def generate(self, bars: list[PriceBar]) -> list[Signal]:
        if not bars:
            return []
        highs = [b.high if b.high is not None else 0.0 for b in bars]
        lows = [b.low if b.low is not None else 0.0 for b in bars]
        closes, has_close = self._closes(bars)

        tenkan = ind.tenkan_sen(highs, lows, self.tenkan_period)
        kijun = ind.kijun_sen(highs, lows, self.kijun_period)
        senkou_a_raw = ind.senkou_span_a(tenkan, kijun, self.displacement)
        senkou_b_raw = ind.senkou_span_b(highs, lows, self.senkou_period, self.displacement)

        out: list[Signal] = []
        prev_tk: int = 0  # -1 tenkan below kijun, +1 above, 0 equal/undefined
        for i, bar in enumerate(bars):
            if not has_close[i]:
                continue
            t, k = tenkan[i], kijun[i]
            sa, sb = senkou_a_raw[i], senkou_b_raw[i]
            if t is None or k is None:
                continue
            # TK cross
            tk_signal: int = 0
            if t > k:
                tk_signal = +1
            elif t < k:
                tk_signal = -1
            # Price relative to cloud
            close = closes[i]
            above_cloud = sa is not None and sb is not None and close > max(sa, sb)
            below_cloud = sa is not None and sb is not None and close < min(sa, sb)
            # Chikou (close 26 bar ago vs current close)
            chikou_confirm = False
            chikou_idx = i - self.displacement
            if chikou_idx >= 0:
                past_close = closes[chikou_idx]
                chikou_confirm = past_close < close

            action = SignalAction.HOLD
            reason_parts: list[str] = []
            strength = 0.0
            if tk_signal == +1 and prev_tk <= 0 and above_cloud:
                action = SignalAction.BUY
                strength = (t - k) / k if k else 0.1
                reason_parts.append("TK_bullish")
                if chikou_confirm:
                    reason_parts.append("Chikou_confirm")
            elif tk_signal == -1 and prev_tk >= 0 and below_cloud:
                action = SignalAction.SELL
                strength = (k - t) / k if k else 0.1
                reason_parts.append("TK_bearish")
                if chikou_confirm:
                    reason_parts.append("Chikou_confirm")
            out.append(
                self._emit(
                    bar,
                    action,
                    _clamp01(strength),
                    " ".join(reason_parts) if reason_parts else "no_signal",
                    {
                        "tenkan": t,
                        "kijun": k,
                        "senkou_a": sa if sa is not None else 0.0,
                        "senkou_b": sb if sb is not None else 0.0,
                    },
                )
            )
            prev_tk = tk_signal
        return out


class DonchianStrategy(Strategy):
    """Donchian channel breakout: buy above upper, sell below lower."""

    name = "donchian"

    def __init__(self, period: int = 20, confirmation_bars: int = 1) -> None:
        if period <= 0:
            raise ValueError("period must be positive")
        self.period = period
        self.confirmation_bars = confirmation_bars

    def generate(self, bars: list[PriceBar]) -> list[Signal]:
        if not bars:
            return []
        highs = [b.high if b.high is not None else 0.0 for b in bars]
        lows = [b.low if b.low is not None else 0.0 for b in bars]
        closes, has_close = self._closes(bars)
        upper, middle, lower = ind.donchian_channel(highs, lows, self.period)
        out: list[Signal] = []
        prev_state: int = 0  # -1 below lower, +1 above upper, 0 inside
        for i, bar in enumerate(bars):
            if not has_close[i] or upper[i] is None or lower[i] is None:
                continue
            close = closes[i]
            if close > upper[i]:
                state = +1
            elif close < lower[i]:
                state = -1
            else:
                state = 0
            action = SignalAction.HOLD
            strength = 0.0
            if state == +1 and prev_state != +1:
                action = SignalAction.BUY
                strength = (close - upper[i]) / upper[i]
            elif state == -1 and prev_state != -1:
                action = SignalAction.SELL
                strength = (lower[i] - close) / close
            out.append(
                self._emit(
                    bar,
                    action,
                    _clamp01(strength),
                    f"close={close:.2f} upper={upper[i]:.2f} lower={lower[i]:.2f}",
                    {"upper": upper[i], "middle": middle[i], "lower": lower[i], "close": close},
                )
            )
            prev_state = state
        return out


class MeanReversionStrategy(Strategy):
    """RSI mean reversion: buy oversold, sell overbought."""

    name = "mean_reversion"

    def __init__(self, rsi_period: int = 14, oversold: float = 30.0, overbought: float = 70.0) -> None:
        if rsi_period <= 0:
            raise ValueError("rsi_period must be positive")
        self.rsi_period = rsi_period
        self.oversold = oversold
        self.overbought = overbought

    def generate(self, bars: list[PriceBar]) -> list[Signal]:
        closes, has_close = self._closes(bars)
        rsi = ind.rsi(closes, self.rsi_period)
        out: list[Signal] = []
        prev_state: int = 0  # -1 oversold, +1 overbought, 0 neutral
        for i, bar in enumerate(bars):
            if not has_close[i] or rsi[i] is None:
                continue
            r = rsi[i]
            if r <= self.oversold:
                state = -1
            elif r >= self.overbought:
                state = +1
            else:
                state = 0
            action = SignalAction.HOLD
            strength = 0.0
            if state == -1 and prev_state != -1:
                action = SignalAction.BUY
                strength = max(0.0, (self.oversold - r) / self.oversold)
            elif state == +1 and prev_state != +1:
                action = SignalAction.SELL
                strength = max(0.0, (r - self.overbought) / (100.0 - self.overbought))
            out.append(
                self._emit(bar, action, _clamp01(strength), f"rsi={r:.1f}", {"rsi": r})
            )
            prev_state = state
        return out


STRATEGIES: dict[str, type[Strategy]] = {
    "sma_cross": SmaCrossStrategy,
    "rsi": RsiStrategy,
    "macd": MacdStrategy,
    "bollinger": BollingerStrategy,
    "supertrend": SupertrendStrategy,
    "ichimoku": IchimokuStrategy,
    "donchian": DonchianStrategy,
    "mean_reversion": MeanReversionStrategy,
}


def build_strategy(name: str, **kwargs: object) -> Strategy:
    """Instantiate a registered strategy by name.

    Raises :class:`ValueError` on an unknown name. ``CompositeStrategy`` is not
    in the registry because it requires sub-strategy instances; build it directly.
    """
    cls = STRATEGIES.get(name)
    if cls is None:
        known = ", ".join(sorted(STRATEGIES))
        raise ValueError(f"unknown strategy {name!r}; known: {known}")
    return cls(**kwargs)  # type: ignore[arg-type]
