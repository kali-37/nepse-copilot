"""Reads over the ``app_settings`` key/value table.

Migration ``0011_app_settings`` owns the schema. These helpers exist so that the
web API (which writes overrides) and the health report (which only reads them)
agree on what a stored value *means*: a toggle two callers parse differently is
a toggle nobody can trust.

A malformed row degrades to "no override" rather than raising, because a
hand-edited value should hand control back to the environment instead of
breaking the caller. Secrets never live in this table — MeroShare credentials
stay in the environment or the OS keyring.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any


def ensure_table(conn: sqlite3.Connection) -> None:
    """Assert the migrated table exists.

    Deliberately a guard and not ``CREATE TABLE``: creating it here would leave
    an unversioned schema behind that ``schema_version`` does not know about.
    """
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='app_settings'"
    ).fetchone()
    if row is None:
        raise RuntimeError("database is missing migration 0011_app_settings")


def read_json(conn: sqlite3.Connection, key: str) -> tuple[Any | None, str | None]:
    """``(value, updated_at)`` for *key*, or ``(None, None)`` when unusable."""
    ensure_table(conn)
    row = conn.execute(
        "SELECT value, updated_at FROM app_settings WHERE key = ?", (key,)
    ).fetchone()
    if row is None:
        return None, None
    raw = row["value"] if hasattr(row, "keys") else row[0]
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return None, None
    updated = row["updated_at"] if hasattr(row, "keys") else row[1]
    return parsed, updated


def read_bool(conn: sqlite3.Connection, key: str) -> tuple[bool | None, str | None]:
    """As :func:`read_json`, but only a real JSON boolean counts as an override."""
    parsed, updated = read_json(conn, key)
    if not isinstance(parsed, bool):
        return None, None
    return parsed, updated
