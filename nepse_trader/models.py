"""Core data contracts shared across ingestion, analysis, and trading.

All monetary values are in NPR. All dates are NEPSE trading dates (NPT). We use
Decimal-free floats internally for speed but round at presentation/cost layers.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SourceName(str, Enum):
    NEPSE_OFFICIAL = "nepse_official"
    SHARESANSAR = "sharesansar"
    MEROLAGANI = "merolagani"
    NEPSEALPHA = "nepsealpha"
    CHUKUL = "chukul"
    HAR_REPLAY = "har_replay"
    MANUAL = "manual"


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=False, populate_by_name=True)


class PriceBar(_Base):
    """A single security's end-of-day (or snapshot) OHLCV record."""

    symbol: str
    business_date: date
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = Field(default=None, description="Last traded / closing price")
    previous_close: float | None = None
    volume: int | None = Field(default=None, description="Traded quantity (shares)")
    turnover: float | None = Field(default=None, description="Traded value in NPR")
    trades: int | None = None
    source: SourceName
    fetched_at: datetime | None = None

    @field_validator("symbol")
    @classmethod
    def _upper_symbol(cls, v: str) -> str:
        return v.strip().upper()

    @property
    def change(self) -> float | None:
        if self.close is None or self.previous_close is None:
            return None
        return self.close - self.previous_close

    @property
    def change_percent(self) -> float | None:
        if self.close is None or self.previous_close in (None, 0):
            return None
        return (self.close - self.previous_close) / self.previous_close * 100.0


class IndexValue(_Base):
    """A market index reading (NEPSE Index, Sensitive, sub-indices)."""

    name: str
    business_date: date
    value: float
    change: float | None = None
    change_percent: float | None = None
    source: SourceName
    fetched_at: datetime | None = None


class FloorsheetEntry(_Base):
    """A single matched trade from the floorsheet (transaction-level data)."""

    contract_id: str | None = None
    symbol: str
    business_date: date
    buyer_broker: str | None = None
    seller_broker: str | None = None
    quantity: int
    rate: float
    amount: float | None = None
    source: SourceName

    @field_validator("symbol")
    @classmethod
    def _upper_symbol(cls, v: str) -> str:
        return v.strip().upper()


class MarketStatus(_Base):
    """Whether the market is open, and the as-of timestamp reported by source."""

    is_open: bool
    as_of: datetime | None = None
    session: str | None = None
    source: SourceName


class ReconciledPrice(_Base):
    """A price for a symbol/date agreed (or disputed) across multiple sources."""

    symbol: str
    business_date: date
    close: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    previous_close: float | None = None
    volume: int | None = None
    turnover: float | None = None
    sources_agreeing: list[SourceName] = Field(default_factory=list)
    sources_present: list[SourceName] = Field(default_factory=list)
    disputed_fields: list[str] = Field(default_factory=list)
    confidence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="0..1, share of sources agreeing on close"
    )

    @property
    def is_trustworthy(self) -> bool:
        return self.confidence >= 0.5 and not self.disputed_fields


class SignalAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class Signal(_Base):
    """A strategy's decision for a symbol on a date."""

    symbol: str
    business_date: date
    action: SignalAction
    strategy: str
    strength: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: str = ""
    price: float | None = None
    indicators: dict[str, float] = Field(default_factory=dict)

    @field_validator("symbol")
    @classmethod
    def _upper_symbol(cls, v: str) -> str:
        return v.strip().upper()


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class PaperTrade(_Base):
    """An executed paper trade with full Nepal cost breakdown."""

    trade_id: str
    symbol: str
    side: OrderSide
    business_date: date
    quantity: int
    price: float
    gross_amount: float
    broker_commission: float
    sebon_fee: float
    dp_charge: float
    cgt: float = 0.0
    net_amount: float = Field(description="Cash impact incl. all fees (signed by side handled by ledger)")
    strategy: str | None = None

    @field_validator("symbol")
    @classmethod
    def _upper_symbol(cls, v: str) -> str:
        return v.strip().upper()


class Position(_Base):
    symbol: str
    quantity: int = 0
    avg_cost: float = 0.0  # per-share cost incl. buy-side fees (WAC)

    @field_validator("symbol")
    @classmethod
    def _upper_symbol(cls, v: str) -> str:
        return v.strip().upper()

    @property
    def cost_basis(self) -> float:
        return self.quantity * self.avg_cost
