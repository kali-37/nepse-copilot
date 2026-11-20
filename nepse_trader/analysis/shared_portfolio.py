"""A long-only symbol basket sharing one fee-aware cash ledger."""

from __future__ import annotations

import math
from datetime import date
from decimal import Decimal

from nepse_trader.analysis.backtest import _max_drawdown
from nepse_trader.analysis.portfolio import PortfolioResult
from nepse_trader.models import OrderSide, PriceBar, SignalAction
from nepse_trader.trading.portfolio import PaperPortfolio


class SharedPortfolioBacktester:
    """Act on a session's signals at the next published session's open.

    Sells free cash before buys; names get equal target weights and shares round
    down to lots. Optional periodic rebalancing uses the prior session's mark,
    never the execution session's close. This ledger never writes paper trades.
    """

    def __init__(self, initial_cash: float = 1_000_000, lot_size: int = 10,
                 rebalance_every: int = 0, annualization: int = 252):
        if not math.isfinite(initial_cash) or initial_cash <= 0 or lot_size <= 0 or rebalance_every < 0:
            raise ValueError("Cash and lot size must be positive; rebalance interval cannot be negative.")
        self.initial_cash = initial_cash
        self.lot_size = lot_size
        self.rebalance_every = rebalance_every
        self.annualization = annualization

    def run(self, strategy, symbol_bars: dict[str, list[PriceBar]]) -> PortfolioResult:
        histories = {symbol: sorted(bars, key=lambda bar: bar.business_date)
                     for symbol, bars in symbol_bars.items() if bars}
        ledger = PaperPortfolio(self.initial_cash)
        by_day: dict[date, dict[str, PriceBar]] = {}
        orders: dict[date, dict[str, SignalAction]] = {}
        for symbol, bars in histories.items():
            signals = {signal.business_date: signal.action for signal in strategy.generate(bars)}
            for index, bar in enumerate(bars):
                by_day.setdefault(bar.business_date, {})[symbol] = bar
                if index:
                    action = signals.get(bars[index - 1].business_date, SignalAction.HOLD)
                    if action != SignalAction.HOLD:
                        orders.setdefault(bar.business_date, {})[symbol] = action
        marks: dict[str, Decimal] = {}
        active: set[str] = set()
        pending: dict[str, SignalAction] = {}
        curve = []
        exposures = []
        sales = []

        def held(symbol: str) -> int:
            position = ledger.positions.get(symbol)
            return position.quantity if position else 0

        def equity() -> Decimal:
            return ledger.cash + sum((held(symbol) * price for symbol, price in marks.items()), Decimal(0))

        def sell(symbol: str, quantity: int, price: Decimal, day: date) -> None:
            before = ledger.realized_pnl
            ledger.sell(symbol, price, quantity, day, strategy.name)
            sales.append(float(ledger.realized_pnl - before))

        for index, day in enumerate(sorted(by_day)):
            today = by_day[day]
            fills = {symbol: Decimal(str(bar.open if bar.open is not None else bar.close))
                     for symbol, bar in today.items()
                     if (bar.open if bar.open is not None else bar.close) is not None
                     and math.isfinite(bar.open if bar.open is not None else bar.close)
                     and (bar.open if bar.open is not None else bar.close) > 0}
            pending.update(orders.get(day, {}))
            changes = {symbol: action for symbol, action in pending.items() if symbol in fills}
            for symbol, action in changes.items():
                pending.pop(symbol)
                if action == SignalAction.SELL:
                    active.discard(symbol)
                    if held(symbol):
                        sell(symbol, held(symbol), fills[symbol], day)
                elif action == SignalAction.BUY:
                    active.add(symbol)
            rebalance = bool(self.rebalance_every and index and index % self.rebalance_every == 0)
            tradable = sorted(active.intersection(fills))
            target = equity() / len(active) if active else Decimal(0)
            if rebalance:
                for symbol in tradable:
                    prior_price = marks.get(symbol, fills[symbol])
                    wanted = int(target / prior_price) // self.lot_size * self.lot_size
                    excess = held(symbol) - wanted
                    if excess > 0:
                        sell(symbol, excess, fills[symbol], day)
            for symbol in tradable:
                if changes.get(symbol) != SignalAction.BUY and not rebalance:
                    continue
                prior_price = marks.get(symbol, fills[symbol])
                budget = min(ledger.cash, max(Decimal(0), target - held(symbol) * prior_price))
                price = fills[symbol]
                quantity = int(budget / price) // self.lot_size * self.lot_size
                while quantity and ledger.cost_engine.compute(OrderSide.BUY, price, quantity).net_amount > budget:
                    quantity -= self.lot_size
                if quantity:
                    ledger.buy(symbol, price, quantity, day, strategy.name)
            for symbol, bar in today.items():
                if bar.close is not None and math.isfinite(bar.close) and bar.close > 0:
                    marks[symbol] = Decimal(str(bar.close))
                elif symbol in fills:
                    marks[symbol] = fills[symbol]
            current_equity = equity()
            curve.append((day, float(current_equity)))
            invested = current_equity - ledger.cash
            exposures.append(float(invested / current_equity * 100) if current_equity > 0 else 0)
        final = float(equity())
        returns = [b[1] / a[1] - 1 for a, b in zip(curve, curve[1:], strict=False) if a[1] > 0]
        mean = sum(returns) / len(returns) if returns else 0
        variance = sum((value - mean) ** 2 for value in returns) / (len(returns) - 1) if len(returns) > 1 else 0
        sharpe = mean / math.sqrt(variance) * math.sqrt(self.annualization) if variance > 0 else 0
        years = (curve[-1][0] - curve[0][0]).days / 365.25 if len(curve) > 1 else 0
        cagr = ((final / self.initial_cash) ** (1 / years) - 1) * 100 if years and final > 0 else 0
        return PortfolioResult(strategy_name=strategy.name, initial_cash=self.initial_cash,
            final_equity=final, total_return_pct=(final / self.initial_cash - 1) * 100,
            cagr_pct=cagr, max_drawdown_pct=_max_drawdown(curve), sharpe=sharpe,
            num_trades=len(ledger.trades), win_rate_pct=sum(value > 0 for value in sales) / len(sales) * 100 if sales else 0,
            exposure_pct=sum(exposures) / len(exposures) if exposures else 0, equity_curve=curve,
            trades=[trade.model_dump(mode="json") for trade in ledger.trades],
            per_symbol={symbol: {"quantity": held(symbol), "market_value": float(held(symbol) * marks.get(symbol, Decimal(0)))}
                        for symbol in histories})
