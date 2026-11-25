from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from nepse_trader.advisor import (
    auction_advice_history,
    build_auction_advice,
    build_rashifal,
    confidence_for_prediction,
    distill_lesson,
    journal_history,
    latest_auction_advice,
    latest_dose_run,
    latest_run,
    record_review,
    record_score,
    retire_prediction,
    review_queue,
    run_history,
    save_auction_advice,
    save_rashifal,
)
from nepse_trader.advisor.confidence import band_for
from nepse_trader.advisor.outcomes import score_predictions
from nepse_trader.ai import Analyst, TokenBudget
from nepse_trader.analysis.backtest import Backtester
from nepse_trader.analysis.costs import CostEngine
from nepse_trader.analysis.strategies import STRATEGIES, build_strategy
from nepse_trader.config import Settings, get_settings, load_sources
from nepse_trader.export import EXPORT_TABLES
from nepse_trader.health import record_snapshot, snapshot_history, system_health
from nepse_trader.ingest.fundamentals import MeroLaganiFundamentalsClient
from nepse_trader.meroshare import (
    MeroShareClient,
    MeroShareDisabledError,
    compare_with_paper,
    comparison_summary,
    keyring_available,
    resolve_credentials,
    stored_holdings,
    sync_from_client,
    sync_from_csv,
    sync_history,
    sync_status,
)
from nepse_trader.models import CorporateAction, CorporateActionType, SourceName
from nepse_trader.pipeline import DailyPipeline
from nepse_trader.rag import DocumentIndex, build_evidence, build_retriever
from nepse_trader.rag.corpus import KIND_NEWS
from nepse_trader.storage import Storage
from nepse_trader.web.jobs import HANDLERS, JobBusy, registry

log = logging.getLogger("nepse_trader.web")

# ---------------------------------------------------------------------------
# App lifespan — single Storage instance for all requests
# ---------------------------------------------------------------------------
_state: dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    if "storage" not in _state:
        settings = get_settings()
        storage = Storage(settings.db_path)
        _state["storage"] = storage
        _state["settings"] = settings
        log.info("web API started — db_path=%s", settings.db_path)
    yield
    if "storage" in _state:
        _state["storage"].close()
        _state.clear()


app = FastAPI(
    title="NEPSE Trader API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _storage() -> Storage:
    return _state["storage"]


def _settings() -> Settings:
    """Settings for the current request.

    Read out of ``_state`` rather than calling ``get_settings()`` directly so a
    test (or a future multi-tenant caller) can inject a ``Settings`` built with
    ``_env_file=None`` alongside its temp-DB ``Storage``, exactly the way
    ``_state["storage"]`` is already overridden. Falls back to the cached global
    when nothing was injected, which is the normal server path.
    """
    settings = _state.get("settings")
    if settings is None:
        settings = get_settings()
        _state["settings"] = settings
    return settings


def _parse_date(value: str | None) -> date | None:
    if value is None:
        return None
    return date.fromisoformat(value)


def _latest_market_date() -> date:
    """The date the dashboard should show when the caller did not pick one.

    ``date.today()`` is the wrong default: NEPSE is shut on Friday and Saturday
    and on every public holiday, so on those days a "today" query returns an
    empty market and the UI looks broken rather than closed.
    """
    storage = _storage()
    return storage.latest_reconciled_date() or storage.latest_price_date() or date.today()


def _pipeline() -> DailyPipeline:
    return DailyPipeline(settings=_settings(), storage=_storage(), clients=[])


def _symbol_filter(symbol: str | None) -> str | None:
    """Normalise an optional ``?symbol=`` to upper case, or None when absent."""
    cleaned = (symbol or "").strip().upper()
    return cleaned or None


def _confidence_response(value: Any, *, band: Any = "", basis: Any = "") -> dict[str, Any]:
    """Make persisted and in-memory confidence values share one API shape.

    Fresh advisor runs carry ``Confidence.as_dict()``. SQLite rows intentionally
    store the scalar, band, and basis in separate columns, so historical runs
    need this small adapter before the frontend can render them safely.
    """
    if hasattr(value, "as_dict"):
        value = value.as_dict()
    if isinstance(value, dict):
        score = value.get("value", 0.0)
        band = value.get("band", band)
        basis = value.get("basis", basis)
        label = value.get("label")
        sample_size = value.get("sample_size", 0)
    else:
        score = value
        label = None
        sample_size = 0
    try:
        score = min(1.0, max(0.0, float(score or 0.0)))
    except (TypeError, ValueError):
        score = 0.0
    derived_band, derived_label = band_for(score)
    return {
        "value": score,
        "band": str(band or derived_band),
        "label": str(label or derived_label),
        "basis": str(basis or "persisted advisor confidence"),
        "sample_size": int(sample_size or 0),
    }


def _symbols_response(value: Any) -> list[str]:
    """Decode the compact comma-separated form used by the ``doses`` table."""
    if isinstance(value, str):
        return [part.strip().upper() for part in value.split(",") if part.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(part).strip().upper() for part in value if str(part).strip()]
    return []


def _plan_card_response(card: Any) -> dict[str, Any]:
    """Adapt a persisted ``advice_cards`` row to the public PlanCard contract."""
    out = dict(card)
    if not out.get("targets"):
        out["targets"] = [
            target for target in (out.get("target_1"), out.get("target_2")) if target is not None
        ]
    out["confidence"] = _confidence_response(
        out.get("confidence"),
        band=out.get("confidence_band"),
        basis=out.get("confidence_basis"),
    )
    return out


def _dose_response(dose: Any) -> dict[str, Any]:
    """Adapt a compact persisted dose row to the display-facing response shape."""
    out = dict(dose)
    out["symbols"] = _symbols_response(out.get("symbols"))
    out["cards"] = [_plan_card_response(card) for card in out.get("cards") or []]
    out["confidence"] = _confidence_response(
        out.get("confidence"),
        band=out.get("confidence_band"),
        basis=out.get("confidence_basis"),
    )
    return out


def _dose_run_response(dose_run: Any) -> dict[str, Any]:
    """Return a stable dose response for both a just-built and stored run."""
    out = dict(dose_run)
    doses = [_dose_response(dose) for dose in out.get("doses") or []]
    out["doses"] = doses
    out["confidence"] = _confidence_response(
        out.get("confidence"),
        band=out.get("confidence_band"),
    )
    out["banner"] = out.get("banner") or ""
    out.setdefault("expected_gross_pnl", sum(float(d.get("expected_gross_pnl") or 0) for d in doses))
    return out


def _attach_dose_cards(conn, dose_run: dict[str, Any]) -> dict[str, Any]:
    """Attach persisted advice cards to their one dose for historical reads."""
    run_id = dose_run.get("run_id")
    if not run_id:
        return dose_run
    cards = [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM advice_cards WHERE run_id=? ORDER BY conviction DESC, symbol",
            (run_id,),
        ).fetchall()
    ]
    doses = dose_run.get("doses") or []
    lower = 0
    for dose in doses:
        limit = int(dose.get("horizon_days") or 0)
        allowed_symbols = set(_symbols_response(dose.get("symbols")))
        selected = [
            _plan_card_response(card)
            for card in cards
            if (
                lower < int(card.get("horizon_days") or 0) <= limit
                and str(card.get("symbol") or "").strip().upper() in allowed_symbols
            )
        ]
        dose["cards"] = selected
        lower = limit
    return dose_run


