"""Risk-managed position sizing, stop-loss, and exposure controls.

All functions are pure: they take current state and return decisions, with no
side effects. The backtester calls these at runtime.
"""

from __future__ import annotations


def size_position(
    equity: float,
    price: float,
    risk_per_trade_pct: float = 2.0,
    max_exposure_pct: float = 100.0,
    lot_size: int = 10,
    atr: float | None = None,
    atr_multiple: float = 2.0,
) -> int:
    """Compute the quantity to buy using fixed-fractional position sizing.

    Two sizing modes:

    1. **ATR-driven** (when *atr* is provided): position size is capped so that
       a stop-loss at ``price - atr * atr_multiple`` risks at most
       ``risk_per_trade_pct`` of equity.

    2. **Simple fractional** (when *atr* is None): invests
       ``equity * max_exposure_pct / 100`` divided by price.

    In both modes the result is rounded down to the nearest *lot_size*.
    """
    if price <= 0 or equity <= 0:
        return 0

    if atr is not None and atr > 0:
        stop_distance = atr * atr_multiple
        risk_per_share = stop_distance
        if risk_per_share <= 0:
            return 0
        risk_capital = equity * risk_per_trade_pct / 100.0
        qty = int(risk_capital / risk_per_share)
    else:
        budget = equity * max_exposure_pct / 100.0
        qty = int(budget / price)

    # Round down to lot size.
    qty = (qty // lot_size) * lot_size
    return max(qty, 0)


def stop_loss_price(
    entry_price: float,
    atr: float | None = None,
    atr_multiple: float = 2.0,
    stop_pct: float | None = None,
    circuit_limit: float = 10.0,
) -> float | None:
    """Compute the stop-loss price for a long position.

    Uses ATR-based or percentage-based stop, clamped to *circuit_limit*%
    below the entry price (NEPSE daily circuit is ±10%).
    Returns ``None`` when there isn't enough data to compute a stop.
    """
    if stop_pct is not None:
        raw_stop = entry_price * (1.0 - stop_pct / 100.0)
    elif atr is not None and atr > 0:
        raw_stop = entry_price - atr * atr_multiple
    else:
        return None

    max_loss = entry_price * circuit_limit / 100.0
    clamped_stop = max(raw_stop, entry_price - max_loss)
    return round(clamped_stop, 2)


def take_profit_price(
    entry_price: float,
    risk_reward: float = 2.0,
    atr: float | None = None,
    atr_multiple: float = 2.0,
    tp_pct: float | None = None,
) -> float | None:
    """Compute the take-profit price for a long position."""
    if tp_pct is not None:
        return round(entry_price * (1.0 + tp_pct / 100.0), 2)
    if atr is not None and atr > 0:
        return round(entry_price + atr * atr_multiple * risk_reward, 2)
    return None


def exposure_pct(
    position_value: float,
    equity: float,
) -> float:
    """Return the fraction of equity deployed in a position (0–100)."""
    if equity <= 0:
        return 0.0
    return min(position_value / equity * 100.0, 100.0)
