"""Current chart state and matured historical evidence for investment ideas.

Scores measure setup evidence, not calibrated win probabilities. Historical
windows never extend beyond the supplied history, and do not overlap.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from statistics import mean

from nepse_trader.advisor.confidence import market
from nepse_trader.analysis import indicators as ind
from nepse_trader.analysis.costs import CostEngine
from nepse_trader.calendar import add_trading_days
from nepse_trader.models import OrderSide, PriceBar


@dataclass
class ChartState:
    close: float
    atr: float
    rsi: float
    ma20: float
    ma50: float
    momentum: float
    volume_ratio: float
    average_volume: float

    def strength(self, horizon: int) -> float:
        trend = (int(self.close > self.ma20) + int(self.ma20 > self.ma50)) / 2
        momentum = min(1, max(0, 0.5 + self.momentum * 10))
        rsi = 1 if 42 <= self.rsi <= 68 else 0.65 if 30 <= self.rsi < 42 else 0.25 if self.rsi > 75 else 0.45
        volume = min(1, self.volume_ratio / 1.5)
        return (0.4 * trend + 0.25 * momentum + 0.2 * rsi + 0.15 * volume) if horizon <= 3 else (0.55 * trend + 0.2 * momentum + 0.15 * rsi + 0.1 * volume)

    def reasons(self) -> list[str]:
        return [
            "Price is above its 20-session trend" if self.close > self.ma20 else "Price is below its 20-session trend",
            "The medium-term trend is rising" if self.ma20 > self.ma50 else "The medium-term trend is weakening",
            "Recent momentum is positive" if self.momentum > 0 else "Recent momentum is negative",
            "Trading volume confirms interest" if self.volume_ratio >= 1.1 else "Volume confirmation is modest",
        ]


def chart_states(bars: list[PriceBar]) -> list[ChartState | None]:
    closes = [bar.close or 0 for bar in bars]
    ma20, ma50, rsi = ind.sma(closes, 20), ind.sma(closes, 50), ind.rsi(closes, 14)
    atr = ind.atr([bar.high or bar.close or 0 for bar in bars], [bar.low or bar.close or 0 for bar in bars], closes, 14)
    out = []
    for i, bar in enumerate(bars):
        window = bars[max(0, i - 19):i + 1]
        complete = i >= 49 and all(all(v is not None and v > 0 and math.isfinite(v) for v in (b.close, b.high, b.low)) for b in bars[i - 49:i + 1])
        if not complete or atr[i] is None or not math.isfinite(atr[i]) or atr[i] <= 0 or rsi[i] is None:
            out.append(None)
            continue
        volumes = [b.volume for b in window if b.volume is not None and b.volume >= 0]
        average = mean(volumes) if volumes else 0
        out.append(ChartState(float(bar.close), float(atr[i]), float(rsi[i]), float(ma20[i]), float(ma50[i]),
            closes[i] / closes[i - 5] - 1, (bar.volume or 0) / average if average else 0, average))
    return out


def historical_evidence(bars: list[PriceBar], states: list[ChartState | None], horizon: int, *, completed_through: date | None = None) -> tuple[int, int]:
    current = states[-1] if states else None
    if current is None:
        return 0, 0
    hits = total = 0
    next_allowed = 49
    engine = CostEngine()
    for i in range(49, len(bars) - horizon):
        state = states[i]
        if state is None or i < next_allowed:
            continue
        if (state.close > state.ma20) != (current.close > current.ma20) or abs(state.rsi - current.rsi) > 18:
            continue
        future = bars[i + 1:i + 1 + horizon]
        if len(future) != horizon or any(any(v is None or not math.isfinite(v) or v <= 0 for v in (b.open, b.high, b.low, b.close)) or b.high < b.low for b in future):
            continue
        if completed_through is not None and future[-1].business_date > completed_through:
            continue
        entry = future[0].open
        if entry is None or entry <= 0:
            continue
        if future[-1].business_date < add_trading_days(future[0].business_date, 2):
            continue
        stop = max(entry * 0.9, entry - state.atr * (1 if horizon <= 3 else 2))
        target = entry + state.atr * (1.5 if horizon <= 3 else 3)
        exit_price = future[-1].close
        for bar in future[2:]:  # Shares cannot be sold before T+2 settlement.
            if bar.business_date < add_trading_days(future[0].business_date, 2):
                continue
            if bar.low <= stop:  # Conservative when both stop and target appear in a session.
                exit_price = min(stop, bar.open) if bar.open and bar.open < stop else stop
                break
            if bar.high >= target:
                exit_price = target
                break
        buy = engine.compute(OrderSide.BUY, entry, 100)
        sell = engine.compute(OrderSide.SELL, exit_price, 100, buy_cost_basis=buy.net_amount, holding_days=horizon)
        hits += sell.net_amount > buy.net_amount
        total += 1
        next_allowed = i + horizon + 1
    return hits, total


def evidence_confidence(state: ChartState, horizon: int, hits: int, total: int, quality: float) -> dict:
    historic = (hits + 2) / (total + 4)
    coverage = min(1, total / 12)
    score = (0.6 * (historic * coverage + 0.5 * (1 - coverage)) + 0.4 * state.strength(horizon)) * quality
    detail = f"{hits}/{total} comparable, non-overlapping historical setups ended profitable after modeled fees (100-share benchmark); current trend, momentum, RSI, volume and source quality are also weighted."
    result = market(score, detail, sample_size=total).as_dict()
    result.update(kind="evidence_score", historical_hits=hits, historical_samples=total,
                  label="Strong evidence" if score >= 0.7 else "Moderate evidence" if score >= 0.5 else "Weak evidence")
    return result
