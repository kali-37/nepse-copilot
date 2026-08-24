"""Data contracts for the MeroShare mirror.

:class:`MeroShareHolding` is deliberately shaped like
:class:`nepse_trader.models.Position` — same ``symbol``, an integer share count,
and a per-share cost — so a later "real vs paper" view can put the two side by
side without a translation layer. It carries the extra fields the portal
actually reports (ISIN, demat number, pledged balance, previous close) because
throwing them away would mean a second sync to get them back.

Money is ``float`` here, not ``Decimal``: these are figures the portal computed
and we are mirroring, not a ledger we are keeping. That matches ``PriceBar``,
which is also observation rather than accounting.

No model in this module has a credential field, and none ever will — see the
``0006_meroshare`` migration docstring.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=False, populate_by_name=True)


class MeroShareHolding(_Base):
    """One scrip balance in the user's demat account, as MeroShare reports it."""

    symbol: str
    current_balance: int = 0
    wacc: float | None = Field(default=None, description="Weighted average cost per share, NPR")
    demat_number: str = ""
    # Persisted mirrors keep only these privacy-safe derivatives.  The raw
    # demat/BOID may exist on a freshly fetched in-memory object long enough to
    # issue the CDSC read, but it must never be written to SQLite or serialized
    # by a public API.
    demat_hash: str = ""
    demat_last4: str = ""
    isin: str | None = None
    script_desc: str | None = None
    previous_balance: int | None = None
    pledged_balance: int | None = None
    previous_closing_price: float | None = None
    last_transaction_date: date | None = None
    source: str = "meroshare"

    @field_validator("symbol")
    @classmethod
    def _upper_symbol(cls, v: str) -> str:
        return v.strip().upper()

    @property
    def cost_basis(self) -> float | None:
        """Total invested in this scrip per the portal's WACC."""
        if self.wacc is None:
            return None
        return self.current_balance * self.wacc

    @property
    def market_value(self) -> float | None:
        if self.previous_closing_price is None:
            return None
        return self.current_balance * self.previous_closing_price


class MeroShareTransaction(_Base):
    """One demat credit or debit. ``quantity`` is signed: debits are negative."""

    symbol: str
    transaction_date: date
    quantity: int = 0
    transaction_type: str = ""
    description: str | None = None
    price: float | None = None
    balance_after: int | None = None
    reference: str | None = None
    demat_number: str = ""
    demat_hash: str = ""
    demat_last4: str = ""
    source: str = "meroshare"

    @field_validator("symbol")
    @classmethod
    def _upper_symbol(cls, v: str) -> str:
        return v.strip().upper()

    @property
    def txn_id(self) -> str:
        """Deterministic id — the portal exposes no stable row identifier.

        Hashing the natural key is what makes a re-sync idempotent: the same
        transaction hashes to the same id and upserts over itself. Fields are
        joined with a separator that cannot appear in them, so two different
        transactions cannot collide by concatenation.
        """
        parts = [
            self.demat_number,
            self.symbol,
            self.transaction_date.isoformat(),
            self.transaction_type,
            str(self.quantity),
            self.reference or "",
        ]
        return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:24]


class MeroSharePortfolio(_Base):
    """A whole sync's worth of holdings, plus where it came from."""

    holdings: list[MeroShareHolding] = Field(default_factory=list)
    fetched_at: datetime | None = None
    source: str = "meroshare"

    @property
    def total_cost_basis(self) -> float:
        return sum(h.cost_basis or 0.0 for h in self.holdings)

    @property
    def total_market_value(self) -> float:
        return sum(h.market_value or 0.0 for h in self.holdings)

    def by_symbol(self) -> dict[str, MeroShareHolding]:
        return {h.symbol: h for h in self.holdings}


class HoldingDiff(_Base):
    """One symbol's disagreement (or agreement) between real and paper books."""

    symbol: str
    real_quantity: int = 0
    paper_quantity: int = 0
    real_wacc: float | None = None
    paper_avg_cost: float | None = None

    @property
    def quantity_delta(self) -> int:
        """Real minus paper. Positive means the real account holds more."""
        return self.real_quantity - self.paper_quantity

    @property
    def only_in(self) -> str | None:
        """``"real"``, ``"paper"``, or ``None`` when both hold the symbol."""
        if self.real_quantity and not self.paper_quantity:
            return "real"
        if self.paper_quantity and not self.real_quantity:
            return "paper"
        return None

    @property
    def agrees(self) -> bool:
        return self.real_quantity == self.paper_quantity
