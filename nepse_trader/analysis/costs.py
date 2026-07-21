"""Nepal equity transaction cost & tax engine.

Computes the full, realistic cost stack for a NEPSE equity trade:
  * Broker commission on a tiered (slab) percentage of transaction amount,
    subject to a flat minimum commission.
  * SEBON regulatory fee (percentage of amount).
  * DP charge (flat per scrip per settlement, sell side typically).
  * Capital Gains Tax on the SELL side, rate depending on holding period and
    investor type (individual short/long, institutional).

All monetary values are :class:`~decimal.Decimal` (paisa-precise). Rates are
sourced from config/cost_model.yaml.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Context, Decimal, localcontext

from nepse_trader.config import CostModel, load_cost_model
from nepse_trader.models import OrderSide

# Paise-precise context: 2 decimal places, half-up rounding.
_MONEY_CTX = Context(prec=30, rounding=ROUND_HALF_UP)


def _to_money(value: float | str | Decimal) -> Decimal:
    """Convert a number to paisa-precise Decimal (2 dp, half-up)."""
    d = Decimal(value) if not isinstance(value, Decimal) else value
    with localcontext(_MONEY_CTX):
        return d.quantize(Decimal("0.01"))


@dataclass
class CostBreakdown:
    gross_amount: Decimal
    broker_commission: Decimal
    sebon_fee: Decimal
    dp_charge: Decimal
    cgt: Decimal
    net_amount: Decimal
    total_fees: Decimal

    def as_dict(self) -> dict[str, float]:
        return {
            "gross_amount": float(self.gross_amount),
            "broker_commission": float(self.broker_commission),
            "sebon_fee": float(self.sebon_fee),
            "dp_charge": float(self.dp_charge),
            "cgt": float(self.cgt),
            "net_amount": float(self.net_amount),
            "total_fees": float(self.total_fees),
        }


class CostEngine:
    def __init__(self, model: CostModel | None = None):
        self.model = model or load_cost_model()
        self._slabs = sorted(self.model.broker_commission_slabs, key=lambda s: s.min_amount)

    def commission_rate(self, amount: Decimal | float) -> Decimal:
        for slab in self._slabs:
            if slab.max_amount is None or amount <= slab.max_amount:
                return Decimal(str(slab.rate_percent))
        return Decimal(str(self._slabs[-1].rate_percent))

    def broker_commission(self, amount: Decimal | float) -> Decimal:
        amount = Decimal(amount) if not isinstance(amount, Decimal) else amount
        rate = self.commission_rate(amount)
        raw = amount * rate / Decimal("100")
        return _to_money(max(raw, Decimal(str(self.model.broker_min_commission))))

    def sebon_fee(self, amount: Decimal | float) -> Decimal:
        amount = Decimal(amount) if not isinstance(amount, Decimal) else amount
        return _to_money(amount * Decimal(str(self.model.sebon_fee_percent)) / Decimal("100"))

    def _cgt_rate(self, investor: str, holding_days: int | None) -> Decimal:
        investor = (investor or "individual").lower()
        if investor.startswith("inst"):
            return Decimal(str(self.model.cgt_institutional_percent))
        if holding_days is not None and holding_days > 365:
            return Decimal(str(self.model.cgt_long_percent))
        return Decimal(str(self.model.cgt_short_percent))

    def compute(
        self,
        side: OrderSide,
        price: float | Decimal,
        quantity: int,
        *,
        buy_cost_basis: float | Decimal | None = None,
        holding_days: int | None = None,
        investor: str = "individual",
        apply_dp: bool = True,
    ) -> CostBreakdown:
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        price_d = Decimal(price) if not isinstance(price, Decimal) else price
        if price_d < 0:
            raise ValueError("price must be non-negative")

        gross = _to_money(price_d * quantity)
        commission = self.broker_commission(gross)
        sebon = self.sebon_fee(gross)
        dp = _to_money(self.model.dp_charge_per_scrip) if apply_dp else Decimal("0.00")

        cgt = Decimal("0.00")
        if side is OrderSide.BUY:
            net = _to_money(gross + commission + sebon + dp)
        else:
            sell_fees = commission + sebon + dp
            net_proceeds_before_tax = _to_money(gross - sell_fees)
            if buy_cost_basis is not None:
                basis = Decimal(buy_cost_basis) if not isinstance(buy_cost_basis, Decimal) else buy_cost_basis
                gain = _to_money(net_proceeds_before_tax - basis)
                if gain > 0:
                    rate = self._cgt_rate(investor, holding_days)
                    cgt = _to_money(gain * rate / Decimal("100"))
            net = _to_money(net_proceeds_before_tax - cgt)

        total_fees = _to_money(commission + sebon + dp + cgt)
        return CostBreakdown(
            gross_amount=gross,
            broker_commission=commission,
            sebon_fee=sebon,
            dp_charge=dp,
            cgt=cgt,
            net_amount=net,
            total_fees=total_fees,
        )

    def effective_buy_cost_per_share(self, price: float | Decimal, quantity: int) -> Decimal:
        bd = self.compute(OrderSide.BUY, price, quantity)
        return _to_money(bd.net_amount / quantity)
