"""Tests for the NEPSE trading calendar."""

from __future__ import annotations

from datetime import date

from nepse_trader.calendar import (
    _get_holidays,
    add_trading_days,
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


class TestAddTradingDays:
    """T+2 settlement lives on this function, so the weekend cases matter most."""

    def test_thursday_plus_two_is_monday_not_saturday(self):
        thursday = date(2026, 8, 20)
        assert thursday.strftime("%A") == "Thursday"
        assert add_trading_days(thursday, 2) == date(2026, 8, 24)

    def test_wednesday_plus_two_is_sunday_not_friday(self):
        wednesday = date(2026, 8, 19)
        assert add_trading_days(wednesday, 2) == date(2026, 8, 23)

    def test_sunday_plus_two_is_tuesday(self):
        sunday = date(2026, 8, 23)
        assert sunday.strftime("%A") == "Sunday"
        assert add_trading_days(sunday, 2) == date(2026, 8, 25)

    def test_zero_snaps_forward_off_a_weekend(self):
        friday = date(2026, 8, 21)
        assert add_trading_days(friday, 0) == date(2026, 8, 23)

    def test_zero_on_a_trading_day_is_a_no_op(self):
        wednesday = date(2026, 8, 19)
        assert add_trading_days(wednesday, 0) == wednesday

    def test_counting_starts_from_the_next_trading_day_after_a_weekend(self):
        """A trade dated Saturday is really the Sunday session."""
        saturday = date(2026, 8, 22)
        assert add_trading_days(saturday, 1) == add_trading_days(date(2026, 8, 23), 1)

    def test_a_holiday_is_skipped(self):
        constitution_day = date(2026, 9, 20)  # a Sunday, and a holiday
        assert not is_trading_day(constitution_day)
        thursday = date(2026, 9, 17)
        # T+1 is Monday the 21st (Fri/Sat weekend, Sun is the holiday), T+2 the 22nd.
        assert add_trading_days(thursday, 2) == date(2026, 9, 22)

    def test_negative_moves_back(self):
        monday = date(2026, 8, 24)
        assert add_trading_days(monday, -1) == date(2026, 8, 23)
        assert add_trading_days(monday, -2) == date(2026, 8, 20)

    def test_negative_from_a_weekend_snaps_back_first(self):
        saturday = date(2026, 8, 22)
        assert add_trading_days(saturday, -1) == date(2026, 8, 19)

    def test_the_result_is_always_a_trading_day(self):
        start = date(2026, 8, 3)
        for offset in range(30):
            for n in (0, 1, 2, 5, -1, -3):
                result = add_trading_days(date.fromordinal(start.toordinal() + offset), n)
                assert is_trading_day(result)

    def test_forward_then_back_returns_to_the_start(self):
        wednesday = date(2026, 8, 19)
        assert add_trading_days(add_trading_days(wednesday, 3), -3) == wednesday

    def test_a_long_span_is_monotonic(self):
        d = date(2026, 1, 5)
        previous = add_trading_days(d, 0)
        for n in range(1, 60):
            current = add_trading_days(d, n)
            assert current > previous
            previous = current
