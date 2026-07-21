"""Tests for corporate actions model, storage, and migrations."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from nepse_trader.models import CorporateAction, CorporateActionType, SourceName
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