def _advisor_run_response(run: Any) -> dict[str, Any]:
    """Normalize an advisor run loaded from SQLite for the React contract."""
    out = dict(run)
    out["cards"] = [_plan_card_response(card) for card in out.get("cards") or []]
    if out.get("doses"):
        out["doses"] = _attach_dose_cards(_storage()._conn, _dose_run_response(out["doses"]))
    else:
        out["doses"] = None
    out["degraded"] = bool(out.get("banner"))
    # Stored as NULL when the run was not degraded; the contract says string.
    out["banner"] = out.get("banner") or ""
    return out


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/health/report")
def health_report(record: bool = Query(False)):
    """The full multi-check system report.

    ``/api/health`` stays a bare liveness probe so a load balancer polling it
    cannot be made expensive; this is the diagnostic view. ``?record=true`` is
    the only way it writes, so ordinary polling never grows the database.
    """
    storage = _storage()
    report = system_health(storage, _settings())
    if record:
        report["snapshot_id"] = record_snapshot(storage._conn, report)
    return report


@app.get("/api/health/history")
def health_history(limit: int = Query(30, ge=1, le=365)):
    """Recorded snapshots, newest first — the trend behind the current report."""
    return snapshot_history(_storage()._conn, limit=limit)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
@app.get("/api/dashboard")
def dashboard():
    return _storage().db_stats()


@app.get("/api/market-breadth")
def market_breadth(business_date: str | None = Query(None)):
    bd = _parse_date(business_date) or _latest_market_date()
    return _pipeline().market_breadth(bd)


@app.get("/api/movers")
def movers(business_date: str | None = Query(None), top: int = Query(5)):
    bd = _parse_date(business_date) or _latest_market_date()
    gainers, losers = _pipeline().top_movers(bd, top=top)
    return {"gainers": gainers, "losers": losers, "business_date": bd.isoformat()}


# ---------------------------------------------------------------------------
# Symbols
# ---------------------------------------------------------------------------
@app.get("/api/symbols")
def list_symbols():
    return _storage().symbols()


@app.get("/api/symbols/{symbol}/prices")
def symbol_prices(
    symbol: str,
    start: str | None = Query(None),
    end: str | None = Query(None),
    limit: int = Query(500),
):
    storage = _storage()
    prices = storage.reconciled_history(symbol.upper())
    if start:
        sd = date.fromisoformat(start)
        prices = [p for p in prices if p.business_date >= sd]
    if end:
        ed = date.fromisoformat(end)
        prices = [p for p in prices if p.business_date <= ed]
    if limit:
        prices = prices[-limit:]
    return [
        {
            "business_date": p.business_date.isoformat(),
            "open": p.open,
            "high": p.high,
            "low": p.low,
            "close": p.close,
            "volume": p.volume,
            "turnover": p.turnover,
            "confidence": p.confidence,
        }
        for p in prices
    ]


@app.get("/api/symbols/{symbol}/signals")
def symbol_signals(
    symbol: str,
    strategy: str = Query("sma_cross"),
):
    pipe = _pipeline()
    try:
        sigs = pipe.signals_for(symbol.upper(), strategy)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return [
        {
            "business_date": s.business_date.isoformat(),
            "strategy": s.strategy,
            "action": s.action.value,
            "strength": s.strength,
            "reason": s.reason,
            "price": s.price,
        }
        for s in sigs
    ]


@app.get("/api/symbols/{symbol}/quant")
def symbol_quant(symbol: str):
    pipe = _pipeline()
    rows = pipe.quant_stats([symbol.upper()])
    if not rows:
        raise HTTPException(404, f"No quant data for {symbol.upper()}")
    return rows[0]


@app.get("/api/symbols/{symbol}/fundamentals")
def symbol_fundamentals(symbol: str):
    cached = _storage().fundamentals().get(symbol.upper())
    if cached is not None:
        return cached.model_dump(mode="json")
    if not _settings().online:
        raise HTTPException(404, f"No stored fundamentals for {symbol.upper()}; download them in Operations when online.")
    from nepse_trader.ingest.base import BaseClient

    transport = BaseClient(_settings(), cache_raw=False)
    client = MeroLaganiFundamentalsClient(client=transport)
    try:
        data = client.fetch_fundamentals(symbol.upper())
    except Exception as e:
        raise HTTPException(502, f"Fundamentals fetch failed: {e}") from e
    finally:
        transport.close()
    if data is None or (data.market_price is None and data.eps is None):
        raise HTTPException(404, f"No fundamentals for {symbol.upper()}")
    _storage().upsert_fundamental(data)
    return {
        "company_name": data.company_name,
        "sector": data.sector,
        "market_price": data.market_price,
        "eps": data.eps,
        "pe_ratio": data.pe_ratio,
        "book_value": data.book_value,
        "pbv": data.pbv,
        "dividend_pct": data.dividend_pct,
        "market_cap": data.market_cap,
        "shares_outstanding": data.shares_outstanding,
        "high_52w": data.high_52w,
        "low_52w": data.low_52w,
        "avg_volume_30d": data.avg_volume_30d,
    }


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------
@app.get("/api/portfolio")
def portfolio(cash: float = Query(100_000.0)):
    pipe = _pipeline()
    pf = pipe.replay_portfolio(cash)
    quotes = {}
    for position in pf.holdings():
        history = pipe.storage.reconciled_history(position.symbol)
        closes = [row.close for row in history if row.close is not None]
        if closes:
            quotes[position.symbol] = closes[-1]
    return pf.to_dict(quotes)


# ---------------------------------------------------------------------------
# Backtest
# ---------------------------------------------------------------------------
@app.get("/api/backtest/screen")
def backtest_screen(
    strategies: str = Query("all", description="Comma list or 'all'"),
    cash: float = Query(100_000.0),
    min_bars: int = Query(60),
    rank_by: str = Query("sharpe"),
    top: int = Query(30),
    max_pe: float | None = Query(None, gt=0),
    max_pbv: float | None = Query(None, gt=0),
    min_eps: float | None = Query(None),
    sector: str | None = Query(None),
):
    pipe = _pipeline()
    strat_list = (
        list(STRATEGIES)
        if strategies.strip().lower() == "all"
        else [s.strip() for s in strategies.split(",") if s.strip()]
    )
    rows = pipe.screen_strategies(
        strategy_names=strat_list,
        cash=cash,
        min_bars=min_bars,
        rank_by=rank_by,
        max_pe=max_pe, max_pbv=max_pbv, min_eps=min_eps, sector=sector,
    )
    return [r.as_dict() for r in rows[:top]]


