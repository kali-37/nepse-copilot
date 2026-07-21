"""Tests for corporate actions model, storage, adjustment, and migrations."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from nepse_trader.ingest.reconcile import adjust_prices
from nepse_trader.models import CorporateAction, CorporateActionType, ReconciledPrice, SourceName
from nepse_trader.storage import Storage
from nepse_trader.storage.migrations import run_pending


def test_corporate_action_model():
    ca = CorporateAction(
        symbol="NABIL",
        ex_date=date(2025, 1, 15),
        action_type=CorporateActionType.BONUS,
        ratio_numerator=1,
        ratio_denominator=1,
        factor=Decimal("0.5"),
        source=SourceName.MANUAL,
        notes="1:1 bonus",
    )
    assert ca.symbol == "NABIL"
    assert ca.action_type is CorporateActionType.BONUS
    assert ca.description == "bonus 1:1"
    assert ca.factor == Decimal("0.5")


def test_corporate_action_symbol_uppercased():
    ca = CorporateAction(
        symbol="nabil",
        ex_date=date(2025, 1, 15),
        action_type=CorporateActionType.SPLIT,
        ratio_numerator=10,
        ratio_denominator=1,
        factor=Decimal("0.1"),
        source=SourceName.MANUAL,
    )
    assert ca.symbol == "NABIL"


def test_upsert_and_read_corporate_action(tmp_path):
    db_path = tmp_path / "test.db"
    storage = Storage(db_path)

    ca = CorporateAction(
        symbol="NABIL",
        ex_date=date(2025, 1, 15),
        action_type=CorporateActionType.BONUS,
        ratio_numerator=1,
        ratio_denominator=1,
        factor=Decimal("0.5"),
        source=SourceName.MANUAL,
        notes="1:1 bonus share",
    )
    storage.upsert_corporate_action(ca)

    all_ca = storage.corporate_actions()
    assert len(all_ca) == 1
    assert all_ca[0].symbol == "NABIL"
    assert all_ca[0].factor == Decimal("0.5")
    assert all_ca[0].notes == "1:1 bonus share"

    # Filter by symbol
    nabil_ca = storage.corporate_actions(symbol="NABIL")
    assert len(nabil_ca) == 1
    assert nabil_ca[0].action_type is CorporateActionType.BONUS

    # Empty for non-existent symbol
    empty = storage.corporate_actions(symbol="GHOST")
    assert len(empty) == 0


def test_upsert_idempotent(tmp_path):
    """Re-upserting the same event updates fields without duplicates."""
    db_path = tmp_path / "test.db"
    storage = Storage(db_path)

    ca = CorporateAction(
        symbol="SCB",
        ex_date=date(2025, 6, 1),
        action_type=CorporateActionType.SPLIT,
        ratio_numerator=10,
        ratio_denominator=1,
        factor=Decimal("0.1"),
        source=SourceName.MANUAL,
    )
    storage.upsert_corporate_action(ca)

    updated = CorporateAction(
        symbol="SCB",
        ex_date=date(2025, 6, 1),
        action_type=CorporateActionType.SPLIT,
        ratio_numerator=5,
        ratio_denominator=1,
        factor=Decimal("0.2"),
        source=SourceName.MANUAL,
        notes="corrected split ratio",
    )
    storage.upsert_corporate_action(updated)

    rows = storage.corporate_actions()
    assert len(rows) == 1
    assert rows[0].ratio_numerator == 5
    assert rows[0].factor == Decimal("0.2")


# ---------------------------------------------------------------------------
# Adjustment pass
# ---------------------------------------------------------------------------


def _price(symbol: str, d: date, close: float) -> ReconciledPrice:
    return ReconciledPrice(symbol=symbol, business_date=d, close=close)


def _ca(symbol: str, d: date, factor_str: str, atype: str = "bonus") -> CorporateAction:
    return CorporateAction(
        symbol=symbol,
        ex_date=d,
        action_type=CorporateActionType(atype),
        ratio_numerator=1,
        ratio_denominator=1,
        factor=Decimal(factor_str),
        source=SourceName.MANUAL,
    )


def test_adjust_no_actions():
    prices = [_price("NABIL", date(2025, 1, 1), 100.0)]
    result = adjust_prices(prices, [])
    assert result[0].adjusted_close == 100.0


def test_adjust_single_bonus():
    prices = [
        _price("NABIL", date(2025, 1, 1), 200.0),
        _price("NABIL", date(2025, 1, 2), 100.0),
    ]
    actions = [_ca("NABIL", date(2025, 1, 2), "0.5")]  # 1:1 bonus on Jan 2
    result = adjust_prices(prices, actions)
    # Pre-event close halved
    assert result[0].adjusted_close == 100.0  # 200 * 0.5
    # Post-event price stays the same (factor = 1.0 since no more events)
    assert result[1].adjusted_close == 100.0


def test_adjust_two_events():
    prices = [
        _price("NABIL", date(2025, 1, 1), 400.0),
        _price("NABIL", date(2025, 2, 1), 200.0),
        _price("NABIL", date(2025, 3, 1), 100.0),
    ]
    actions = [
        _ca("NABIL", date(2025, 2, 1), "0.5"),  # 1:1 bonus
        _ca("NABIL", date(2025, 3, 1), "0.5"),  # another 1:1 bonus
    ]
    result = adjust_prices(prices, actions)
    # Jan: 400 * 0.5 * 0.5 = 100
    assert result[0].adjusted_close == 100.0
    # Feb: 200 * 0.5 = 100
    assert result[1].adjusted_close == 100.0
    # Mar: 100 * 1.0 = 100
    assert result[2].adjusted_close == 100.0


def test_adjust_different_symbols():
    prices = [
        _price("NABIL", date(2025, 1, 1), 200.0),
        _price("SCB", date(2025, 1, 1), 500.0),
    ]
    actions = [_ca("NABIL", date(2025, 1, 2), "0.5")]
    result = adjust_prices(prices, actions)
    # SCB unaffected
    assert result[1].adjusted_close == 500.0


def test_adjust_with_none_close():
    prices = [
        ReconciledPrice(symbol="NABIL", business_date=date(2025, 1, 2), close=None),
    ]
    actions = [_ca("NABIL", date(2025, 1, 2), "0.5")]
    result = adjust_prices(prices, actions)
    assert result[0].adjusted_close is None


def test_migration_applies_cleanly(tmp_path):
    """Corporate actions migration can run on a fresh DB."""
    import sqlite3

    db = tmp_path / "migrate.db"
    conn = sqlite3.connect(str(db))
    run_pending(conn)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(corporate_actions)")}
    assert "factor" in columns
    assert "action_type" in columns
    conn.close()
