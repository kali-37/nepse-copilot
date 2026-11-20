"""Pure HTTP retry timing and robots rule parsing."""

from __future__ import annotations

import math
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.robotparser import RobotFileParser

from tenacity import wait_exponential


def retry_after_seconds(value: str | None, now: datetime | None = None) -> float | None:
    if not value:
        return None
    try:
        seconds = float(value)
        return max(0, seconds) if math.isfinite(seconds) else None
    except ValueError:
        try:
            when = parsedate_to_datetime(value)
            if when.tzinfo is None:
                when = when.replace(tzinfo=UTC)
            return max(0, (when - (now or datetime.now(UTC))).total_seconds())
        except (ValueError, TypeError, OverflowError):
            return None


def retry_wait(state) -> float:
    error = state.outcome.exception()
    delay = getattr(error, "retry_after", None)
    return delay if delay is not None else wait_exponential(multiplier=1.5, min=2, max=30)(state)


def robots_rules(url: str, status: int, text: str) -> RobotFileParser:
    rules = RobotFileParser(url)
    if status in (401, 403):
        rules.disallow_all = True
    elif status in (404, 410):
        rules.allow_all = True
    elif 200 <= status < 300:
        rules.parse(text.splitlines())
    else:
        raise ValueError("Could not verify robots.txt.")
    return rules
