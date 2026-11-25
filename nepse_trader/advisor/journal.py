"""Prediction journal lifecycle and persistence.

The journal is deliberately small and explicit.  A prediction is written before
its result is known, then moves through ``open -> scored -> reviewed -> retired``.
Scoring is supplied by :mod:`nepse_trader.advisor.outcomes`; this module owns the
audit trail and the review/lesson boundary.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from nepse_trader.advisor.confidence import (
    DEFAULT_PRIOR,
    Confidence,
    confidence_from_history,
    market,
    wilson_lower_bound,
)
from nepse_trader.calendar import add_trading_days
from nepse_trader.rag.corpus import KIND_REPORT, Document
from nepse_trader.rag.index import DocumentIndex


class JournalError(ValueError):
    """Raised when a prediction lifecycle transition is invalid."""


@dataclass(frozen=True)
class Prediction:
    """A journal row represented as a typed, read-only value."""

    id: int
    prediction_id: str
    symbol: str
    status: str
    horizon: str
    horizon_days: int
    made_on: date
    deadline: date
    confidence: Confidence
    outcome: str | None = None
    hit: int | None = None
    lesson_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "prediction_id": self.prediction_id,
            "symbol": self.symbol,
            "status": self.status,
            "horizon": self.horizon,
            "horizon_days": self.horizon_days,
            "made_on": self.made_on.isoformat(),
            "deadline": self.deadline.isoformat(),
            "confidence": self.confidence.as_dict(),
            "outcome": self.outcome,
            "hit": self.hit,
            "lesson_id": self.lesson_id,
        }


def _as_date(value: date | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _now(value: date | datetime | str | None = None) -> str:
    if value is None:
        return datetime.now(UTC).isoformat()
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _confidence(value: Confidence | float | int | None) -> Confidence:
    if isinstance(value, Confidence):
        return value
    if value is None:
        return market(0.45, "no supplied track record; house prior")
    return market(float(value), "caller supplied forecast confidence")


def confidence_for_prediction(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    action: str = "",
    horizon: str = "",
    horizon_days: int = 0,
    kind: str = "plan",
    prior: float = DEFAULT_PRIOR,
) -> Confidence:
    """Return confidence from comparable, already-resolved journal calls.

    Comparability is intentionally narrow: the first bucket matches symbol,
    prediction kind, action, and trading-day horizon. If it has no resolved
    calls, the fallback keeps the symbol/kind/horizon and drops action; the
    final fallback uses the global kind/horizon bucket. ``UNRESOLVED`` and
    ``NO_DATA`` are excluded at every level, so uncertainty never becomes
    calibration evidence.
    """
    symbol = str(symbol).strip().upper()
    action = str(action or "")
    horizon = str(horizon or "")
    horizon_days = int(horizon_days or 0)
    common = [
        "status IN ('scored','reviewed','retired')",
        "outcome NOT IN ('UNRESOLVED','NO_DATA')",
        "kind = ?",
        "horizon_days = ?",
        "hit IS NOT NULL",
    ]

    buckets = [
        ("symbol/action/horizon", common + ["symbol = ?", "action = ?"], [kind, horizon_days, symbol, action]),
        ("symbol/horizon", common + ["symbol = ?"], [kind, horizon_days, symbol]),
        ("global/horizon", common, [kind, horizon_days]),
    ]
    for label, clauses, params in buckets:
        row = conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(CASE WHEN hit=1 THEN 1 ELSE 0 END), 0) AS hits "
            "FROM predictions WHERE " + " AND ".join(clauses),
            params,
        ).fetchone()
        n = int(row["n"] or 0)
        if n:
            hits = int(row["hits"] or 0)
            basis = (
                f"{label} history for {symbol}"
                + (f"/{action}" if action else "")
                + (f"/{horizon or horizon_days} horizon" if horizon or horizon_days else "")
            )
            return confidence_from_history(hits, n, prior=prior, basis=basis)
    return market(
        prior,
        f"no resolved comparable predictions for {symbol}; house prior",
    )


def _row_to_prediction(row: sqlite3.Row | dict[str, Any]) -> Prediction:
    made = _as_date(row["made_on"])
    deadline = _as_date(row["deadline"])
    return Prediction(
        id=int(row["id"]),
        prediction_id=str(row["prediction_id"]),
        symbol=str(row["symbol"]),
        status=str(row["status"]),
        horizon=str(row["horizon"] or ""),
        horizon_days=int(row["horizon_days"] or 0),
        made_on=made,
        deadline=deadline,
        confidence=market(float(row["confidence"] or 0.0), str(row["confidence_basis"] or "")),
        outcome=row["outcome"],
        hit=(int(row["hit"]) if row["hit"] is not None else None),
        lesson_id=row["lesson_id"],
    )


def _fetch(conn: sqlite3.Connection, prediction_id: str) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM predictions WHERE prediction_id = ? OR CAST(id AS TEXT) = ?",
        (prediction_id, prediction_id),
    ).fetchone()
    if row is None:
        raise JournalError(f"prediction not found: {prediction_id}")
    return row


def get_prediction(conn: sqlite3.Connection, prediction_id: str) -> Prediction:
    """Return one journal entry by its stable id (or numeric row id)."""
    return _row_to_prediction(_fetch(conn, prediction_id))


def log_prediction(
    conn: sqlite3.Connection,
    card: object,
    *,
    made_on: date | str,
    horizon: str = "",
    confidence: Confidence | float | int | None = None,
    run_id: int | None = None,
    kind: str = "plan",
    prediction_id: str | None = None,
    commit: bool = True,
) -> Prediction:
    """Write a plan card before its outcome is known.

    All values that can later be compared with a realized trade are copied at
    log time.  This prevents a later strategy/config change from rewriting the
    historical call.
    """
    made = _as_date(made_on)
    symbol = str(card.symbol)
    horizon_days = int(card.horizon_days or 0)
    deadline = add_trading_days(made, horizon_days) if horizon_days > 0 else made
    conf = _confidence(confidence if confidence is not None else getattr(card, "confidence", None))
    pred_id = prediction_id or f"pred:{made.isoformat()}:{symbol}:{uuid4().hex}"
    targets = list(getattr(card, "targets", []) or [])
    generated = _now()
    conn.execute(
        """
        INSERT INTO predictions (
            prediction_id, run_id, kind, symbol, made_on, horizon, horizon_days,
            deadline, action, reference_price, entry_low, entry_high, stop,
            target_1, target_2, quantity, expected_net_pnl, confidence,
            confidence_band, confidence_basis, rationale, status, created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            pred_id,
            run_id,
            kind,
            symbol,
            made.isoformat(),
            horizon,
            horizon_days,
            deadline.isoformat(),
            str(getattr(card, "action", "")),
            getattr(card, "reference_price", None),
            getattr(card, "entry_low", None),
            getattr(card, "entry_high", None),
            getattr(card, "stop", None),
            targets[0] if targets else None,
            targets[1] if len(targets) > 1 else None,
            int(getattr(card, "quantity", 0) or 0),
            float(getattr(card, "net_pnl", 0) or 0),
            conf.value,
            conf.band,
            conf.basis,
            str(getattr(card, "rationale", "") or ""),
            "open",
            generated,
        ),
    )
    if commit:
        conn.commit()
    return get_prediction(conn, pred_id)


