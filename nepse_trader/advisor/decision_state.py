"""Snapshot identity for market evidence and the user's mutable holdings."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from nepse_trader.advisor.positions import available_cash, owned_positions
from nepse_trader.calendar import is_trading_day, next_trading_day, previous_trading_day


def session_dates(today: date) -> tuple[date, date, str]:
    now = datetime.now(ZoneInfo("Asia/Kathmandu"))
    clock = now.time() if now.date() == today else time(15, 1)
    trading = is_trading_day(today)
    previous = previous_trading_day(today - timedelta(days=1))
    expected = today if trading and clock >= time(11) else previous
    entry = today if trading and clock < time(15) else next_trading_day(today + timedelta(days=1))
    phase = "closed" if not trading else "pre_open" if clock < time(11) else "market_hours" if clock < time(15) else "after_close"
    return expected, entry, phase


def market_date(storage, today: date) -> date | None:
    value = storage._conn.execute("SELECT MAX(business_date) FROM reconciled_prices WHERE business_date<=?", (today.isoformat(),)).fetchone()[0]
    return date.fromisoformat(value) if value else None


def decision_state(pipe, today: date) -> str:
    observed = market_date(pipe.storage, today)
    quotes = [dict(row) for row in pipe.storage._conn.execute(
        "SELECT * FROM reconciled_prices WHERE business_date=? ORDER BY symbol", (observed.isoformat() if observed else '',))]
    # Historical repairs can change indicators even when today's close does not.
    revision = pipe.storage._conn.execute("SELECT value FROM app_settings WHERE key='market_revision'").fetchone()
    history = revision[0] if revision else '0'
    events = pipe.storage._conn.execute("SELECT MAX(id) FROM holding_advice_events").fetchone()[0]
    payload = dict(engine="decision-v3-financial-model",events=events,day=today.isoformat(), phase=session_dates(today)[2], quotes=quotes, history=history,
                   cash=str(available_cash(pipe.storage)), positions=sorted(owned_positions(pipe), key=lambda p: p['symbol']),
                   actions=[ca.model_dump(mode='json') for ca in pipe.storage.corporate_actions()])
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