@app.get("/api/backtest/run")
def backtest_run(
    symbol: str,
    strategy: str = Query("sma_cross"),
    cash: float = Query(100_000.0),
    fraction: float = Query(1.0),
    fast: int | None = Query(None),
    slow: int | None = Query(None),
    period: int | None = Query(None),
    signal_period: int | None = Query(None, alias="signal"),
):
    pipe = _pipeline()
    bars = pipe.reconciled_bars(symbol.upper())
    if len(bars) < 2:
        raise HTTPException(400, f"Not enough history for {symbol.upper()}")
    kwargs: dict[str, int] = {}
    if fast is not None:
        kwargs["fast"] = fast
    if slow is not None:
        kwargs["slow"] = slow
    if period is not None:
        kwargs["period"] = period
    if signal_period is not None:
        kwargs["signal"] = signal_period
    strat = build_strategy(strategy, **kwargs)
    bt = Backtester(cost_engine=CostEngine(), initial_cash=cash, position_fraction=fraction)
    result = bt.run(strat, bars)
    return {
        "summary": result.summary(),
        "equity_curve": [(d.isoformat(), e) for d, e in result.equity_curve],
        "trades": result.trades,
    }


# ---------------------------------------------------------------------------
# Ingest trigger
# ---------------------------------------------------------------------------
@app.post("/api/ingest")
def trigger_ingest(
    business_date: str | None = Query(None),
    all_sources: bool = Query(True),
    async_: bool = Query(False, alias="async"),
    force: bool = Query(False),
):
    import asyncio

    bd = _parse_date(business_date)
    pipe = DailyPipeline(settings=_settings(), storage=_storage(), include_all_sources=all_sources)
    if async_:
        rep = asyncio.run(pipe.async_ingest(bd, force=force))
    else:
        rep = pipe.ingest(bd, force=force)
    return rep.as_dict()


# ---------------------------------------------------------------------------
# RAG — search the local document corpus
# ---------------------------------------------------------------------------
@app.get("/api/rag/search")
def rag_search(
    q: str = Query("", description="Free text. Empty falls back to most recent."),
    limit: int = Query(8, ge=1, le=50),
    symbol: str | None = Query(None),
    kind: str | None = Query(None, description="Comma list of document kinds"),
):
    """Ranked documents for *q*, plus the packed evidence block.

    Always the local index — never the web leg. A search endpoint that could
    reach the network would make an offline install feel broken and would spend
    the RAG web budget on idle typing in the UI; :func:`build_retriever` is
    called with ``online=False`` for exactly that reason.
    """
    index = DocumentIndex(_storage()._conn)
    retriever = build_retriever(index, _settings(), online=False)
    symbols = [s] if (s := _symbol_filter(symbol)) else None
    kinds = [k.strip() for k in kind.split(",") if k.strip()] if kind else None

    hits = retriever.retrieve(q, limit=limit, symbols=symbols, kinds=kinds)
    pack = build_evidence(
        hits,
        query=q,
        max_documents=limit,
        max_chars=_settings().rag_max_evidence_chars,
    )
    return {
        "query": q,
        "uses_fts": index.uses_fts,
        "count": len(hits),
        "hits": [
            {
                "doc_id": h.document.doc_id,
                "kind": h.document.kind,
                "symbol": h.document.symbol,
                "title": h.document.title,
                "body": h.document.body,
                "url": h.document.url,
                "source": h.document.source,
                "business_date": (
                    h.document.business_date.isoformat() if h.document.business_date else None
                ),
                "score": h.score,
                "matched_terms": h.matched_terms,
            }
            for h in hits
        ],
        "evidence": {
            "markers": pack.markers,
            "kinds": pack.kinds,
            "symbols": pack.symbols,
            "truncated": pack.truncated,
            "considered": pack.considered,
            "citations": pack.citation_map(),
            "rendered": pack.render(),
        },
    }


@app.get("/api/rag/stats")
def rag_stats():
    """Corpus size per document kind, and whether bm25 ranking is available."""
    index = DocumentIndex(_storage()._conn)
    return {
        "total": index.count(),
        "per_kind": index.kinds(),
        "uses_fts": index.uses_fts,
    }


# ---------------------------------------------------------------------------
# AI budget
# ---------------------------------------------------------------------------
@app.get("/api/ai/budget")
def ai_budget():
    """Today's LLM spend against the caps, plus the recent ledger rows.

    Read-only: constructing a :class:`TokenBudget` writes nothing, so polling
    this from the UI cannot itself consume budget.
    """
    budget = TokenBudget(_storage()._conn, _settings())
    summary = budget.summary().as_dict()
    return {**summary, "history": budget.history(limit=20)}


# ---------------------------------------------------------------------------
# News — the ingested slice of the document corpus
# ---------------------------------------------------------------------------
@app.get("/api/news")
def news(
    limit: int = Query(20, ge=1, le=200),
    symbol: str | None = Query(None),
):
    """Recently ingested news documents, newest first.

    Served off :class:`DocumentIndex.recent` rather than a fresh fetch: news is
    ingested by ``ingest news``, and having the API scrape on read would make a
    page load depend on a third-party site being up.
    """
    index = DocumentIndex(_storage()._conn)
    symbols = [s] if (s := _symbol_filter(symbol)) else None
    docs = index.recent(limit=limit, symbols=symbols, kinds=[KIND_NEWS])
    return [
        {
            "doc_id": d.doc_id,
            "symbol": d.symbol,
            "title": d.title,
            "body": d.body,
            "url": d.url,
            "source": d.source,
            "business_date": d.business_date.isoformat() if d.business_date else None,
            "fetched_at": d.fetched_at.isoformat() if d.fetched_at else None,
        }
        for d in docs
    ]


# ---------------------------------------------------------------------------
# Settings — the watchlist
# ---------------------------------------------------------------------------
_WATCHLIST_KEY = "watchlist"
_MEROSHARE_ENABLED_KEY = "meroshare_enabled"


def _ensure_app_settings(conn) -> None:
    """Assert the migrated settings table exists.

    ``app_settings`` is created by migration ``0011_app_settings``.  Keeping
    this small guard preserves the helper used by older callers/tests without
    silently creating an unversioned schema at request time.
    """
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='app_settings'"
    ).fetchone()
    if row is None:
        raise RuntimeError("database is missing migration 0011_app_settings")


def _stored_bool_setting(conn, key: str) -> tuple[bool | None, str | None]:
    """Read a boolean override from ``app_settings`` safely."""
    _ensure_app_settings(conn)
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
    if not isinstance(parsed, bool):
        return None, None
    updated = row["updated_at"] if hasattr(row, "keys") else row[1]
    return parsed, updated


def _meroshare_enabled() -> tuple[bool, str, str | None]:
    """Return effective MeroShare toggle, source, and DB update time."""
    stored, updated_at = _stored_bool_setting(_storage()._conn, _MEROSHARE_ENABLED_KEY)
    if stored is not None:
        return stored, "database", updated_at
    return bool(_settings().meroshare_enabled), "env", None


def _meroshare_settings() -> Settings:
    """Copy settings with the persisted toggle applied for this request."""
    enabled, _, _ = _meroshare_enabled()
    return _settings().model_copy(update={"meroshare_enabled": enabled})