def log_plan_cards(
    conn: sqlite3.Connection,
    cards: list[object],
    *,
    made_on: date | str,
    horizon: str = "",
    confidence: Confidence | float | int | None = None,
    run_id: int | None = None,
    kind: str = "plan",
    commit: bool = True,
) -> list[Prediction]:
    """Log a batch of cards, returning entries in input order."""
    out = [
        log_prediction(
            conn,
            card,
            made_on=made_on,
            horizon=horizon,
            confidence=confidence,
            run_id=run_id,
            kind=kind,
            commit=False,
        )
        for card in cards
    ]
    if commit:
        conn.commit()
    return out


def record_score(conn: sqlite3.Connection, prediction_id: str, result: object) -> Prediction:
    """Apply a pure outcome result to a journal row.

    ``result`` is intentionally duck-typed so the journal remains compatible
    with the outcome agent's frozen dataclass and with simple test doubles.
    """
    row = _fetch(conn, prediction_id)
    if row["status"] != "open":
        raise JournalError(f"only open predictions can be scored (status={row['status']})")
    outcome = getattr(result, "outcome", None)
    if outcome is None and isinstance(result, dict):
        outcome = result.get("outcome")
    outcome = getattr(outcome, "value", outcome)
    if not outcome:
        raise JournalError("score result must include an outcome")

    def field(name: str, default=None):
        value = getattr(result, name, default)
        if isinstance(result, dict):
            value = result.get(name, default)
        return value

    resolved_on = field("resolved_on")
    terminal = str(outcome) not in {"UNRESOLVED", "NO_DATA"}

    # ``outcomes.score_prediction`` deliberately returns ``Decimal`` for P&L
    # so callers can retain paise precision.  SQLite's stdlib adapter does not
    # bind Decimal values by default, however, and the journal table stores a
    # REAL.  Normalize Decimal at this persistence boundary (as text, which
    # SQLite's REAL affinity converts without losing the represented amount)
    # while leaving the pure outcome result strongly typed for Python callers.
    def sqlite_number(value: object):
        return str(value) if isinstance(value, Decimal) else value

    conn.execute(
        """
        UPDATE predictions SET status=CASE WHEN ? THEN 'scored' ELSE status END,
            outcome=?, resolved_on=?,
            realized_exit_price=?, realized_net_pnl=?, mfe=?, mae=?,
            bars_seen=?, hit=?, scored_at=CASE WHEN ? THEN ? ELSE scored_at END
        WHERE id=?
        """,
        (
            terminal,
            str(outcome),
            _as_date(resolved_on).isoformat() if resolved_on else None,
            sqlite_number(field("realized_exit_price", field("exit_price"))),
            sqlite_number(field("realized_net_pnl")),
            sqlite_number(field("mfe")),
            sqlite_number(field("mae")),
            int(field("bars_seen", 0) or 0),
            field("hit"),
            terminal,
            _now(),
            int(row["id"]),
        ),
    )
    from nepse_trader.advisor.outcomes import _persist_evaluation
    _persist_evaluation(conn, row["prediction_id"], result)
    if terminal:
        _refresh_calibration(conn, int(row["id"]))
    conn.commit()
    return get_prediction(conn, prediction_id)


