from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from nepse_trader.analysis.corporate_actions import adjustment_factor
from nepse_trader.analysis.fundamentals import filter_symbols
from nepse_trader.analysis.market import broker_flows, sector_breadth
from nepse_trader.analysis.portfolio import PortfolioBacktester
from nepse_trader.analysis.shared_portfolio import SharedPortfolioBacktester
from nepse_trader.analysis.walkforward import walk_forward
from nepse_trader.models import (
    CorporateActionType,
    FloorsheetEntry,
    FundamentalData,
    PriceBar,
    ReconciledPrice,
    Signal,
    SignalAction,
    SourceName,
)
from nepse_trader.storage import Storage


def test_bonus_split_and_unpriced_rights_factors():
    assert adjustment_factor(CorporateActionType.BONUS, 1, 1) == Decimal("0.5")
    assert adjustment_factor(CorporateActionType.BONUS, 20, 100) == Decimal(100) / 120
    assert adjustment_factor(CorporateActionType.SPLIT, 10, 1) == Decimal("0.1")
    assert adjustment_factor(CorporateActionType.RIGHTS, 2, 1) == 1
    assert adjustment_factor(CorporateActionType.DIVIDEND, 20, 100) == 1
    with pytest.raises(ValueError):
        adjustment_factor(CorporateActionType.BONUS, 0, 1)


def test_fundamentals_are_dated_and_filters_exclude_missing_values(tmp_path):
    with Storage(tmp_path / "db") as db:
        first = FundamentalData(symbol="nabil", eps=10, pe_ratio=15, pbv=2, sector="Banks", fetched_at=datetime(2026, 1, 1, tzinfo=UTC))
        db.upsert_fundamental(first)
        db.upsert_fundamental(first.model_copy(update={"pe_ratio": 30}), date(2026, 2, 1))
        snapshots = db.fundamentals(date(2026, 1, 31))
        assert snapshots["NABIL"].pe_ratio == 15
        assert db.fundamentals()["NABIL"].pe_ratio == 30
        assert filter_symbols(["NABIL", "MISSING"], snapshots, max_pe=20, min_eps=5) == ["NABIL"]
        assert filter_symbols(["NABIL", "MISSING"], snapshots) == ["NABIL", "MISSING"]
        assert filter_symbols(["NABIL"], snapshots, sector="BANKS") == ["NABIL"]


def test_broker_flow_deduplicates_sources_and_storage(tmp_path):
    trade = FloorsheetEntry(contract_id="1", symbol="NABIL", business_date=date(2026, 1, 1),
        buyer_broker="58", seller_broker="42", quantity=10, rate=100, source=SourceName.SHARESANSAR)
    with Storage(tmp_path / "db") as db:
        db.upsert_floorsheet([trade])
        db.upsert_floorsheet([trade])
        assert len(db.floorsheet_entries(trade.business_date)) == 1
    rows = broker_flows([trade, trade.model_copy(update={"source": SourceName.CHUKUL})])
    assert rows[0]["net_amount"] == 1000
    assert rows[1]["net_amount"] == -1000
    assert sum(row["net_quantity"] for row in rows) == 0


def test_sector_breadth_labels_unknown_and_does_not_invent_changes():
    snapshots = {"A": FundamentalData(symbol="A", sector="Banks")}
    rows = sector_breadth([ReconciledPrice(symbol="A", business_date=date(2026, 1, 1), close=110, previous_close=100),
                          ReconciledPrice(symbol="B", business_date=date(2026, 1, 1), close=100)], snapshots)
    assert rows[0]["sector"] == "Banks"
    assert rows[0]["mean_change_pct"] == 10
    assert rows[1]["sector"] == "Unclassified"
    assert rows[1]["mean_change_pct"] is None


class BuyThenSell:
    name = "fixed"

    def generate(self, bars):
        return [Signal(symbol=bar.symbol, business_date=bar.business_date, strategy=self.name,
                       action=SignalAction.BUY if i == 0 else SignalAction.SELL if i == 2 else SignalAction.HOLD)
                for i, bar in enumerate(bars)]


def _bars(symbol, closes):
    return [PriceBar(symbol=symbol, business_date=date(2026, 1, 1) + timedelta(days=i),
                     open=price, close=price, high=price, low=price, source=SourceName.SHARESANSAR)
            for i, price in enumerate(closes)]