def _stored_watchlist(conn) -> tuple[list[str], str | None]:
    """The persisted watchlist and when it was written, or ``([], None)``.

    Returns the empty list for a malformed stored value rather than raising: a
    hand-edited row should degrade to "no override", not break the settings page.
    """
    _ensure_app_settings(conn)
    row = conn.execute(
        "SELECT value, updated_at FROM app_settings WHERE key = ?", (_WATCHLIST_KEY,)
    ).fetchone()
    if row is None:
        return ([], None)
    try:
        parsed = json.loads(row["value"])
    except ValueError:
        log.warning("stored watchlist is not valid JSON; ignoring it")
        return ([], None)
    if not isinstance(parsed, list):
        return ([], None)
    return ([str(s) for s in parsed], row["updated_at"])


class WatchlistUpdate(BaseModel):
    """A replacement watchlist. Symbols are upper-cased and de-duplicated."""

    symbols: list[str] = Field(..., max_length=200)


@app.get("/api/settings/watchlist")
def get_watchlist():
    """The effective watchlist and where it came from.

    Two layers: whatever ``PUT`` last stored, else ``NEPSE_WATCHLIST`` from the
    environment. ``source`` says which, because "my watchlist is empty" and "my
    .env is winning" look identical otherwise.
    """
    stored, updated_at = _stored_watchlist(_storage()._conn)
    env_watchlist = list(_settings().watchlist)
    return {
        "symbols": stored or env_watchlist,
        "source": "database" if stored else "env",
        "env_watchlist": env_watchlist,
        "updated_at": updated_at,
        "max_symbols": _settings().advisor_max_symbols,
    }


@app.put("/api/settings/watchlist")
def put_watchlist(body: WatchlistUpdate):
    """Persist a new watchlist to ``app_settings``.

    Written to the DB, not to ``Settings``: ``get_settings()`` is ``lru_cache``d
    over env/.env, so mutating it would survive exactly until the process
    restarted. An empty list is a valid write — it clears the override and hands
    the watchlist back to the environment.
    """
    symbols: list[str] = []
    for raw in body.symbols:
        sym = str(raw).strip().upper()
        if sym and sym not in symbols:
            symbols.append(sym)

    conn = _storage()._conn
    _ensure_app_settings(conn)
    conn.execute(
        """INSERT INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)
           ON CONFLICT(key) DO UPDATE SET
             value=excluded.value, updated_at=excluded.updated_at""",
        (_WATCHLIST_KEY, json.dumps(symbols), datetime.now(UTC).isoformat()),
    )
    conn.commit()
    return get_watchlist()


# ---------------------------------------------------------------------------
# Advisor — the daily prescription
# ---------------------------------------------------------------------------
class AdvisorRunRequest(BaseModel):
    """One advisor run. ``symbols`` empty means "resolve from the watchlist"."""

    mode: Literal["normal", "ai"] = "normal"
    horizon: Literal["day", "week", "month", "year"] = "week"
    online: bool = False
    symbols: list[str] | None = None
    equity: float = Field(100_000.0, gt=0)


class JournalScoreRequest(BaseModel):
    """Optional bounds for scoring one or many open predictions."""

    prediction_id: str | None = None
    as_of: date | None = None
    limit: int = Field(100, ge=1, le=500)


class JournalReviewRequest(BaseModel):
    """Review text; ``text`` is accepted as a client-friendly alias."""

    prediction_id: str | None = None
    review: str | None = Field(None, max_length=20_000)
    text: str | None = Field(None, max_length=20_000)


class JournalDistillRequest(BaseModel):
    """Durable lesson text and its provenance."""

    prediction_id: str | None = None
    lesson: str | None = Field(None, max_length=20_000)
    text: str | None = Field(None, max_length=20_000)
    source: str = Field("api", min_length=1, max_length=64)


class AuctionAdviceRequest(BaseModel):
    """Inputs for fee-aware, manual-only auction guidance."""

    symbol: str = Field(..., min_length=1, max_length=32)
    auction_date: date | None = None
    units: int = Field(..., gt=0)
    min_bid_price: float = Field(..., gt=0)
    market_price: float = Field(..., gt=0)
    expected_exit_price: float | None = Field(None, gt=0)
    horizon_days: int = Field(10, ge=0, le=5_000)
    quantity: int | None = Field(None, gt=0)
    confidence: float | None = Field(None, ge=0, le=1)
    edge_buffer_pct: float = Field(0.10, ge=0, lt=1)


class MeroShareToggleRequest(BaseModel):
    """Persist or clear the local MeroShare integration override."""

    enabled: bool | None = None


def _advisor_symbols(requested: list[str] | None) -> list[str]:
    """Which symbols a run covers: request → stored watchlist → env → whole DB."""
    if requested:
        return [s.strip().upper() for s in requested if s.strip()]
    stored, _ = _stored_watchlist(_storage()._conn)
    return stored or list(_settings().watchlist) or _storage().symbols()


def _evidence_builder(online: bool):
    """A ``symbol -> rendered evidence`` callable for an AI-mode run.

    Built once per run so the index and retriever are constructed once rather
    than per symbol. An empty symbol means "the whole market", which is what
    :func:`build_rashifal` passes when it asks for the weekly thesis.
    """
    settings = _settings()
    index = DocumentIndex(_storage()._conn)
    retriever = build_retriever(index, settings, online=online)

    def evidence_for(symbol: str) -> str:
        query = symbol or "market breadth regime"
        hits = retriever.retrieve(
            query,
            limit=settings.rag_max_documents,
            symbols=[symbol] if symbol else None,
        )
        return build_evidence(
            hits,
            query=query,
            max_documents=settings.rag_max_documents,
            max_chars=settings.rag_max_evidence_chars,
        ).render()

    return evidence_for


@app.post("/api/advisor/run")
def advisor_run(body: AdvisorRunRequest):
    """Build a rashifal, persist it, and return it.

    ``mode="ai"`` attaches an :class:`Analyst`; when no provider is configured or
    the budget is spent the run still succeeds and carries a ``banner`` — that is
    the advisor's degradation contract, and surfacing it as a 200 with a banner
    rather than a 5xx is what lets the UI show the numbers anyway.
    """
    pipe = _pipeline()
    symbols = _advisor_symbols(body.symbols)
    if not symbols:
        raise HTTPException(400, "No symbols to advise on — the database is empty")

    run_date = _storage().latest_reconciled_date() or date.today()
    breadth = pipe.market_breadth(run_date)
    positions = {
        p.symbol: p.quantity for p in pipe.replay_portfolio(body.equity).holdings()
    }

    analyst = None
    evidence_for = None
    if body.mode == "ai":
        analyst = Analyst(_storage()._conn, _settings(), online=body.online)
        evidence_for = _evidence_builder(body.online)

    result = build_rashifal(
        symbols=symbols,
        bars_for=pipe.reconciled_bars,
        signals_for=lambda sym: [signal for name in STRATEGIES for signal in pipe.signals_for(sym, name)[-1:] if signal.business_date == run_date],
        equity=body.equity,
        run_date=run_date,
        mode=body.mode,
        horizon=body.horizon,
        online=body.online,
        breadth=breadth,
        positions=positions,
        analyst=analyst,
        evidence_for=evidence_for,
        cost_engine=pipe.cost_engine,
        confidence_for=lambda **context: confidence_for_prediction(
            _storage()._conn,
            symbol=str(context.get("symbol") or ""),
            action=str(context.get("action") or ""),
            horizon=str(context.get("horizon") or ""),
            horizon_days=int(context.get("horizon_days") or 0),
        ),
        max_symbols=_settings().advisor_max_symbols,
    )
    save_rashifal(_storage()._conn, result)
    return result.as_dict()


