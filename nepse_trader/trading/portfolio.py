"""Paper-trading portfolio ledger.

A self-contained, in-memory account that executes simulated BUY/SELL fills with
the *full* Nepal cost stack (broker commission, SEBON fee, DP charge, CGT) applied
via :class:`~nepse_trader.analysis.costs.CostEngine`.

All monetary values use :class:`~decimal.Decimal` (paisa-precise).
"""

from __future__ import annotations

import uuid
from collections import deque
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from nepse_trader.analysis.costs import CostEngine, _to_money
from nepse_trader.models import OrderSide, PaperTrade, Position


@dataclass
class _Lot:
    """An open buy lot, used for FIFO cost-basis & holding-period accounting."""

    business_date: date
    quantity: int
    cost_per_share: Decimal


class PaperPortfolio:
    """An in-memory paper-trading account with realistic Nepal costs."""

    def __init__(
        self,
        initial_cash: float | Decimal = 100_000.0,
        cost_engine: CostEngine | None = None,
        storage: object | None = None,
        investor: str = "individual",
    ) -> None:
        self.initial_cash = _to_money(initial_cash)
        self.cash = self.initial_cash
        self.cost_engine = cost_engine or CostEngine()
        self.storage = storage
        self.investor = investor

        self.positions: dict[str, Position] = {}
        self.trades: list[PaperTrade] = []
        self.realized_pnl: Decimal = Decimal("0.00")
        self._lots: dict[str, deque[_Lot]] = {}

    @staticmethod
    def _validate(symbol: str, price: float | Decimal, quantity: int) -> None:
        if not symbol or not str(symbol).strip():
            raise ValueError("symbol must be a non-empty string")
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        if Decimal(price) <= 0:
            raise ValueError("price must be positive")

    def _persist(self, trade: PaperTrade) -> None:
        if self.storage is not None:
            self.storage.insert_paper_trade(trade)

    def _held(self, symbol: str) -> int:
        pos = self.positions.get(symbol)
        return pos.quantity if pos else 0

    def buy(
        self,
        symbol: str,
        price: float | Decimal,
        quantity: int,
        business_date: date,
        strategy: str | None = None,
    ) -> PaperTrade:
        symbol = str(symbol).strip().upper()
        price_d = _to_money(price)
        self._validate(symbol, price_d, quantity)

        bd = self.cost_engine.compute(OrderSide.BUY, price_d, quantity)
        if bd.net_amount > self.cash:
            raise ValueError(
                f"insufficient funds: need {bd.net_amount:.2f}, have {self.cash:.2f}"
            )

        self.cash = _to_money(self.cash - bd.net_amount)

        pos = self.positions.get(symbol) or Position(symbol=symbol)
        old_qty = pos.quantity
        old_avg = pos.avg_cost
        new_qty = old_qty + quantity
        new_avg = _to_money(
            (Decimal(str(old_qty)) * old_avg + bd.net_amount) / Decimal(str(new_qty))
        )
        pos.quantity = new_qty
        pos.avg_cost = new_avg
        self.positions[symbol] = pos

        cost_per_share = _to_money(bd.net_amount / Decimal(str(quantity)))
        self._lots.setdefault(symbol, deque()).append(
            _Lot(business_date=business_date, quantity=quantity, cost_per_share=cost_per_share)
        )

        trade = PaperTrade(
            trade_id=uuid.uuid4().hex,
            symbol=symbol,
            side=OrderSide.BUY,
            business_date=business_date,
            quantity=quantity,
            price=price_d,
            gross_amount=bd.gross_amount,
            broker_commission=bd.broker_commission,
            sebon_fee=bd.sebon_fee,
            dp_charge=bd.dp_charge,
            cgt=bd.cgt,
            net_amount=bd.net_amount,
            strategy=strategy,
        )
        self.trades.append(trade)
        self._persist(trade)
        return trade

    def sell(
        self,
        symbol: str,
        price: float | Decimal,
        quantity: int,
        business_date: date,
        strategy: str | None = None,
    ) -> PaperTrade:
        symbol = str(symbol).strip().upper()
        price_d = _to_money(price)
        self._validate(symbol, price_d, quantity)

        held = self._held(symbol)
        if quantity > held:
            raise ValueError(
                f"cannot sell {quantity} of {symbol}: only {held} held"
            )

        lots = self._lots.get(symbol, deque())
        remaining = quantity
        basis_of_sold = Decimal("0.00")
        oldest_lot_date: date | None = None
        while remaining > 0 and lots:
            lot = lots[0]
            if oldest_lot_date is None:
                oldest_lot_date = lot.business_date
            take = min(remaining, lot.quantity)
            basis_of_sold += _to_money(Decimal(str(take)) * lot.cost_per_share)
            lot.quantity -= take
            remaining -= take
            if lot.quantity == 0:
                lots.popleft()
        basis_of_sold = _to_money(basis_of_sold)

        holding_days = (
            (business_date - oldest_lot_date).days if oldest_lot_date is not None else None
        )

        bd = self.cost_engine.compute(
            OrderSide.SELL,
            price_d,
            quantity,
            buy_cost_basis=basis_of_sold,
            holding_days=holding_days,
            investor=self.investor,
        )

        self.cash = _to_money(self.cash + bd.net_amount)
        self.realized_pnl = _to_money(self.realized_pnl + (bd.net_amount - basis_of_sold))

        pos = self.positions[symbol]
        pos.quantity -= quantity
        if pos.quantity <= 0:
            self.positions.pop(symbol, None)
            self._lots.pop(symbol, None)
        else:
            self.positions[symbol] = pos

        trade = PaperTrade(
            trade_id=uuid.uuid4().hex,
            symbol=symbol,
            side=OrderSide.SELL,
            business_date=business_date,
            quantity=quantity,
            price=price_d,
            gross_amount=bd.gross_amount,
            broker_commission=bd.broker_commission,
            sebon_fee=bd.sebon_fee,
            dp_charge=bd.dp_charge,
            cgt=bd.cgt,
            net_amount=bd.net_amount,
            strategy=strategy,
        )
        self.trades.append(trade)
        self._persist(trade)
        return trade

    def market_value(self, prices: dict[str, float | Decimal]) -> Decimal:
        total = Decimal("0.00")
        for sym, pos in self.positions.items():
            px = prices.get(sym)
            if px is not None:
                total += Decimal(str(pos.quantity)) * Decimal(str(px))
        return _to_money(total)

    def equity(self, prices: dict[str, float | Decimal]) -> Decimal:
        return _to_money(self.cash + self.market_value(prices))

    def unrealized_pnl(self, prices: dict[str, float | Decimal]) -> Decimal:
        total = Decimal("0.00")
        for sym, pos in self.positions.items():
            px = prices.get(sym)
            if px is not None:
                total += Decimal(str(pos.quantity)) * (Decimal(str(px)) - pos.avg_cost)
        return _to_money(total)

    def holdings(self) -> list[Position]:
        return [self.positions[s] for s in sorted(self.positions)]

    def to_dict(self) -> dict[str, object]:
        return {
            "initial_cash": float(self.initial_cash),
            "cash": float(self.cash),
            "realized_pnl": float(self.realized_pnl),
            "investor": self.investor,
            "positions": [
                {"symbol": p.symbol, "quantity": p.quantity, "avg_cost": float(p.avg_cost)}
                for p in self.holdings()
            ],
            "trades": len(self.trades),
        }

    def summary(self, prices: dict[str, float] | None = None) -> str:
        n_pos = len(self.positions)
        if prices is None:
            return (
                f"PaperPortfolio: cash={self.cash:.2f} positions={n_pos} "
                f"realized_pnl={self.realized_pnl:.2f} trades={len(self.trades)}"
            )
        return (
            f"PaperPortfolio: equity={self.equity(prices):.2f} cash={self.cash:.2f} "
            f"positions={n_pos} unrealized_pnl={self.unrealized_pnl(prices):.2f} "
            f"realized_pnl={self.realized_pnl:.2f} trades={len(self.trades)}"
        )
