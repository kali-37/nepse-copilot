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

    def test_friday_sessions_start_after_the_schedule_change(self):
        assert is_trading_day(date(2026, 4, 3)) is False
        assert is_trading_day(date(2026, 4, 10)) is True

    def test_sunday_sessions_end_after_the_schedule_change(self):
        assert is_trading_day(date(2026, 4, 5)) is True
        assert is_trading_day(date(2026, 4, 12)) is False

    def test_monday_is_trading(self):
        # 2026-07-27 is a Monday
        assert is_trading_day(date(2026, 7, 27)) is True

    def test_nepali_new_year_closes_exchange(self):
        assert is_trading_day(date(2024, 1, 1)) is True
        assert is_trading_day(date(2025, 4, 14)) is False
        assert is_trading_day(date(2026, 4, 14)) is False

    def test_constitution_day(self):
        assert is_trading_day(date(2023, 9, 20)) is False

    def test_holiday_list_loaded(self):
        holidays = _get_holidays()
        assert isinstance(holidays, list)
        assert len(holidays) > 0


class TestNextPreviousTradingDay:
    def test_next_from_saturday(self):
        assert next_trading_day(date(2026, 7, 25)) == date(2026, 7, 27)

    def test_next_from_friday(self):
        assert next_trading_day(date(2026, 7, 24)) == date(2026, 7, 24)

    def test_previous_from_saturday(self):
        assert previous_trading_day(date(2026, 7, 25)) == date(2026, 7, 24)

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

    def test_thursday_plus_two_is_monday(self):
        thursday = date(2026, 8, 20)
        assert thursday.strftime("%A") == "Thursday"
        assert add_trading_days(thursday, 2) == date(2026, 8, 24)

    def test_wednesday_plus_two_is_friday_after_the_cutover(self):
        wednesday = date(2026, 8, 19)
        assert add_trading_days(wednesday, 2) == date(2026, 8, 21)

    def test_wednesday_plus_two_is_sunday_before_the_cutover(self):
        wednesday = date(2026, 4, 1)
        assert add_trading_days(wednesday, 2) == date(2026, 4, 5)

    def test_settlement_can_cross_the_cutover(self):
        assert add_trading_days(date(2026, 4, 5), 2) == date(2026, 4, 7)

    def test_zero_snaps_forward_off_a_weekend(self):
        sunday = date(2026, 8, 23)
        assert add_trading_days(sunday, 0) == date(2026, 8, 24)

    def test_zero_on_a_trading_day_is_a_no_op(self):
        wednesday = date(2026, 8, 19)
        assert add_trading_days(wednesday, 0) == wednesday

    def test_counting_starts_from_the_next_trading_day_after_a_weekend(self):
        """The start snaps from Saturday to Monday."""
        saturday = date(2026, 8, 22)
        assert add_trading_days(saturday, 1) == date(2026, 8, 25)

    def test_a_holiday_is_skipped(self):
        monday = date(2026, 4, 13)
        assert add_trading_days(monday, 2) == date(2026, 4, 16)

    def test_negative_moves_back(self):
        monday = date(2026, 8, 24)
        assert add_trading_days(monday, -1) == date(2026, 8, 21)
        assert add_trading_days(monday, -2) == date(2026, 8, 20)

    def test_negative_from_a_weekend_snaps_back_first(self):
        saturday = date(2026, 8, 22)
        assert add_trading_days(saturday, -1) == date(2026, 8, 20)

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