def score_prediction(conn: sqlite3.Connection, prediction_id: str, result: object) -> Prediction:
    """Compatibility alias for :func:`record_score`."""
    return record_score(conn, prediction_id, result)


def _refresh_calibration(conn: sqlite3.Connection, row_id: int) -> None:
    """Rebuild the materialised symbol/horizon roll-up after a score."""
    row = conn.execute("SELECT symbol, horizon, kind FROM predictions WHERE id = ?", (row_id,)).fetchone()
    if row is None or row["kind"] == "decision_v1":
        return
    stats = conn.execute(
        """
        SELECT COUNT(*) AS resolved,
               COALESCE(SUM(CASE WHEN hit=1 THEN 1 ELSE 0 END), 0) AS hits,
               AVG(expected_net_pnl) AS expected_pnl,
               AVG(realized_net_pnl) AS realized_pnl
        FROM predictions
        WHERE symbol = ? AND horizon = ?
          AND kind != 'decision_v1' AND hit IS NOT NULL
          AND status IN ('scored', 'reviewed', 'retired')
          AND outcome NOT IN ('UNRESOLVED', 'NO_DATA')
        """,
        (row["symbol"], row["horizon"]),
    ).fetchone()
    resolved = int(stats["resolved"] or 0)
    hits = int(stats["hits"] or 0)
    hit_rate = hits / resolved if resolved else None
    conn.execute(
        """
        INSERT INTO calibration
            (scope, subject, horizon, hits, resolved, hit_rate, wilson_lower,
             mean_expected_pnl, mean_realized_pnl, updated_at)
        VALUES ('symbol', ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(scope, subject, horizon) DO UPDATE SET
            hits=excluded.hits, resolved=excluded.resolved,
            hit_rate=excluded.hit_rate, wilson_lower=excluded.wilson_lower,
            mean_expected_pnl=excluded.mean_expected_pnl,
            mean_realized_pnl=excluded.mean_realized_pnl,
            updated_at=excluded.updated_at
        """,
        (
            row["symbol"],
            row["horizon"],
            hits,
            resolved,
            hit_rate,
            wilson_lower_bound(hits, resolved),
            stats["expected_pnl"],
            stats["realized_pnl"],
            _now(),
        ),
    )


def record_review(
    conn: sqlite3.Connection,
    prediction_id: str,
    review: str,
    *,
    reviewed_at: date | datetime | str | None = None,
) -> Prediction:
    """Attach the AI (or human) review to a scored prediction."""
    row = _fetch(conn, prediction_id)
    if row["status"] != "scored":
        raise JournalError(f"only scored predictions can be reviewed (status={row['status']})")
    text = str(review or "").strip()
    if not text:
        raise JournalError("review cannot be empty")
    conn.execute(
        "UPDATE predictions SET status='reviewed', review=?, reviewed_at=? WHERE id=?",
        (text, _now(reviewed_at), int(row["id"])),
    )
    conn.commit()
    return get_prediction(conn, prediction_id)


