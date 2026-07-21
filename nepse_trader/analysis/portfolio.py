"""Multi-symbol portfolio backtester with equal-weight capital allocation."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

from nepse_trader.analysis.backtest import Backtester, _max_drawdown
from nepse_trader.analysis.costs import CostEngine
from nepse_trader.models import PriceBar


@dataclass
class PortfolioResult:
    """Aggregate performance of a multi-symbol portfolio."""

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
    per_symbol: dict[str, dict] = field(default_factory=dict)

    def summary(self) -> dict:
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
            f"exposure {self.exposure_pct:.0f}% | "
            f"symbols {len(self.per_symbol)}"
        )


class PortfolioBacktester:
    """Run a strategy across multiple symbols with equal capital allocation."""

    def __init__(
        self,
        cost_engine: CostEngine | None = None,
        initial_cash: float = 1_000_000.0,
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
        self.annualization = int(annualization)
        self.slippage_pct = float(slippage_pct)
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.use_atr_stops = use_atr_stops
        self.risk_per_trade_pct = risk_per_trade_pct
        self.max_exposure_pct = max_exposure_pct
        self.lot_size = lot_size

    def run(
        self,
        strategy,
        symbol_bars: dict[str, list[PriceBar]],
        symbol_atr: dict[str, dict[date, float]] | None = None,
    ) -> PortfolioResult:
        """Run *strategy* on each symbol and aggregate results.

        *symbol_bars* maps symbol to its price bars.
        *symbol_atr* optionally maps symbol -> {date: atr_value}.
        Each symbol gets an equal share of *initial_cash*.
        """
        if not symbol_bars:
            return self._empty_result(getattr(strategy, "name", type(strategy).__name__))

        n = len(symbol_bars)
        cash_per_symbol = self.initial_cash / n
        symbol_atr = symbol_atr or {}

        per_symbol: dict[str, dict] = {}
        all_trades: list[dict] = []
        all_equity_curves: dict[str, dict[date, float]] = {}
        unique_dates: set[date] = set()

        for sym, bars in symbol_bars.items():
            bt = Backtester(
                cost_engine=self.cost_engine,
                initial_cash=cash_per_symbol,
                position_fraction=1.0,
                annualization=self.annualization,
                slippage_pct=self.slippage_pct,
                stop_loss_pct=self.stop_loss_pct,
                take_profit_pct=self.take_profit_pct,
                use_atr_stops=self.use_atr_stops,
                risk_per_trade_pct=self.risk_per_trade_pct,
                max_exposure_pct=self.max_exposure_pct,
                lot_size=self.lot_size,
            )
            atr = symbol_atr.get(sym)
            result = bt.run(strategy, bars, atr_bars=atr)
            per_symbol[sym] = result.summary()
            per_symbol[sym]["trades"] = len(result.trades)
            equity_map = {d: e for d, e in result.equity_curve}
            all_equity_curves[sym] = equity_map
            unique_dates.update(equity_map.keys())
            all_trades.extend(result.trades)

        sorted_dates = sorted(unique_dates)
        portfolio_equity: list[tuple[date, float]] = []
        for d in sorted_dates:
            total = 0.0
            for eq_map in all_equity_curves.values():
                total += eq_map.get(d, 0.0)
            portfolio_equity.append((d, total))

        final_equity = portfolio_equity[-1][1] if portfolio_equity else 0.0
        total_return_pct = (
            (final_equity - self.initial_cash) / self.initial_cash * 100.0
            if self.initial_cash
            else 0.0
        )

        cagr_pct = 0.0
        if len(portfolio_equity) >= 2 and self.initial_cash > 0 and final_equity > 0:
            span_days = (portfolio_equity[-1][0] - portfolio_equity[0][0]).days
            years = span_days / 365.25
            if years > 0:
                cagr_pct = ((final_equity / self.initial_cash) ** (1.0 / years) - 1.0) * 100.0

        max_dd = _max_drawdown(portfolio_equity)
        sharpe = self._portfolio_sharpe(portfolio_equity)
        wins = sum(1 for t in all_trades if t.get("pnl", 0) > 0)
        win_rate_pct = (wins / len(all_trades) * 100.0) if all_trades else 0.0
        # exposure = avg of per-symbol exposure
        exposure_pct = sum(
            s.get("exposure_pct", 0.0) for s in per_symbol.values()
        ) / max(len(per_symbol), 1)

        return PortfolioResult(
            strategy_name=getattr(strategy, "name", type(strategy).__name__),
            initial_cash=self.initial_cash,
            final_equity=final_equity,
            total_return_pct=total_return_pct,
            cagr_pct=cagr_pct,
            max_drawdown_pct=max_dd,
            sharpe=sharpe,
            num_trades=len(all_trades),
            win_rate_pct=win_rate_pct,
            exposure_pct=exposure_pct,
            equity_curve=portfolio_equity,
            trades=all_trades,
            per_symbol=per_symbol,
        )

    def _portfolio_sharpe(self, equity_curve: list[tuple[date, float]]) -> float:
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

    def _empty_result(self, name: str) -> PortfolioResult:
        return PortfolioResult(
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
        )
