"""Long-only, event-driven backtester with the full Nepal cost model.

The engine replays a chronological sequence of :class:`PriceBar` records for a
single symbol, asks a strategy for its signals, and simulates fills using the
realistic NEPSE cost stack (broker commission, SEBON fee, DP charge, CGT) via
:class:`~nepse_trader.analysis.costs.CostEngine`.

Execution model
---------------
SAME-BAR CLOSE execution. A signal carrying ``business_date == bar.business_date``
is executed at that bar's ``close`` price (optionally adjusted by ``slippage_pct``).
This is a deliberate simplification: it assumes the strategy's decision for a day
is actionable at that day's closing auction. It can be mildly optimistic versus a
strict next-open model, but keeps the accounting transparent and is the convention
documented here so results are reproducible.

Position model
--------------
Long-only and all-in per position: a BUY while flat invests
``cash * position_fraction`` (sized for buy-side fees), a SELL while long
liquidates the entire holding. Pyramiding and shorting are out of scope.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

from nepse_trader.analysis.costs import CostEngine
from nepse_trader.analysis.risk import size_position, stop_loss_price, take_profit_price
from nepse_trader.models import OrderSide, PriceBar, Signal, SignalAction


@dataclass
class BacktestResult:
    """Summary of a single backtest run."""

    strategy_name: str
    initial_cash: float
    final_equity: float
    total_return_pct: float
    cagr_pct: float
    max_drawdown_pct: float
    sharpe: float
    num_trades: int
    win_rate_pct: float
    exposure_pct: float
    equity_curve: list[tuple[date, float]] = field(default_factory=list)
    trades: list[dict] = field(default_factory=list)

    def summary(self) -> dict:
        """Return the headline metrics as a plain dict (no curve/trade detail)."""
        return {
            "strategy_name": self.strategy_name,
            "initial_cash": round(self.initial_cash, 2),
            "final_equity": round(self.final_equity, 2),
            "total_return_pct": round(self.total_return_pct, 2),
            "cagr_pct": round(self.cagr_pct, 2),
            "max_drawdown_pct": round(self.max_drawdown_pct, 2),
            "sharpe": round(self.sharpe, 3),
            "num_trades": self.num_trades,
            "win_rate_pct": round(self.win_rate_pct, 2),
            "exposure_pct": round(self.exposure_pct, 2),
        }

    def __str__(self) -> str:
        return (
            f"[{self.strategy_name}] "
            f"return {self.total_return_pct:+.2f}% "
            f"(CAGR {self.cagr_pct:+.2f}%) | "
            f"equity {self.final_equity:,.2f} | "
            f"maxDD {self.max_drawdown_pct:.2f}% | "
            f"Sharpe {self.sharpe:.2f} | "
            f"trades {self.num_trades} "
            f"win {self.win_rate_pct:.0f}% | "
            f"exposure {self.exposure_pct:.0f}%"
        )


def _max_drawdown(equity_curve: list[tuple[date, float]]) -> float:
    """Maximum peak-to-trough drawdown of an equity curve, as a positive percent.

    Returns 0.0 for an empty/flat/monotonically rising curve. The result is the
    magnitude of the largest decline from a running peak, e.g. a fall from 120 to
    90 yields 25.0 (a 25% drawdown).
    """
    peak = None
    max_dd = 0.0
    for _, equity in equity_curve:
        if peak is None or equity > peak:
            peak = equity
        if peak and peak > 0:
            dd = (peak - equity) / peak * 100.0
            if dd > max_dd:
                max_dd = dd
    return max_dd


class Backtester:
    """Event-driven, long-only backtester over a single symbol's price bars."""

    def __init__(
        self,
        cost_engine: CostEngine | None = None,
        initial_cash: float = 100_000.0,
        position_fraction: float = 1.0,
        annualization: int = 252,
        slippage_pct: float = 0.0,
        stop_loss_pct: float | None = None,
        take_profit_pct: float | None = None,
        use_atr_stops: bool = False,
        risk_per_trade_pct: float | None = None,
        max_exposure_pct: float | None = None,
        lot_size: int = 10,
    ) -> None:
        self.cost_engine = cost_engine or CostEngine()
        self.initial_cash = float(initial_cash)
        self.position_fraction = float(position_fraction)
        self.annualization = int(annualization)
        self.slippage_pct = float(slippage_pct)
        self.stop_loss_pct = float(stop_loss_pct) if stop_loss_pct is not None else None
        self.take_profit_pct = float(take_profit_pct) if take_profit_pct is not None else None
        self.use_atr_stops = bool(use_atr_stops)
        self.risk_per_trade_pct = float(risk_per_trade_pct) if risk_per_trade_pct is not None else None
        self.max_exposure_pct = float(max_exposure_pct) if max_exposure_pct is not None else None
        self.lot_size = int(lot_size)

    def run(
        self,
        strategy,
        bars: list[PriceBar],
        atr_bars: dict[date, float] | None = None,
    ) -> BacktestResult:
        """Replay ``bars`` for ``strategy`` and return a :class:`BacktestResult`.

        Bars are sorted ascending by ``business_date``. The strategy is asked once
        (``strategy.generate(bars)``) and its signals are indexed by date; the bar
        loop executes the matching signal at that bar's close (same-bar model).

        When *atr_bars* is supplied (``{date: atr_value}``), it is used for ATR-based
        position sizing and stop-loss / take-profit checks.
        """
        name = getattr(strategy, "name", strategy.__class__.__name__)

        if not bars:
            return self._empty_result(name)

        bars = sorted(bars, key=lambda b: b.business_date)
        atr_bars = atr_bars or {}

        signals = strategy.generate(bars) or []
        sig_by_date: dict[date, Signal] = {}
        for sig in signals:
            # Last signal for a date wins if duplicated.
            sig_by_date[sig.business_date] = sig

        cash = self.initial_cash
        shares = 0
        entry_basis = 0.0  # total NPR paid incl. buy fees for the open lot
        entry_price = 0.0
        entry_date: date | None = None
        entry_atr: float | None = None

        stop_price: float | None = None
        tp_price: float | None = None

        equity_curve: list[tuple[date, float]] = []
        trades: list[dict] = []
        bars_holding = 0

        for bar in bars:
            close = bar.close
            sig = sig_by_date.get(bar.business_date)

            # --- stop-loss / take-profit check before processing signal ---
            if shares > 0 and close is not None:
                triggered: str | None = None
                if stop_price is not None and close <= stop_price:
                    triggered = "stop_loss"
                elif tp_price is not None and close >= tp_price:
                    triggered = "take_profit"
                if triggered:
                    fill = self._fill_price(close, OrderSide.SELL)
                    holding_days = (bar.business_date - entry_date).days if entry_date else 0
                    bd = self.cost_engine.compute(
                        OrderSide.SELL,
                        fill,
                        shares,
                        buy_cost_basis=entry_basis,
                        holding_days=holding_days,
                    )
                    cash += float(bd.net_amount)
                    pnl = float(bd.net_amount) - entry_basis
                    return_pct = (pnl / entry_basis * 100.0) if entry_basis else 0.0
                    trades.append(
                        {
                            "symbol": bar.symbol,
                            "entry_date": entry_date,
                            "exit_date": bar.business_date,
                            "qty": shares,
                            "entry_price": entry_price,
                            "exit_price": fill,
                            "pnl": round(pnl, 2),
                            "return_pct": round(return_pct, 4),
                            "holding_days": holding_days,
                            "fees": round(float(bd.total_fees), 2),
                            "cgt": round(float(bd.cgt), 2),
                            "exit_reason": triggered,
                        }
                    )
                    shares = 0
                    entry_basis = 0.0
                    entry_price = 0.0
                    entry_date = None
                    entry_atr = None
                    stop_price = None
                    tp_price = None

            if sig is not None and close is not None:
                if sig.action is SignalAction.BUY and shares == 0:
                    fill = self._fill_price(close, OrderSide.BUY)
                    if self.risk_per_trade_pct is not None or self.max_exposure_pct is not None:
                        atr = atr_bars.get(bar.business_date)
                        qty = size_position(
                            equity=cash,
                            price=fill,
                            risk_per_trade_pct=self.risk_per_trade_pct or 2.0,
                            max_exposure_pct=self.max_exposure_pct or 100.0,
                            lot_size=self.lot_size,
                            atr=atr,
                        )
                    else:
                        qty = self._size_buy(cash, fill)
                    if qty > 0:
                        bd = self.cost_engine.compute(OrderSide.BUY, fill, qty)
                        cash -= float(bd.net_amount)
                        shares = qty
                        entry_basis = float(bd.net_amount)
                        entry_price = fill
                        entry_date = bar.business_date
                        entry_atr = atr_bars.get(bar.business_date)
                        stop_price = stop_loss_price(
                            entry_price=fill,
                            atr=entry_atr if self.use_atr_stops else None,
                            stop_pct=self.stop_loss_pct,
                        )
                        tp_price = take_profit_price(
                            entry_price=fill,
                            atr=entry_atr if self.use_atr_stops else None,
                            tp_pct=self.take_profit_pct,
                        )
                elif sig.action is SignalAction.SELL and shares > 0:
                    fill = self._fill_price(close, OrderSide.SELL)
                    holding_days = (bar.business_date - entry_date).days if entry_date else 0
                    bd = self.cost_engine.compute(
                        OrderSide.SELL,
                        fill,
                        shares,
                        buy_cost_basis=entry_basis,
                        holding_days=holding_days,
                    )
                    cash += float(bd.net_amount)
                    pnl = float(bd.net_amount) - entry_basis
                    return_pct = (pnl / entry_basis * 100.0) if entry_basis else 0.0
                    trades.append(
                        {
                            "symbol": bar.symbol,
                            "entry_date": entry_date,
                            "exit_date": bar.business_date,
                            "qty": shares,
                            "entry_price": entry_price,
                            "exit_price": fill,
                            "pnl": round(pnl, 2),
                            "return_pct": round(return_pct, 4),
                            "holding_days": holding_days,
                            "fees": round(float(bd.total_fees), 2),
                            "cgt": round(float(bd.cgt), 2),
                            "exit_reason": "signal",
                        }
                    )
                    shares = 0
                    entry_basis = 0.0
                    entry_price = 0.0
                    entry_date = None
                    entry_atr = None
                    stop_price = None
                    tp_price = None

            # Mark-to-market at this bar's close (fall back to entry price if the
            # bar has no close while holding, so equity stays sensible).
            mark = close if close is not None else entry_price
            equity = cash + shares * (mark or 0.0)
            equity_curve.append((bar.business_date, equity))
            if shares > 0:
                bars_holding += 1

        # Liquidate any open position at the last available close for final equity.
        last_bar = bars[-1]
        if shares > 0 and last_bar.close is not None:
            fill = self._fill_price(last_bar.close, OrderSide.SELL)
            holding_days = (last_bar.business_date - entry_date).days if entry_date else 0
            bd = self.cost_engine.compute(
                OrderSide.SELL,
                fill,
                shares,
                buy_cost_basis=entry_basis,
                holding_days=holding_days,
            )
            cash += float(bd.net_amount)
            pnl = float(bd.net_amount) - entry_basis
            return_pct = (pnl / entry_basis * 100.0) if entry_basis else 0.0
            trades.append(
                {
                    "symbol": last_bar.symbol,
                    "entry_date": entry_date,
                    "exit_date": last_bar.business_date,
                    "qty": shares,
                    "entry_price": entry_price,
                    "exit_price": fill,
                    "pnl": round(pnl, 2),
                    "return_pct": round(return_pct, 4),
                    "holding_days": holding_days,
                    "fees": round(float(bd.total_fees), 2),
                    "cgt": round(float(bd.cgt), 2),
                    "exit_reason": "signal",
                }
            )
            shares = 0
            # Final mark already recorded for the last bar; update it to reflect
            # the realized liquidation so final_equity == curve tail.
            equity_curve[-1] = (last_bar.business_date, cash)

        # If a position is still open (e.g. the last bar had no close so it could
        # not be liquidated above), mark it at the same fallback used for the
        # equity-curve tail (entry price) rather than zero — otherwise the final
        # equity / return / CAGR collapse to a spurious ~-100%.
        if shares == 0:
            final_equity = cash
        else:
            mark = last_bar.close if last_bar.close is not None else entry_price
            final_equity = cash + shares * (mark or 0.0)

        return self._build_result(
            name=name,
            final_equity=final_equity,
            equity_curve=equity_curve,
            trades=trades,
            bars_holding=bars_holding,
            num_bars=len(bars),
        )

    # --- helpers -----------------------------------------------------------

    def _fill_price(self, price: float, side: OrderSide) -> float:
        """Apply slippage: buys fill higher, sells fill lower."""
        if self.slippage_pct == 0.0:
            return price
        adj = price * self.slippage_pct / 100.0
        return price + adj if side is OrderSide.BUY else price - adj

    def _size_buy(self, cash: float, fill_price: float) -> int:
        """Largest whole-share quantity affordable within the cash budget.

        Budget is ``cash * position_fraction``. We seed the estimate from the bare
        per-share price (fees are a small markup, so this slightly OVER-estimates
        the affordable quantity), then correct against the actual CostEngine
        net_amount. Because flat fees (DP) and the minimum-commission floor make
        the per-share cost vary with lot size, we converge in BOTH directions:
        trim down while the lot overruns the budget, then nudge up while the next
        share still fits.
        """
        if fill_price <= 0:
            return 0
        budget = cash * self.position_fraction
        if budget <= 0:
            return 0

        qty = int(math.floor(budget / fill_price))

        def fits(q: int) -> bool:
            if q <= 0:
                return False
            return self.cost_engine.compute(OrderSide.BUY, fill_price, q).net_amount <= budget

        # Trim down until the lot (incl. fees) fits the budget.
        while qty > 0 and not fits(qty):
            qty -= 1
        # Nudge up while the next larger lot still fits (rarely triggers, but keeps
        # sizing exact regardless of fee curvature).
        while fits(qty + 1):
            qty += 1
        return qty

    def _empty_result(self, name: str) -> BacktestResult:
        return BacktestResult(
            strategy_name=name,
            initial_cash=self.initial_cash,
            final_equity=self.initial_cash,
            total_return_pct=0.0,
            cagr_pct=0.0,
            max_drawdown_pct=0.0,
            sharpe=0.0,
            num_trades=0,
            win_rate_pct=0.0,
            exposure_pct=0.0,
            equity_curve=[],
            trades=[],
        )

    def _build_result(
        self,
        *,
        name: str,
        final_equity: float,
        equity_curve: list[tuple[date, float]],
        trades: list[dict],
        bars_holding: int,
        num_bars: int,
    ) -> BacktestResult:
        total_return_pct = (
            (final_equity - self.initial_cash) / self.initial_cash * 100.0
            if self.initial_cash
            else 0.0
        )

        # CAGR over the elapsed calendar span (years from #days / 365.25).
        cagr_pct = 0.0
        if len(equity_curve) >= 2 and self.initial_cash > 0 and final_equity > 0:
            span_days = (equity_curve[-1][0] - equity_curve[0][0]).days
            years = span_days / 365.25
            if years > 0:
                growth = final_equity / self.initial_cash
                cagr_pct = (growth ** (1.0 / years) - 1.0) * 100.0

        max_dd = _max_drawdown(equity_curve)
        sharpe = self._sharpe(equity_curve)

        wins = sum(1 for t in trades if t["pnl"] > 0)
        win_rate_pct = (wins / len(trades) * 100.0) if trades else 0.0
        exposure_pct = (bars_holding / num_bars * 100.0) if num_bars else 0.0

        return BacktestResult(
            strategy_name=name,
            initial_cash=self.initial_cash,
            final_equity=final_equity,
            total_return_pct=total_return_pct,
            cagr_pct=cagr_pct,
            max_drawdown_pct=max_dd,
            sharpe=sharpe,
            num_trades=len(trades),
            win_rate_pct=win_rate_pct,
            exposure_pct=exposure_pct,
            equity_curve=equity_curve,
            trades=trades,
        )

    def _sharpe(self, equity_curve: list[tuple[date, float]]) -> float:
        """Annualized Sharpe from daily equity returns (risk-free = 0)."""
        if len(equity_curve) < 2:
            return 0.0
        rets: list[float] = []
        for (_, prev), (_, cur) in zip(equity_curve, equity_curve[1:], strict=False):
            if prev:
                rets.append(cur / prev - 1.0)
        if len(rets) < 2:
            return 0.0
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
        std = var**0.5
        if std == 0:
            return 0.0
        return mean / std * math.sqrt(self.annualization)
