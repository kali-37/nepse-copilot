"""Tests for the NEPSE trading calendar."""

from __future__ import annotations

from datetime import date

from nepse_trader.calendar import (
    _get_holidays,
    is_trading_day,
    load_holidays,
    next_trading_day,
    periods_per_year,
    previous_trading_day,
)


class TestIsTradingDay:
    def test_saturday_is_not_trading(self):
        # 2026-07-25 is a Saturday
        assert is_trading_day(date(2026, 7, 25)) is False

    def test_friday_is_not_trading(self):
        # 2026-07-24 is a Friday
        assert is_trading_day(date(2026, 7, 24)) is False

    def test_sunday_is_trading(self):
        # 2026-07-26 is a Sunday
        assert is_trading_day(date(2026, 7, 26)) is True

    def test_monday_is_trading(self):
        # 2026-07-27 is a Monday
        assert is_trading_day(date(2026, 7, 27)) is True

    def test_known_holiday_new_year(self):
        # Jan 1 is a fixed holiday
        # 2027-01-01 is a Friday — already non-trading
        # 2028-01-01 is a Saturday — already non-trading
        # 2024-01-01 is a Monday → should be blocked by holiday
        assert is_trading_day(date(2024, 1, 1)) is False

    def test_constitution_day(self):
        # Sept 20 is Constitution Day
        # 2024-09-20 is a Friday — but it's already non-trading anyway
        # 2026-09-20 is a Sunday → should be blocked by holiday
        assert is_trading_day(date(2026, 9, 20)) is False

    def test_holiday_list_loaded(self):
        holidays = _get_holidays()
        assert isinstance(holidays, list)
        assert len(holidays) > 0


class TestNextPreviousTradingDay:
    def test_next_from_saturday(self):
        # Sat 2026-07-25 → next trading day is Sun 2026-07-26
        assert next_trading_day(date(2026, 7, 25)) == date(2026, 7, 26)

    def test_next_from_friday(self):
        # Fri 2026-07-24 → next trading day is Sun 2026-07-26
        assert next_trading_day(date(2026, 7, 24)) == date(2026, 7, 26)

    def test_previous_from_saturday(self):
        # Sat 2026-07-25 → previous trading day is Thu 2026-07-23
        assert previous_trading_day(date(2026, 7, 25)) == date(2026, 7, 23)

    def test_previous_from_monday(self):
        # Mon 2026-07-27 → previous is Mon (itself, it's a trading day)
        assert previous_trading_day(date(2026, 7, 27)) == date(2026, 7, 27)

    def test_round_trip(self):
        d = date(2026, 7, 22)  # Wednesday
        assert next_trading_day(previous_trading_day(d)) == d


class TestPeriodsPerYear:
    def test_positive_and_reasonable(self):
        ppy = periods_per_year(2026)
        assert 200 <= ppy <= 320

    def test_defaults_to_current_year(self):
        ppy = periods_per_year()
        assert isinstance(ppy, int) and ppy > 0


class TestLoadHolidays:
    def test_loads_without_error(self):
        holidays = load_holidays()
        assert isinstance(holidays, list)
        assert all(isinstance(h, date) for h in holidays)
        assert holidays == sorted(holidays)  # already sorted
