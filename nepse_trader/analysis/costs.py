"""Nepal equity transaction cost & tax engine.

Computes the full, realistic cost stack for a NEPSE equity trade:
  * Broker commission on a tiered (slab) percentage of transaction amount,
    subject to a flat minimum commission.
  * SEBON regulatory fee (percentage of amount).
  * DP charge (flat per scrip per settlement, sell side typically).
  * Capital Gains Tax on the SELL side, rate depending on holding period and
    investor type (individual short/long, institutional).

All rates are sourced from config/cost_model.yaml so they can be updated when
SEBON/NEPSE revise the schedule without touching code. The math here is
deliberately explicit and rounded to paisa (2 dp) at the end.
"""

from __future__ import annotations

from dataclasses import dataclass

from nepse_trader.config import CostModel, load_cost_model
from nepse_trader.models import OrderSide


@dataclass
class CostBreakdown:
    gross_amount: float
    broker_commission: float
    sebon_fee: float
    dp_charge: float
    cgt: float
    # Net cash settled: for BUY, cash you pay out (gross + fees);
    # for SELL, cash you receive (gross - fees - cgt).
    net_amount: float
    total_fees: float

    def as_dict(self) -> dict[str, float]:
        return {
            "gross_amount": self.gross_amount,
            "broker_commission": self.broker_commission,
            "sebon_fee": self.sebon_fee,
            "dp_charge": self.dp_charge,
            "cgt": self.cgt,
            "net_amount": self.net_amount,
            "total_fees": self.total_fees,
        }


def _round2(x: float) -> float:
    return round(x + 1e-9, 2)


class CostEngine:
    def __init__(self, model: CostModel | None = None):
        self.model = model or load_cost_model()
        self._slabs = sorted(self.model.broker_commission_slabs, key=lambda s: s.min_amount)

    def commission_rate(self, amount: float) -> float:
        """Return the broker commission percentage applicable to `amount`.

        NEPSE broker commission is charged at a single slab rate determined by
        the total transaction amount (not marginal/blended). The official
        schedule assigns a boundary value to the LOWER (higher-rate) tier — e.g.
        a transaction of exactly Rs 50,000 is charged at 0.36%, not 0.33%. So we
        match the first slab whose inclusive upper bound (max_amount) covers the
        amount: the slab range is (prev_max, max], with the final open slab
        (max_amount=None) catching everything above.
        """
        for slab in self._slabs:
            if slab.max_amount is None or amount <= slab.max_amount:
                return slab.rate_percent
        return self._slabs[-1].rate_percent

    def broker_commission(self, amount: float) -> float:
        raw = amount * self.commission_rate(amount) / 100.0
        return _round2(max(raw, self.model.broker_min_commission))

    def sebon_fee(self, amount: float) -> float:
        return _round2(amount * self.model.sebon_fee_percent / 100.0)

    def _cgt_rate(self, investor: str, holding_days: int | None) -> float:
        investor = (investor or "individual").lower()
        if investor.startswith("inst"):
            return self.model.cgt_institutional_percent
        # Individual long-term rate applies only when held MORE THAN 365 days;
        # a sale on exactly the 365th day is still short-term (7.5%).
        if holding_days is not None and holding_days > 365:
            return self.model.cgt_long_percent
        return self.model.cgt_short_percent

    def compute(
        self,
        side: OrderSide,
        price: float,
        quantity: int,
        *,
        buy_cost_basis: float | None = None,
        holding_days: int | None = None,
        investor: str = "individual",
        apply_dp: bool = True,
    ) -> CostBreakdown:
        """Compute the full cost breakdown for one trade.

        For SELL trades, `buy_cost_basis` (total NPR originally paid incl. buy
        fees, for the quantity being sold) enables correct CGT on realized gain.
        If omitted, CGT is computed on gross proceeds-less-sell-fees only when a
        gain cannot be determined CGT is taken as 0 (caller should pass basis).
        """
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        if price < 0:
            raise ValueError("price must be non-negative")

        gross = _round2(price * quantity)
        commission = self.broker_commission(gross)
        sebon = self.sebon_fee(gross)
        dp = self.model.dp_charge_per_scrip if apply_dp else 0.0

        cgt = 0.0
        if side is OrderSide.BUY:
            # Buyer pays gross + commission + sebon + DP.
            net = _round2(gross + commission + sebon + dp)
        else:
            sell_fees = commission + sebon + dp
            net_proceeds_before_tax = gross - sell_fees
            if buy_cost_basis is not None:
                gain = net_proceeds_before_tax - buy_cost_basis
                if gain > 0:
                    rate = self._cgt_rate(investor, holding_days)
                    cgt = _round2(gain * rate / 100.0)
            net = _round2(net_proceeds_before_tax - cgt)

        total_fees = _round2(commission + sebon + dp + cgt)
        return CostBreakdown(
            gross_amount=gross,
            broker_commission=commission,
            sebon_fee=sebon,
            dp_charge=_round2(dp),
            cgt=cgt,
            net_amount=net,
            total_fees=total_fees,
        )

    def effective_buy_cost_per_share(self, price: float, quantity: int) -> float:
        """Per-share cost incl. buy-side fees — used as WAC basis."""
        bd = self.compute(OrderSide.BUY, price, quantity)
        return bd.net_amount / quantity