@app.get("/api/advisor/latest")
def advisor_latest():
    """The most recent persisted run with its cards, or 404 if none exists."""
    run = latest_run(_storage()._conn)
    if run is None:
        raise HTTPException(404, "The advisor has not run yet")
    return _advisor_run_response(run)


@app.get("/api/advisor/history")
def advisor_history(limit: int = Query(30, ge=1, le=200)):
    """Recent runs, newest first, without their cards."""
    return run_history(_storage()._conn, limit=limit)


@app.get("/api/advisor/doses/latest")
def advisor_doses_latest():
    """The latest four-horizon dose run, with disjoint card assignments."""
    dose_run = latest_dose_run(_storage()._conn)
    if dose_run is None:
        raise HTTPException(404, "The advisor has not generated doses yet")
    return _attach_dose_cards(_storage()._conn, _dose_run_response(dose_run))


@app.get("/api/journal/history")
def journal_history_endpoint(
    symbol: str | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    """Prediction audit rows, newest first, optionally filtered for review."""
    return journal_history(
        _storage()._conn,
        symbol=_symbol_filter(symbol),
        status=(status or "").strip().lower() or None,
        limit=limit,
    )


def _journal_error(exc: ValueError) -> HTTPException:
    """Translate lifecycle/domain errors without leaking internals."""
    status = 404 if "not found" in str(exc).lower() else 409
    return HTTPException(status, str(exc))


@app.post("/api/journal/score")
def journal_score_endpoint(body: JournalScoreRequest):
    """Score one or a bounded batch of open calls against local price bars."""
    conn = _storage()._conn
    if body.prediction_id:
        rows = conn.execute(
            """SELECT * FROM predictions
               WHERE (prediction_id=? OR CAST(id AS TEXT)=?) AND status='open' AND kind!='decision_v1'""",
            (body.prediction_id, body.prediction_id),
        ).fetchall()
        if not rows:
            raise HTTPException(404, "No open advisor prediction matched that id. Dashboard recommendations are evaluated by Refresh today.")
    else:
        rows = conn.execute(
            "SELECT * FROM predictions WHERE status='open' AND kind!='decision_v1' ORDER BY made_on, id LIMIT ?",
            (body.limit,),
        ).fetchall()

    pipe = _pipeline()
    results = score_predictions(
        list(rows),
        pipe.reconciled_bars,
        cost_engine=pipe.cost_engine,
        as_of=body.as_of,
    )
    for result in results:
        record_score(conn, result.prediction_id, result)
    return [result.as_dict() for result in results]


@app.post("/api/journal/{prediction_id}/score")
def journal_score_one_endpoint(
    prediction_id: str,
    as_of: date | None = Query(None),
):
    """Path-oriented scoring alias for clients operating on one row."""
    return journal_score_endpoint(JournalScoreRequest(prediction_id=prediction_id, as_of=as_of))


@app.post("/api/journal/{prediction_id}/review")
def journal_review_endpoint(prediction_id: str, body: JournalReviewRequest):
    """Attach a human or AI review to a scored prediction."""
    text = (body.review or body.text or "").strip()
    if not text:
        raise HTTPException(422, "review cannot be empty")
    try:
        return record_review(_storage()._conn, prediction_id, text).as_dict()
    except ValueError as exc:
        raise _journal_error(exc) from exc


@app.post("/api/journal/{prediction_id}/distill")
def journal_distill_endpoint(prediction_id: str, body: JournalDistillRequest):
    """Distill a reviewed prediction into the durable local RAG corpus."""
    text = (body.lesson or body.text or "").strip()
    if not text:
        raise HTTPException(422, "lesson cannot be empty")
    try:
        lesson_id = distill_lesson(
            _storage()._conn,
            prediction_id,
            text,
            source=body.source,
        )
    except ValueError as exc:
        raise _journal_error(exc) from exc
    return {"prediction_id": prediction_id, "lesson_id": lesson_id}


@app.post("/api/journal/{prediction_id}/retire")
def journal_retire_endpoint(prediction_id: str):
    """Retire a reviewed row only after its lesson has been distilled."""
    try:
        return retire_prediction(_storage()._conn, prediction_id).as_dict()
    except ValueError as exc:
        raise _journal_error(exc) from exc


@app.get("/api/journal/review-queue")
def journal_review_queue_endpoint(limit: int = Query(100, ge=1, le=500)):
    """Bounded scored rows awaiting the review step."""
    return review_queue(_storage()._conn, limit=limit)


@app.get("/api/journal/calibration")
def journal_calibration_endpoint(
    symbol: str | None = Query(None),
    horizon: Literal["day", "week", "month", "year"] | None = Query(None),
    limit: int = Query(200, ge=1, le=500),
):
    """Materialised expected-versus-realised accuracy, bounded and local."""
    clauses: list[str] = []
    params: list[Any] = []
    if normalized := _symbol_filter(symbol):
        clauses.append("subject=?")
        params.append(normalized)
    if horizon:
        clauses.append("horizon=?")
        params.append(horizon)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    params.append(limit)
    rows = _storage()._conn.execute(
        "SELECT * FROM calibration" + where + " ORDER BY subject, horizon LIMIT ?",
        params,
    ).fetchall()
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Auction — fee-aware advice only; no bid placement is reachable from the API
# ---------------------------------------------------------------------------
@app.post("/api/auction/advice")
def auction_advice_endpoint(body: AuctionAdviceRequest):
    """Calculate and persist a manual auction bid ceiling."""
    try:
        advice = build_auction_advice(
            body.symbol,
            auction_date=body.auction_date or date.today(),
            units=body.units,
            min_bid_price=body.min_bid_price,
            market_price=body.market_price,
            expected_exit_price=body.expected_exit_price,
            horizon_days=body.horizon_days,
            quantity=body.quantity,
            confidence=body.confidence,
            edge_buffer_pct=body.edge_buffer_pct,
            cost_engine=_pipeline().cost_engine,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    save_auction_advice(_storage()._conn, advice)
    _storage()._conn.commit()
    return {**advice.as_dict(), "manual_only": True, "bid_submitted": False}


@app.get("/api/auction/advice")
@app.get("/api/auction/history")
def auction_advice_history_endpoint(
    symbol: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """Saved advice rows, newest first; this endpoint cannot submit bids."""
    return auction_advice_history(
        _storage()._conn,
        symbol=_symbol_filter(symbol),
        limit=limit,
    )


@app.get("/api/auction/latest")
def auction_latest_endpoint(symbol: str | None = Query(None)):
    """Latest saved auction advice, optionally for one symbol."""
    advice = latest_auction_advice(_storage()._conn, symbol=_symbol_filter(symbol))
    if advice is None:
        raise HTTPException(404, "No auction advice has been saved yet")
    return advice


# ---------------------------------------------------------------------------
# MeroShare — READ-ONLY mirror of the user's own account
# ---------------------------------------------------------------------------
# Nothing here places an order or applies for an IPO, and no response, log line
# or error message carries a credential. `/status` reports whether credentials
# are *configured* (booleans and a field-name list) and never their values; the
# sync endpoints surface `SyncResult.error`, which the sync layer has already put
# through `redact()`.
@app.get("/api/settings/meroshare")
def get_meroshare_setting():
    """Effective integration toggle with its DB-or-environment provenance."""
    enabled, source, updated_at = _meroshare_enabled()
    return {
        "enabled": enabled,
        "source": source,
        "env_enabled": bool(_settings().meroshare_enabled),
        "updated_at": updated_at,
    }


@app.put("/api/settings/meroshare")
def put_meroshare_setting(body: MeroShareToggleRequest):
    """Persist a local toggle, or clear it with ``{"enabled": null}``."""
    conn = _storage()._conn
    _ensure_app_settings(conn)
    if body.enabled is None:
        conn.execute("DELETE FROM app_settings WHERE key=?", (_MEROSHARE_ENABLED_KEY,))
    else:
        conn.execute(
            """INSERT INTO app_settings (key, value, updated_at) VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET
                 value=excluded.value, updated_at=excluded.updated_at""",
            (
                _MEROSHARE_ENABLED_KEY,
                json.dumps(body.enabled),
                datetime.now(UTC).isoformat(),
            ),
        )
    conn.commit()
    return get_meroshare_setting()


@app.get("/api/meroshare/status")
def meroshare_status():
    """Mirror state plus whether credentials are configured — never their values."""
    effective = _meroshare_settings()
    enabled, enabled_source, enabled_updated_at = _meroshare_enabled()
    creds = resolve_credentials(effective).credentials
    keyring_ok, keyring_reason = keyring_available()
    return {
        **sync_status(_storage()._conn),
        "enabled": enabled,
        "enabled_source": enabled_source,
        "enabled_updated_at": enabled_updated_at,
        "credentials_configured": creds.complete,
        "credentials_missing": creds.missing(),
        "credential_source": creds.source,
        "keyring_available": keyring_ok,
        "keyring_note": keyring_reason,
    }


@app.post("/api/meroshare/sync")
def meroshare_sync(with_transactions: bool = Query(True)):
    """Log in, read holdings (and history), persist. Read-only at the portal.

    A failed sync is a 200 with ``ok: false``: :func:`sync_from_client` logs the
    attempt and leaves the previous holdings alone, and the caller needs the
    redacted reason more than it needs an exception. Only a disabled integration
    is a 4xx, since that is a configuration problem rather than a run failure.
    """
    try:
        client = MeroShareClient(_meroshare_settings())
    except MeroShareDisabledError as exc:
        raise HTTPException(400, str(exc)) from None
    try:
        result = sync_from_client(
            _storage()._conn, client, with_transactions=with_transactions
        )
    finally:
        client.close()
    return {
        "ok": result.ok,
        "method": result.method,
        "holdings": result.holdings,
        "transactions": result.transactions,
        "error": result.error,
        "ran_at": result.ran_at,
    }


class MeroShareImportRequest(BaseModel):
    """A pasted CSV/holdings export. No credential is involved in this path."""

    csv_text: str = Field(..., min_length=1)


@app.post("/api/meroshare/import")
def meroshare_import(body: MeroShareImportRequest):
    """Persist a pasted CSV export — the no-credentials path into the mirror."""
    result = sync_from_csv(_storage()._conn, body.csv_text)
    return {
        "ok": result.ok,
        "method": result.method,
        "holdings": result.holdings,
        "transactions": result.transactions,
        "error": result.error,
        "ran_at": result.ran_at,
    }


@app.get("/api/meroshare/holdings")
def meroshare_holdings():
    """Holdings as last synced, ordered by symbol."""
    return [
        {
            "symbol": h.symbol,
            "current_balance": h.current_balance,
            "previous_balance": h.previous_balance,
            "pledged_balance": h.pledged_balance,
            "wacc": h.wacc,
            "previous_closing_price": h.previous_closing_price,
            "cost_basis": h.cost_basis,
            "market_value": h.market_value,
            "isin": h.isin,
            "script_desc": h.script_desc,
            # The full BOID/demat is an account identifier.  It is retained
            # internally only to aggregate multiple demats correctly, never
            # exposed through the browser API.
            "demat_last4": h.demat_last4 or (h.demat_number[-4:] if h.demat_number else None),
            "last_transaction_date": (
                h.last_transaction_date.isoformat() if h.last_transaction_date else None
            ),
            "source": h.source,
        }
        for h in stored_holdings(_storage()._conn)
    ]


@app.get("/api/meroshare/history")
def meroshare_history(limit: int = Query(20, ge=1, le=200)):
    """Recent MeroShare sync attempts, including redacted failures."""
    return sync_history(_storage()._conn, limit=limit)


@app.get("/api/meroshare/compare")
def meroshare_compare(cash: float = Query(100_000.0, gt=0)):
    """Compare the stored real holdings with the replayed paper book."""
    pipe = _pipeline()
    paper = pipe.replay_portfolio(cash).holdings()
    diffs = compare_with_paper(stored_holdings(_storage()._conn), paper)
    rows = [
        {
            "symbol": diff.symbol,
            "real_quantity": diff.real_quantity,
            "paper_quantity": diff.paper_quantity,
            "real_wacc": diff.real_wacc,
            "paper_avg_cost": diff.paper_avg_cost,
            "quantity_delta": diff.quantity_delta,
            "only_in": diff.only_in,
            "agrees": diff.agrees,
        }
        for diff in diffs
    ]
    return {"rows": rows, "summary": comparison_summary(diffs)}


# ---------------------------------------------------------------------------
# Background jobs — the long-running CLI commands, without a blocking request
# ---------------------------------------------------------------------------
class JobSubmitRequest(BaseModel):
    """Start one of the long-running commands.

    ``params`` is passed through to the handler rather than being modelled per
    kind: the five job kinds take overlapping but different options, and a
    discriminated union of five near-identical models would be more schema than
    the handlers themselves. Handlers validate what they read, and a bad value
    surfaces as a failed job with the reason attached.
    """

    kind: Literal["refresh-today", "ingest", "reconcile", "run-daily", "rag-index", "screen", "backfill", "fundamentals", "floorsheet"]
    params: dict[str, Any] = Field(default_factory=dict)


@app.post("/api/jobs")
def submit_job(body: JobSubmitRequest):
    """Queue a job and return it immediately, before any work has happened.

    409 when something is already running — every job writes to the same SQLite
    file, so this build runs one at a time and points the caller at the job in
    progress instead of interleaving two.
    """
    try:
        job = registry.submit(body.kind, body.params, _settings())
    except JobBusy as exc:
        raise HTTPException(
            409,
            detail={
                "message": f"a {exc.kind} job is already running",
                "running_job_id": exc.job_id,
            },
        ) from exc
    return job.as_dict()


@app.get("/api/jobs")
def list_jobs(limit: int = Query(20, ge=1, le=100)):
    """Recent jobs, newest first, without log bodies.

    ``kinds`` lets the UI render a launcher for every job type without knowing
    the list, and ``running`` is what a page polls to re-attach to a job that
    was started before the tab was opened.
    """
    return {
        "jobs": registry.listing(limit),
        "running": registry.running_id(),
        "kinds": sorted(HANDLERS),
    }


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    """Full job state including the tail of its log. This is the poll target."""
    payload = registry.snapshot(job_id)
    if payload is None:
        raise HTTPException(404, f"No job {job_id}")
    return payload


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    """Ask a job to stop at its next progress checkpoint.

    Cancelling a finished job is deliberately not an error: the operator cannot
    know it finished between the last poll and the click.
    """
    job = registry.cancel(job_id)
    if job is None:
        raise HTTPException(404, f"No job {job_id}")
    return job.as_dict()


# ---------------------------------------------------------------------------
# Configured sources
# ---------------------------------------------------------------------------
@app.get("/api/sources")
def sources():
    """Every configured source, whether it is enabled, and how it is accessed."""
    settings = _settings()
    cfg = load_sources()
    return {
        "enabled_in_settings": list(settings.enabled_sources),
        "sources": [
            {
                "name": name,
                "enabled": spec.enabled,
                "base_url": spec.base_url,
                "access_method": spec.access_method,
                "confidence": getattr(spec, "confidence", None),
                "endpoints": [
                    {
                        "name": ep_name,
                        "path": getattr(ep, "path", ""),
                        "method": getattr(ep, "method", "GET"),
                    }
                    for ep_name, ep in spec.endpoints.items()
                ],
            }
            for name, spec in cfg.sources.items()
        ],
    }


# ---------------------------------------------------------------------------
# Table browser — the `export` command, rendered instead of written
# ---------------------------------------------------------------------------
#: Newest-first ordering per exportable table. Keys are exactly
#: :data:`EXPORT_TABLES`, which doubles as the identifier whitelist — a name that
#: is not a key never reaches SQL.
_TABLE_ORDER = {
    "price_bars": "business_date DESC, symbol",
    "reconciled_prices": "business_date DESC, symbol",
    "signals": "business_date DESC, symbol",
    "index_values": "business_date DESC, name",
    "ingest_log": "id DESC",
    "corporate_actions": "ex_date DESC, symbol",
    "paper_trades": "business_date DESC, trade_id DESC",
}


@app.get("/api/tables")
def list_tables():
    """The exportable tables and their row counts.

    This is the browser-side answer to ``export csv``: the dashboard renders the
    rows in-page, so nothing is written to disk and nothing is downloaded.
    """
    conn = _storage()._conn
    out = []
    for name in EXPORT_TABLES:
        count = conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]  # noqa: S608
        out.append({"name": name, "rows": count})
    return {"tables": out}


@app.get("/api/tables/{name}")
def read_table(
    name: str,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """One page of a table, newest first, with its column order and total.

    Paged in SQL rather than by slicing ``Storage.all_*()`` so opening the
    browser on ``price_bars`` does not pull the whole history into memory.
    """
    if name not in _TABLE_ORDER:
        raise HTTPException(404, f"Unknown table {name!r}. Try one of: {', '.join(EXPORT_TABLES)}")
    conn = _storage()._conn
    total = conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]  # noqa: S608
    cursor = conn.execute(
        f"SELECT * FROM {name} ORDER BY {_TABLE_ORDER[name]} LIMIT ? OFFSET ?",  # noqa: S608
        (limit, offset),
    )
    rows = [dict(r) for r in cursor.fetchall()]
    columns = [d[0] for d in cursor.description] if cursor.description else []
    return {
        "name": name,
        "columns": columns,
        "rows": rows,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# ---------------------------------------------------------------------------
# Corporate actions — manual entry, as in the CLI
# ---------------------------------------------------------------------------
class CorporateActionRequest(BaseModel):
    """A manually recorded bonus / rights / split / dividend."""

    symbol: str = Field(min_length=1)
    ex_date: str
    action_type: Literal["bonus", "rights", "split", "dividend"]
    ratio_numerator: int = Field(1, gt=0)
    ratio_denominator: int = Field(1, gt=0)
    notes: str = ""
    price_factor: Decimal | None = Field(None, gt=0, allow_inf_nan=False)


def _corporate_action_response(ca: CorporateAction) -> dict[str, Any]:
    return {
        "symbol": ca.symbol,
        "ex_date": ca.ex_date.isoformat(),
        "action_type": ca.action_type.value,
        "ratio_numerator": ca.ratio_numerator,
        "ratio_denominator": ca.ratio_denominator,
        "factor": float(ca.factor),
        "source": ca.source.value,
        "notes": ca.notes or "",
        "description": ca.description,
    }


@app.get("/api/corporate-actions")
def list_corporate_actions(symbol: str | None = Query(None)):
    """Stored corporate actions, optionally for one symbol."""
    actions = _storage().corporate_actions(symbol=_symbol_filter(symbol))
    return [_corporate_action_response(ca) for ca in actions]


@app.post("/api/corporate-actions")
def add_corporate_action(body: CorporateActionRequest):
    """Record a corporate action by hand.

    Preserve published prices and recompute the separate adjusted history.
    """
    try:
        ex_date = date.fromisoformat(body.ex_date)
    except ValueError as exc:
        raise HTTPException(400, f"ex_date must be YYYY-MM-DD, got {body.ex_date!r}") from exc
    from nepse_trader.analysis.corporate_actions import adjustment_factor

    factor = adjustment_factor(CorporateActionType(body.action_type), body.ratio_numerator,
                               body.ratio_denominator, body.price_factor)
    action = CorporateAction(
        symbol=body.symbol.strip().upper(),
        ex_date=ex_date,
        action_type=CorporateActionType(body.action_type),
        ratio_numerator=body.ratio_numerator,
        ratio_denominator=body.ratio_denominator,
        factor=factor,
        source=SourceName.MANUAL,
        notes=body.notes,
    )
    _storage().upsert_corporate_action(action)
    _pipeline().refresh_adjustments({action.symbol})
    return _corporate_action_response(action)


# ---------------------------------------------------------------------------
# Paper trades — simulated fills only; there is no live order path anywhere
# ---------------------------------------------------------------------------
class PaperTradeRequest(BaseModel):
    """A simulated fill. Full Nepal fees apply, and CGT on a realized gain.

    ``cash`` is the replay parameter, not a deposit: the portfolio is rebuilt
    from every recorded trade starting from this opening balance, so changing it
    between trades silently re-prices the whole book. It defaults to the same
    100,000 the CLI and the portfolio view use, and the UI keeps it fixed.
    """

    symbol: str = Field(min_length=1)
    side: Literal["buy", "sell"]
    price: float = Field(gt=0)
    quantity: int = Field(gt=0)
    business_date: str | None = None
    cash: float = Field(100_000.0, gt=0)


@app.get("/api/paper/trades")
def paper_trades(limit: int = Query(100, ge=1, le=1000)):
    """Recorded simulated trades, newest first."""
    rows = [dict(r) for r in _storage().all_paper_trades()]
    rows.sort(key=lambda r: (str(r.get("business_date") or ""), r.get("trade_id") or ""), reverse=True)
    return rows[:limit]


@app.post("/api/paper/trades")
def record_paper_trade(body: PaperTradeRequest):
    """Record a simulated buy or sell and return the fill plus the new book.

    Replays the existing trades first so position and cost basis are correct,
    then attaches storage so only the new trade is persisted — the same two-step
    the ``paper buy``/``paper sell`` commands use.
    """
    try:
        trade_date = date.fromisoformat(body.business_date) if body.business_date else date.today()
    except ValueError as exc:
        raise HTTPException(
            400, f"business_date must be YYYY-MM-DD, got {body.business_date!r}"
        ) from exc

    pipe = _pipeline()
    portfolio = pipe.replay_portfolio(body.cash)
    portfolio.storage = pipe.storage
    symbol = body.symbol.strip().upper()
    fill = portfolio.buy if body.side == "buy" else portfolio.sell
    try:
        trade = fill(symbol, body.price, body.quantity, trade_date)
    except ValueError as exc:
        # Insufficient cash or selling more than is held. Operator error, not a
        # server fault, so 400 with the portfolio's own wording.
        raise HTTPException(400, str(exc)) from exc
    return {
        "trade": {
            "symbol": trade.symbol,
            "side": trade.side.value if hasattr(trade.side, "value") else str(trade.side),
            "business_date": trade.business_date.isoformat(),
            "quantity": trade.quantity,
            "price": float(trade.price),
            "gross_amount": float(trade.gross_amount),
            "broker_commission": float(trade.broker_commission),
            "sebon_fee": float(trade.sebon_fee),
            "dp_charge": float(trade.dp_charge),
            "cgt": float(trade.cgt),
            "net_amount": float(trade.net_amount),
        },
        "portfolio": portfolio.to_dict(),
    }


# ---------------------------------------------------------------------------
# Bulk analytics — the whole-market views the CLI prints as tables
# ---------------------------------------------------------------------------
@app.get("/api/stats")
def bulk_stats(
    symbols: str | None = Query(None, description="Comma list. Default: the first `top` stored"),
    top: int = Query(25, ge=1, le=500),
    periods: int = Query(252, ge=1, le=366),
):
    """Quantitative statistics for many symbols at once — the `stats` command."""
    pipe = _pipeline()
    requested = [s.strip().upper() for s in (symbols or "").split(",") if s.strip()]
    target = requested or pipe.storage.symbols()[:top]
    if not target:
        return {"symbols": [], "rows": []}
    return {
        "symbols": target,
        "periods_per_year": periods,
        "rows": pipe.quant_stats(target, periods_per_year=periods),
    }


@app.get("/api/signals")
def bulk_signals(
    strategy: str = Query("sma_cross"),
    symbols: str | None = Query(None, description="Comma list. Default: the first `top` stored"),
    top: int = Query(25, ge=1, le=500),
    actionable_only: bool = Query(False, description="Drop HOLD rows"),
):
    """The latest signal per symbol for one strategy — the whole-market `signal` view.

    Note this recomputes and persists signals, exactly as the per-symbol route
    already does; it is a read in the HTTP sense only.
    """
    if strategy not in STRATEGIES:
        raise HTTPException(400, f"Unknown strategy {strategy!r}. One of: {', '.join(STRATEGIES)}")
    pipe = _pipeline()
    requested = [s.strip().upper() for s in (symbols or "").split(",") if s.strip()]
    target = requested or pipe.storage.symbols()[:top]
    rows = [
        {
            "symbol": s.symbol,
            "business_date": s.business_date.isoformat(),
            "strategy": s.strategy,
            "action": s.action.value,
            "strength": s.strength,
            "reason": s.reason,
            "price": s.price,
        }
        for s in pipe.latest_signals(target, strategy)
    ]
    if actionable_only:
        rows = [r for r in rows if r["action"] in ("BUY", "SELL")]
    return {"strategy": strategy, "count": len(rows), "rows": rows}


@app.get("/api/strategies")
def strategy_names():
    """The registered strategy names, so a UI picker cannot drift from the registry."""
    return {"strategies": sorted(STRATEGIES)}


# ---------------------------------------------------------------------------
# AI provider status and connectivity
# ---------------------------------------------------------------------------
class AiTestRequest(BaseModel):
    """Exercise one provider chain with a single tiny prompt."""

    tier: Literal["bulk", "synthesis"] = "synthesis"


@app.get("/api/ai/models")
def ai_models():
    """Each provider chain and which legs are actually usable.

    Read-only and offline: reports what is configured without calling anybody,
    so the page can be opened without spending a token.
    """
    from nepse_trader.ai import LLMRouter

    router = LLMRouter(_storage()._conn, _settings(), online=None)
    status = router.status()
    usable = sum(
        1 for legs in status["tiers"].values() for leg in legs if leg["available"]
    )
    return {
        **status,
        "usable_legs": usable,
        "banner": (
            None
            if usable
            else "No provider is usable — AI mode will degrade to normal mode. "
            "See .env.example for what to set."
        ),
    }


@app.post("/api/ai/test")
def ai_test(body: AiTestRequest):
    """Send one tiny prompt through a chain and report what answered.

    This spends real budget and needs the network — the only honest way to know
    a provider works is to use it, which is why it is a POST and never happens
    on page load. A chain where nobody answers is a 200 with ``ok: false``, not
    a 5xx: a missing third-party key is not a server fault, and the UI needs to
    render the reason.
    """
    from nepse_trader.ai import LLMRouter, prompts

    router = LLMRouter(_storage()._conn, _settings(), online=True)
    response = router.complete(
        prompts.PING, task="ai_test", tier=body.tier, max_tokens=64, use_cache=False
    )
    return {
        "ok": response.ok,
        "tier": body.tier,
        "provider": response.provider,
        "model": response.model,
        "total_tokens": response.total_tokens,
        "text": response.text.strip()[:500] if response.ok else "",
        "error": response.error,
    }


from nepse_trader.web.research import router as _research_router  # noqa: E402

app.include_router(_research_router)

from nepse_trader.web.decisions import router as _decision_router  # noqa: E402

app.include_router(_decision_router)

# ---------------------------------------------------------------------------
# Serve built frontend (production)
# ---------------------------------------------------------------------------
_static = Path(__file__).resolve().parent.parent.parent / "web" / "dist"
if _static.is_dir():

    class _SpaStaticFiles(StaticFiles):
        """Serve ``index.html`` for unknown paths so client-side routes resolve.

        ``StaticFiles(html=True)`` only answers ``/`` with the entry page; deep
        links like ``/rashifal`` or a refresh on ``/settings`` would 404 before
        React Router ever runs.
        """

        async def get_response(self, path: str, scope):
            try:
                response = await super().get_response(path, scope)
            except StarletteHTTPException as exc:
                if exc.status_code != 404 or path.startswith("api"):
                    raise
                # /api/* must keep its JSON 404s; only page paths fall back.
                response = await super().get_response("index.html", scope)
            return response

    app.mount("/", _SpaStaticFiles(directory=str(_static), html=True), name="frontend")
    log.info("serving frontend from %s", _static)
else:
    log.info("no built frontend found at %s — API-only mode", _static)