def _lesson_stats(conn: sqlite3.Connection, symbol: str, horizon: str) -> tuple[int, int, float | None]:
    row = conn.execute(
        """
        SELECT COUNT(*) AS n, COALESCE(SUM(CASE WHEN hit=1 THEN 1 ELSE 0 END), 0) AS hits
        FROM predictions
        WHERE symbol=? AND horizon=? AND status IN ('scored','reviewed','retired')
          AND kind != 'decision_v1' AND hit IS NOT NULL
          AND outcome NOT IN ('UNRESOLVED','NO_DATA')
        """,
        (symbol, horizon),
    ).fetchone()
    n, hits = int(row["n"]), int(row["hits"])
    return n, hits, (hits / n if n else None)


def distill_lesson(
    conn: sqlite3.Connection,
    prediction_id: str,
    lesson: str,
    *,
    index: DocumentIndex | object | None = None,
    source: str = "ai",
    created_at: date | datetime | str | None = None,
) -> str:
    """Store a durable lesson and index it for later RAG retrieval."""
    row = _fetch(conn, prediction_id)
    if row["status"] != "reviewed":
        raise JournalError(f"only reviewed predictions can be distilled (status={row['status']})")
    text = str(lesson or "").strip()
    if not text:
        raise JournalError("lesson cannot be empty")
    lesson_id = f"prediction_lesson:{row['prediction_id']}"
    n, hits, rate = _lesson_stats(conn, row["symbol"], row["horizon"])
    now = _now(created_at)
    conn.execute(
        """
        INSERT INTO prediction_lessons
            (lesson_id, scope, subject, horizon, lesson, sample_size, hits,
             hit_rate, source, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(lesson_id) DO UPDATE SET lesson=excluded.lesson,
            sample_size=excluded.sample_size, hits=excluded.hits,
            hit_rate=excluded.hit_rate, source=excluded.source
        """,
        (lesson_id, "symbol", row["symbol"], row["horizon"], text, n, hits, rate, source, now),
    )
    conn.execute(
        "UPDATE predictions SET lesson=?, lesson_id=? WHERE id=?",
        (text, lesson_id, int(row["id"])),
    )
    conn.commit()

    document = Document(
        doc_id=lesson_id,
        kind=KIND_REPORT,
        title=f"Prediction lesson for {row['symbol']}",
        body=(
            f"Lesson from {row['symbol']} prediction {row['prediction_id']} "
            f"({row['horizon']} horizon): {text}"
        ),
        symbol=row["symbol"],
        business_date=_as_date(row["made_on"]),
        source=source,
    )
    target = index if index is not None else DocumentIndex(conn)
    if not hasattr(target, "upsert") and hasattr(target, "_conn"):
        target = DocumentIndex(target._conn)
    if not hasattr(target, "upsert"):
        raise TypeError("index must provide upsert(documents)")
    target.upsert([document])
    return lesson_id


def retire_prediction(
    conn: sqlite3.Connection,
    prediction_id: str,
    *,
    retired_at: date | datetime | str | None = None,
) -> Prediction:
    """Retire a reviewed prediction after its lesson has been persisted."""
    row = _fetch(conn, prediction_id)
    if row["status"] != "reviewed":
        raise JournalError(f"only reviewed predictions can be retired (status={row['status']})")
    if not row["lesson_id"]:
        raise JournalError("prediction cannot be retired before a lesson is distilled")
    conn.execute(
        "UPDATE predictions SET status='retired', retired_at=? WHERE id=?",
        (_now(retired_at), int(row["id"])),
    )
    conn.commit()
    return get_prediction(conn, prediction_id)


def review_queue(conn: sqlite3.Connection, *, limit: int = 100) -> list[dict[str, Any]]:
    """Rows awaiting review. Retired rows are intentionally absent."""
    rows = conn.execute(
        "SELECT * FROM predictions WHERE status='scored' ORDER BY scored_at, id LIMIT ?",
        (max(1, int(limit)),),
    ).fetchall()
    return [dict(row) for row in rows]


def journal_history(
    conn: sqlite3.Connection,
    *,
    symbol: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Return audit rows, newest first, with optional narrow filters."""
    clauses: list[str] = []
    params: list[Any] = []
    if symbol:
        clauses.append("symbol = ?")
        params.append(symbol.upper())
    if status:
        clauses.append("status = ?")
        params.append(status)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(max(1, int(limit)))
    rows = conn.execute(
        f"SELECT * FROM predictions{where} ORDER BY made_on DESC, id DESC LIMIT ?", params
    ).fetchall()
    return [dict(row) for row in rows]


__all__ = [
    "JournalError",
    "Prediction",
    "confidence_for_prediction",
    "distill_lesson",
    "get_prediction",
    "journal_history",
    "log_plan_cards",
    "log_prediction",
    "record_review",
    "record_score",
    "retire_prediction",
    "review_queue",
    "score_prediction",
]
