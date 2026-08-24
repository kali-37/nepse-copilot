"""Persist the MeroShare mirror, and compare it against the paper book.

Three responsibilities:

* **Idempotent writes.** ``ms_holdings`` upserts on (symbol, demat_hash) and
  ``ms_transactions`` on the deterministic ``txn_id``, following the
  ``ON CONFLICT … DO UPDATE`` idiom in ``storage/db.py``. Syncing the same
  payload twice leaves one row per holding, not two.
* **An honest log.** Every attempt writes an ``ms_sync_log`` row, including
  failures — a stale holdings table with no visible reason is how people end up
  trusting month-old numbers. A failed sync leaves the previous holdings alone
  rather than clearing them.
* **Real vs paper.** :func:`compare_with_paper` is a pure function over two
  dicts, so the interesting cases (agreement, quantity mismatch, symbol on one
  side only) are testable without a database or a portfolio object.

No credential is written by anything here; no table in the ``0006_meroshare``
migration has a column for one.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime

from nepse_trader.meroshare.client import MeroShareAuthError, MeroShareError, MeroShareFetchError
from nepse_trader.meroshare.credentials import redact
from nepse_trader.meroshare.models import (
    HoldingDiff,
    MeroShareHolding,
    MeroShareTransaction,
)
from nepse_trader.meroshare.privacy import demat_fingerprint, demat_last4

log = logging.getLogger("nepse_trader.meroshare.sync")


@dataclass
class SyncResult:
    """What one sync attempt did. ``error`` is always redacted."""

    ok: bool
    method: str
    holdings: int = 0
    transactions: int = 0
    error: str = ""
    ran_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _holding_rows(holdings: Iterable[MeroShareHolding]) -> list[tuple]:
    """Bind-ready holdings rows. No database work happens here."""
    stamp = _now()
    return [
        (
            h.symbol,
            demat_fingerprint(h.demat_number),
            demat_last4(h.demat_number),
            h.isin,
            h.script_desc,
            h.current_balance,
            h.previous_balance,
            h.pledged_balance,
            h.wacc,
            h.previous_closing_price,
            h.last_transaction_date.isoformat() if h.last_transaction_date else None,
            h.source,
            stamp,
        )
        for h in holdings
    ]


def _upsert_holdings(conn, holdings: Iterable[MeroShareHolding]) -> int:
    """Upsert holdings without committing, for a multi-table sync transaction."""
    rows = _holding_rows(holdings)
    if not rows:
        return 0
    conn.executemany(
        """INSERT INTO ms_holdings
           (symbol,demat_hash,demat_last4,isin,script_desc,current_balance,previous_balance,
            pledged_balance,wacc,previous_closing_price,last_transaction_date,
            source,synced_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(symbol,demat_hash) DO UPDATE SET
             demat_last4=excluded.demat_last4,
             isin=excluded.isin, script_desc=excluded.script_desc,
             current_balance=excluded.current_balance,
             previous_balance=excluded.previous_balance,
             pledged_balance=excluded.pledged_balance,
             wacc=excluded.wacc,
             previous_closing_price=excluded.previous_closing_price,
             last_transaction_date=excluded.last_transaction_date,
             source=excluded.source,
             synced_at=excluded.synced_at""",
        rows,
    )
    return len(rows)


def upsert_holdings(conn, holdings: Iterable[MeroShareHolding]) -> int:
    """Upsert holdings on (symbol, demat_hash). Returns rows written."""
    count = _upsert_holdings(conn, holdings)
    if count:
        conn.commit()
    return count


def _transaction_rows(transactions: Iterable[MeroShareTransaction]) -> list[tuple]:
    """Bind-ready transaction rows. No database work happens here."""
    stamp = _now()
    return [
        (
            t.txn_id,
            t.symbol,
            demat_fingerprint(t.demat_number),
            demat_last4(t.demat_number),
            t.transaction_date.isoformat(),
            t.transaction_type,
            t.description,
            t.quantity,
            t.price,
            t.balance_after,
            t.reference,
            t.source,
            stamp,
        )
        for t in transactions
    ]


def _upsert_transactions(conn, transactions: Iterable[MeroShareTransaction]) -> int:
    """Upsert transactions without committing, for a multi-table sync transaction."""
    rows = _transaction_rows(transactions)
    if not rows:
        return 0
    conn.executemany(
        """INSERT INTO ms_transactions
           (txn_id,symbol,demat_hash,demat_last4,transaction_date,transaction_type,description,
            quantity,price,balance_after,reference,source,synced_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(txn_id) DO UPDATE SET
             demat_hash=excluded.demat_hash, demat_last4=excluded.demat_last4,
             transaction_type=excluded.transaction_type,
             description=excluded.description,
             quantity=excluded.quantity, price=excluded.price,
             balance_after=excluded.balance_after, reference=excluded.reference,
             source=excluded.source, synced_at=excluded.synced_at""",
        rows,
    )
    return len(rows)


def upsert_transactions(conn, transactions: Iterable[MeroShareTransaction]) -> int:
    """Upsert transactions on the deterministic ``txn_id``. Returns rows written."""
    count = _upsert_transactions(conn, transactions)
    if count:
        conn.commit()
    return count


def log_sync(
    conn,
    *,
    method: str,
    status: str,
    holdings: int = 0,
    transactions: int = 0,
    error: str = "",
) -> None:
    """Write one ``ms_sync_log`` row. ``error`` is redacted before it lands."""
    conn.execute(
        """INSERT INTO ms_sync_log
           (ran_at,method,status,holdings,transactions,error)
           VALUES (?,?,?,?,?,?)""",
        (_now(), method, status, holdings, transactions, redact(error) if error else None),
    )
    conn.commit()


def sync_payload(
    conn,
    holdings: Sequence[MeroShareHolding],
    transactions: Sequence[MeroShareTransaction] = (),
    *,
    method: str = "api",
) -> SyncResult:
    """Persist an already-fetched payload, logging the attempt either way.

    Split from fetching on purpose: the CSV importer and the HTTP client both
    land here, and a test can exercise persistence with no client at all.
    """
    try:
        # A mirror is only useful when it describes one coherent remote read.
        # Neither public upsert helper is used here because each commits for
        # compatibility with callers that persist a single collection.
        with conn:
            n_holdings = _upsert_holdings(conn, holdings)
            n_txn = _upsert_transactions(conn, transactions)
    except Exception as exc:
        # SQLite errors and trigger messages may include bound data. Do not
        # stringify them into the durable audit log.
        message = f"MeroShare persistence failed: {type(exc).__name__}"
        log_sync(conn, method=method, status="error", error=message)
        log.warning("meroshare sync failed: %s", message)
        return SyncResult(ok=False, method=method, error=message)
    log_sync(
        conn, method=method, status="ok", holdings=n_holdings, transactions=n_txn
    )
    log.info("meroshare sync ok: %d holdings, %d transactions", n_holdings, n_txn)
    return SyncResult(ok=True, method=method, holdings=n_holdings, transactions=n_txn)


def _client_failure_message(exc: Exception, client: object) -> str:
    """A useful, body-free error for a client fetch failure.

    The concrete client only creates these domain exceptions from endpoint
    labels and status codes. Mapping them here keeps that useful distinction
    while preventing a duck-typed client (or an unexpected dependency error)
    from persisting arbitrary response text.
    """
    if isinstance(exc, MeroShareAuthError):
        message = "MeroShare authentication failed"
    elif isinstance(exc, MeroShareFetchError):
        message = "MeroShare read failed"
    elif isinstance(exc, MeroShareError):
        message = "MeroShare client failed"
    else:
        message = f"MeroShare fetch failed: {type(exc).__name__}"

    credentials = getattr(client, "credentials", None)
    redact_with_client = getattr(credentials, "redact", None)
    if callable(redact_with_client):
        return redact_with_client(message)
    return redact(message)


def sync_from_client(conn, client, *, with_transactions: bool = True) -> SyncResult:
    """Log in, read, persist. Any failure is logged to ``ms_sync_log`` and
    returned as data, leaving previously synced holdings untouched.

    ``client`` is duck-typed (``login``/``fetch_holdings``/``fetch_transactions``)
    so tests inject a stub without touching HTTP.
    """
    try:
        if not getattr(client, "logged_in", False):
            client.login()
        holdings = client.fetch_holdings()
        transactions = client.fetch_transactions() if with_transactions else []
    except Exception as exc:
        message = _client_failure_message(exc, client)
        log_sync(conn, method="api", status="error", error=message)
        log.warning("meroshare fetch failed: %s", message)
        return SyncResult(ok=False, method="api", error=message)
    return sync_payload(conn, holdings, transactions, method="api")


def sync_from_csv(conn, text_or_path, *, is_path: bool = False) -> SyncResult:
    """Import a CSV/pasted export and persist it, logging the attempt."""
    from nepse_trader.meroshare.importer import (
        ImportError_,
        parse_holdings_csv,
        parse_holdings_file,
    )

    try:
        holdings = (
            parse_holdings_file(text_or_path) if is_path else parse_holdings_csv(str(text_or_path))
        )
    except (ImportError_, OSError) as exc:
        # Parser diagnostics include the complete header row.  A pasted
        # export can contain account identifiers or other private columns, so
        # never persist or return that arbitrary text.  Local parser callers
        # still receive the detailed exception; the sync boundary gets a
        # stable, body-free message suitable for the audit log and API.  File
        # errors are included because a path can itself contain account data.
        # For ordinary malformed pasted CSV, expose the missing fixed field so
        # the user can repair the export without echoing arbitrary headers.
        message = "MeroShare CSV import failed: invalid holdings export"
        if isinstance(exc, ImportError_) and not is_path:
            raw = str(text_or_path).lower()
            sensitive_markers = (
                "password",
                "secret",
                "account",
                "client",
                "demat",
                "boid",
                "token",
                "username",
                "credential",
            )
            if not any(marker in raw for marker in sensitive_markers):
                detail = str(exc).lower()
                if "symbol column" in detail:
                    message = "MeroShare CSV import failed: missing symbol column"
                elif "balance column" in detail:
                    message = "MeroShare CSV import failed: missing balance column"
        log_sync(conn, method="csv", status="error", error=message)
        return SyncResult(ok=False, method="csv", error=message)
    return sync_payload(conn, holdings, method="csv")


# ---- reads -----------------------------------------------------------------


def stored_holdings(conn) -> list[MeroShareHolding]:
    """Holdings as last synced, ordered by symbol."""
    from datetime import date as _date

    rows = conn.execute("SELECT * FROM ms_holdings ORDER BY symbol").fetchall()
    out: list[MeroShareHolding] = []
    for r in rows:
        ltd = r["last_transaction_date"]
        out.append(
            MeroShareHolding(
                symbol=r["symbol"],
                # The raw BOID is intentionally not present in the mirror;
                # expose only the safe derivatives to downstream renderers.
                demat_number="",
                demat_hash=r["demat_hash"] or "",
                demat_last4=r["demat_last4"] or "",
                isin=r["isin"],
                script_desc=r["script_desc"],
                current_balance=r["current_balance"] or 0,
                previous_balance=r["previous_balance"],
                pledged_balance=r["pledged_balance"],
                wacc=r["wacc"],
                previous_closing_price=r["previous_closing_price"],
                last_transaction_date=_date.fromisoformat(ltd) if ltd else None,
                source=r["source"],
            )
        )
    return out


def stored_transactions(conn, symbol: str | None = None) -> list[MeroShareTransaction]:
    """Transactions as last synced, newest first."""
    from datetime import date as _date

    if symbol:
        rows = conn.execute(
            "SELECT * FROM ms_transactions WHERE symbol=? ORDER BY transaction_date DESC",
            (symbol.strip().upper(),),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM ms_transactions ORDER BY transaction_date DESC"
        ).fetchall()
    return [
        MeroShareTransaction(
            symbol=r["symbol"],
            demat_number="",
            demat_hash=r["demat_hash"] or "",
            demat_last4=r["demat_last4"] or "",
            transaction_date=_date.fromisoformat(r["transaction_date"]),
            transaction_type=r["transaction_type"] or "",
            description=r["description"],
            quantity=r["quantity"] or 0,
            price=r["price"],
            balance_after=r["balance_after"],
            reference=r["reference"],
            source=r["source"],
        )
        for r in rows
    ]


def sync_status(conn) -> dict:
    """Current mirror state — what the CLI and the API both render.

    Contains no credential and nothing user-identifying beyond the account
    content already in the tables.
    """
    holdings = conn.execute("SELECT COUNT(*) AS n FROM ms_holdings").fetchone()["n"]
    transactions = conn.execute("SELECT COUNT(*) AS n FROM ms_transactions").fetchone()["n"]
    last = conn.execute(
        "SELECT ran_at, method, status, holdings, transactions, error "
        "FROM ms_sync_log ORDER BY id DESC LIMIT 1"
    ).fetchone()
    last_ok = conn.execute(
        "SELECT ran_at FROM ms_sync_log WHERE status='ok' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    attempts = conn.execute("SELECT COUNT(*) AS n FROM ms_sync_log").fetchone()["n"]
    total_value = conn.execute(
        "SELECT SUM(current_balance * COALESCE(wacc,0)) AS v FROM ms_holdings"
    ).fetchone()["v"]
    return {
        "holdings": holdings,
        "transactions": transactions,
        "attempts": attempts,
        "last_attempt_at": last["ran_at"] if last else None,
        "last_method": last["method"] if last else None,
        "last_status": last["status"] if last else None,
        "last_error": last["error"] if last else None,
        "last_success_at": last_ok["ran_at"] if last_ok else None,
        "total_cost_basis": round(total_value, 2) if total_value else 0.0,
    }


def sync_history(conn, limit: int = 20) -> list[dict]:
    """Recent sync attempts, newest first — successes and failures alike."""
    rows = conn.execute(
        "SELECT ran_at, method, status, holdings, transactions, error "
        "FROM ms_sync_log ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


# ---- real vs paper ---------------------------------------------------------


def compare_with_paper(
    real: Sequence[MeroShareHolding],
    paper: Sequence[object],
) -> list[HoldingDiff]:
    """Per-symbol differences between the real account and the paper book.

    A pure function over the two sequences: ``real`` is
    :class:`MeroShareHolding` and ``paper`` is anything with ``symbol``,
    ``quantity`` and ``avg_cost`` — which is
    :class:`nepse_trader.models.Position`, but a stub works too. Symbols present
    on only one side appear with zero on the other, so nothing is silently
    dropped. Result is sorted by symbol.
    """
    real_by: dict[str, tuple[int, float, bool]] = {}
    for h in real:
        symbol = h.symbol.strip().upper()
        quantity, cost_total, has_unknown_wacc = real_by.get(symbol, (0, 0.0, False))
        quantity += h.current_balance
        if h.wacc is None:
            has_unknown_wacc = True
        else:
            cost_total += h.current_balance * h.wacc
        real_by[symbol] = (quantity, cost_total, has_unknown_wacc)
    paper_by = {}
    for p in paper:
        symbol = str(getattr(p, "symbol", "")).strip().upper()
        if symbol:
            paper_by[symbol] = p

    out: list[HoldingDiff] = []
    for symbol in sorted(set(real_by) | set(paper_by)):
        r = real_by.get(symbol)
        p = paper_by.get(symbol)
        avg_cost = getattr(p, "avg_cost", None) if p is not None else None
        real_quantity = r[0] if r else 0
        real_wacc = (
            r[1] / real_quantity
            if r and not r[2] and real_quantity
            else None
        )
        out.append(
            HoldingDiff(
                symbol=symbol,
                real_quantity=real_quantity,
                paper_quantity=int(getattr(p, "quantity", 0) or 0) if p is not None else 0,
                real_wacc=real_wacc,
                paper_avg_cost=float(avg_cost) if avg_cost is not None else None,
            )
        )
    return out


def comparison_summary(diffs: Sequence[HoldingDiff]) -> dict:
    """Counts over :func:`compare_with_paper`'s output, for a one-line report."""
    return {
        "symbols": len(diffs),
        "agreeing": sum(1 for d in diffs if d.agrees),
        "mismatched": sum(1 for d in diffs if not d.agrees and d.only_in is None),
        "only_real": sum(1 for d in diffs if d.only_in == "real"),
        "only_paper": sum(1 for d in diffs if d.only_in == "paper"),
    }