def test_shared_account_executes_next_session_and_applies_fees():
    result = SharedPortfolioBacktester(10000).run(BuyThenSell(), {"A": _bars("A", [100, 100, 120, 120]), "B": _bars("B", [100, 100, 120, 120])})
    assert all(trade["business_date"] != "2026-01-01" for trade in result.trades)
    buys = [trade for trade in result.trades if trade["side"] == "BUY"]
    assert {trade["symbol"] for trade in buys} == {"A", "B"}
    assert sum(Decimal(trade["net_amount"]) for trade in buys) <= 10000
    assert 10000 < result.final_equity < 12000
    assert all(data["quantity"] == 0 for data in result.per_symbol.values())
    assert result.equity_curve[-1][1] == result.final_equity


def test_equal_weight_carries_equity_across_missing_sessions():
    a = _bars("A", [100, 100, 100])
    b = _bars("B", [100, 100, 100])[1:]
    result = PortfolioBacktester(initial_cash=10000).run(BuyThenSell(), {"A": a, "B": b})
    assert 9500 < result.equity_curve[0][1] < 10000  # Buy-side fees, plus B's unspent allocation.
    assert all(equity > 9500 for _, equity in result.equity_curve)


def test_walk_forward_rsi_grid_and_default_ichimoku_are_evaluated():
    bars = _bars("A", [100 + index * 0.5 for index in range(200)])
    assert walk_forward(bars, "rsi").folds[0].best_params.get("period") is not None
    result = walk_forward(bars, "ichimoku")
    assert result.folds
    assert result.folds[0].best_params == {}
    assert all(fold.train_end < fold.val_start for fold in result.folds)
    assert all(fold.in_sample_return_pct > -100 for fold in result.folds)
    with pytest.raises(ValueError):
        walk_forward(bars, "rsi", train_pct=0, val_pct=0.2)


def test_walk_forward_never_fills_on_last_training_session(monkeypatch):
    import importlib
    module = importlib.import_module("nepse_trader.analysis.walkforward")
    bars = _bars("A", [100] * 30 + [200] * 20)
    class TrainingBuy:
        name = "training-buy"
        def generate(self, history):
            return [Signal(symbol="A", business_date=bar.business_date, strategy=self.name,
                           action=SignalAction.BUY if bar.business_date == bars[29].business_date else SignalAction.HOLD)
                    for bar in history]
    monkeypatch.setattr(module, "build_strategy", lambda name, **params: TrainingBuy())
    monkeypatch.setattr(module, "_param_grid", lambda name: [{}])
    result = module.walk_forward(bars, "training-buy")
    assert result.folds[0].train_end == bars[29].business_date
    assert result.folds[0].val_start == bars[30].business_date
    assert result.folds[0].out_of_sample_return_pct == 0


def test_shared_portfolio_carries_exit_until_a_usable_quote():
    class ExitAfterBuy:
        name = "exit-after-buy"
        def generate(self, history):
            return [Signal(symbol="A", business_date=bar.business_date, strategy=self.name,
                           action=SignalAction.BUY if i == 0 else SignalAction.SELL if i == 1 else SignalAction.HOLD)
                    for i, bar in enumerate(history)]
    bars = _bars("A", [100, 100, 100, 110])
    bars[2] = bars[2].model_copy(update={"open": None, "close": None})
    result = SharedPortfolioBacktester(10000).run(ExitAfterBuy(), {"A": bars})
    assert result.per_symbol["A"]["quantity"] == 0
    assert result.trades[-1]["side"] == "SELL"
    assert result.trades[-1]["business_date"] == bars[3].business_date.isoformat()


def test_chukul_contract_date_is_verified_instead_of_relabelled():
    from nepse_trader.ingest.chukul import ChukulClient
    payload = [{"transaction": "2026111905012195", "symbol": "BHL", "buyer": "100", "seller": "48", "quantity": 385.0, "rate": 220.4, "amount": 84854.0}]
    assert len(ChukulClient.parse_floorsheet(payload, date(2026, 11, 19))) == 1
    assert ChukulClient.parse_floorsheet(payload, date(2026, 11, 18)) == []


def test_fifo_total_basis_matches_flat_account_cash_gain():
    from nepse_trader.trading.portfolio import PaperPortfolio
    account = PaperPortfolio(300000)
    buy = account.buy("A", 200, 1000, date(2026, 1, 4))
    sell = account.sell("A", 210, 1000, date(2026, 1, 5))
    assert not account.positions
    assert account.realized_pnl == sell.net_amount - buy.net_amount
    assert account.realized_pnl == account.cash - account.initial_cash


def test_fifo_partial_sales_preserve_remaining_cost_residual():
    from nepse_trader.trading.portfolio import PaperPortfolio
    account = PaperPortfolio(300000)
    account.buy("A", 200, 1000, date(2026, 1, 4))
    for quantity in [333, 333, 334]:
        account.sell("A", 210, quantity, date(2026, 1, 5))
    assert not account.positions
    assert account.realized_pnl == account.cash - account.initial_cash
