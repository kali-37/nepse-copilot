"""Bikram-Sambat-aware NEPSE trading calendar.

Provides holiday detection, trading-day queries, and annualisation period
counts. Holidays are loaded from ``config/holidays.yaml`` and supplemented
with the standard weekend (Friday + Saturday, per current NEPSE schedule).
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml

from nepse_trader.config import CONFIG_DIR

# NEPSE standard trading weeks: Sunday–Thursday.
# Friday and Saturday are non-trading days.
_NON_TRADING_WEEKDAYS = {4, 5}  # Monday=0 … Friday=4, Saturday=5


def _default_holidays() -> list[dict[str, Any]]:
    return [
        {"name": "New Year", "month": 1, "day": 1},
        {"name": "Martyrs' Day", "month": 1, "day": 29},
        {"name": "Democracy Day", "month": 2, "day": 19},
        {"name": "International Women's Day", "month": 3, "day": 8},
        {"name": "Constitution Day", "month": 9, "day": 20},
        {"name": "Christmas", "month": 12, "day": 25},
    ]


def load_holidays(path: Path | None = None) -> list[date]:
    """Return a sorted list of known NEPSE holidays as ``date`` objects.

    Reads from the YAML file at *path* (default: ``config/holidays.yaml``).
    Falls back to a curated list of major fixed-date holidays if the file
    does not exist.
    """
    path = path or CONFIG_DIR / "holidays.yaml"
    raw: dict[str, Any] = {}
    if path.exists():
        with path.open(encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}

    holidays: list[date] = []
    entries = raw.get("holidays") or _default_holidays()
    for h in entries:
        year = h.get("year")
        if year:
            holidays.append(date(year, h["month"], h["day"]))
        else:
            for y in (2020, 2021, 2022, 2023, 2024, 2025, 2026, 2027, 2028, 2029, 2030):
                holidays.append(date(y, h["month"], h["day"]))
    # Variable (Bikram Sambat) holidays can specify a range.
    for span in (raw.get("ranges") or []):
        start = date(span["start_year"], span["start_month"], span["start_day"])
        end = date(span["end_year"], span["end_month"], span["end_day"])
        d = start
        while d <= end:
            holidays.append(d)
            d += timedelta(days=1)

    holidays = sorted(set(holidays))
    return holidays


_holidays_cache: list[date] | None = None


def _get_holidays() -> list[date]:
    global _holidays_cache
    if _holidays_cache is None:
        _holidays_cache = load_holidays()
    return _holidays_cache


def is_trading_day(d: date) -> bool:
    """Return ``True`` if *d* is a NEPSE trading day."""
    if d.weekday() in _NON_TRADING_WEEKDAYS:
        return False
    return d not in _get_holidays()


def next_trading_day(d: date) -> date:
    """Return the first trading day on or after *d*."""
    while not is_trading_day(d):
        d += timedelta(days=1)
    return d


def previous_trading_day(d: date) -> date:
    """Return the closest trading day before or on *d*."""
    while not is_trading_day(d):
        d -= timedelta(days=1)
    return d


def add_trading_days(d: date, n: int) -> date:
    """Return the date *n* trading days from *d*, skipping weekends and holidays.

    Positive *n* moves forward, negative *n* moves back, and ``n == 0`` snaps
    forward to the next trading day (so a settlement date computed from a
    Friday trade lands on a day the market is actually open).

    This is what T+2 settlement needs: two *trading* days, not two calendar
    days. A Thursday buy settles the following Monday, not Saturday.
    """
    d = next_trading_day(d) if n >= 0 else previous_trading_day(d)
    step = timedelta(days=1 if n >= 0 else -1)
    for _ in range(abs(n)):
        d += step
        while not is_trading_day(d):
            d += step
    return d


def periods_per_year(reference_year: int | None = None) -> int:
    """Approximate number of NEPSE trading days in a calendar year."""
    y = reference_year or date.today().year
    count = 0
    d = date(y, 1, 1)
    while d.year == y:
        if is_trading_day(d):
            count += 1
        d += timedelta(days=1)
    return max(count, 1)
