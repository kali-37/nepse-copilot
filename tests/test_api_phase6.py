"""Phase 6 endpoints: RAG search, AI budget, news, watchlist, advisor, MeroShare.

Every test builds its own ``Storage`` on a temp path and injects it (plus a
``Settings(_env_file=None, ...)``) into ``nepse_trader.web.api._state``, matching
the override pattern in ``test_web_api.py``. Passing settings explicitly matters
here: several of these endpoints read ``meroshare_*`` and ``watchlist``, and a
developer's real ``.env`` would otherwise decide whether a test passes.

Nothing reaches the network. The MeroShare sync test drives the client through an
``httpx.MockTransport``; the credential-leak test asserts on the response body of
every endpoint that touches the MeroShare layer.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from nepse_trader.ai.budget import TokenBudget
from nepse_trader.ai.providers import LLMResponse
from nepse_trader.config import Settings
from nepse_trader.meroshare import MeroShareCredentials
from nepse_trader.meroshare.models import MeroShareHolding
from nepse_trader.meroshare.sync import sync_payload
from nepse_trader.models import PriceBar, ReconciledPrice, SourceName
from nepse_trader.rag.corpus import KIND_NEWS, KIND_PRICE, Document
from nepse_trader.rag.index import DocumentIndex
from nepse_trader.storage import Storage
from nepse_trader.web.api import app

# Enough bars for an ATR-based plan card (plan.py needs 20).
_BAR_COUNT = 40


def _bars(symbol: str = "NABIL") -> list[PriceBar]:
    out: list[PriceBar] = []
    for i in range(_BAR_COUNT):
        close = 100.0 + i
        out.append(
            PriceBar(
                symbol=symbol,
                business_date=date(2026, 1, 1) + timedelta(days=i),
                open=close - 1,
                high=close + 2,
                low=close - 2,
                close=close,
                previous_close=close - 1,
                volume=1000 + i,
                turnover=float(close * 1000),
                source=SourceName.SHARESANSAR,
                fetched_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
            )
        )
    return out


def _reconciled(symbol: str = "NABIL") -> list[ReconciledPrice]:
    return [
        ReconciledPrice(
            symbol=b.symbol,
            business_date=b.business_date,
            open=b.open,
            high=b.high,
            low=b.low,
            close=b.close,
            previous_close=b.previous_close,
            volume=b.volume,
            turnover=b.turnover,
            sources_agreeing=[SourceName.SHARESANSAR],
            sources_present=[SourceName.SHARESANSAR],
            disputed_fields=[],
            confidence=1.0,
        )
        for b in _bars(symbol)
    ]


def _make_client(tmp_path, *, seed: bool = True, **setting_overrides):
    """A TestClient wired to a fresh temp DB and explicit Settings."""
    db = tmp_path / "phase6.db"
    storage = Storage(db)
    if seed:
        storage.upsert_price_bars(_bars())
        storage.upsert_reconciled(_reconciled())

    settings = Settings(_env_file=None, db_path=db, **setting_overrides)

    from nepse_trader.web.api import _state

    _state["storage"] = storage
    _state["settings"] = settings
    client = TestClient(app)
    return client, storage, settings


@pytest.fixture
def client(tmp_path):
    c, storage, _ = _make_client(tmp_path)
    with c:
        yield c
    storage.close()
    from nepse_trader.web.api import _state

    _state.clear()


@pytest.fixture
def empty_client(tmp_path):
    """A client over a migrated but completely empty database."""
    c, storage, _ = _make_client(tmp_path, seed=False)
    with c:
        yield c
    storage.close()
    from nepse_trader.web.api import _state

    _state.clear()


def _index(client) -> DocumentIndex:
    from nepse_trader.web.api import _state

    return DocumentIndex(_state["storage"]._conn)


# ---------------------------------------------------------------------------
# GET /api/rag/search
# ---------------------------------------------------------------------------
class TestRagSearch:
    def _seed_docs(self, client) -> DocumentIndex:
        index = _index(client)
        index.upsert(
            [
                Document(
                    doc_id="price:NABIL:2026-02-09",
                    kind=KIND_PRICE,
                    symbol="NABIL",
                    business_date=date(2026, 2, 9),
                    title="NABIL price on 2026-02-09",
                    body="NABIL closed at 139.00, up on solid volume.",
                    source="sharesansar",
                ),
                Document(
                    doc_id="news:abc123",
                    kind=KIND_NEWS,
                    symbol="SCB",
                    business_date=date(2026, 2, 8),
                    title="SCB announces dividend",
                    body="Standard Chartered declared a cash dividend for the year.",
                    url="https://example.test/scb",
                    source="sharesansar",
                ),
            ]
        )
        return index

    def test_search_finds_a_document(self, client):
        self._seed_docs(client)
        r = client.get("/api/rag/search?q=NABIL")
        assert r.status_code == 200
        data = r.json()
        assert data["query"] == "NABIL"
        assert data["count"] >= 1
        assert data["hits"][0]["doc_id"] == "price:NABIL:2026-02-09"
        assert data["hits"][0]["kind"] == "price"

    def test_search_packs_evidence_with_citations(self, client):
        self._seed_docs(client)
        r = client.get("/api/rag/search?q=dividend")
        data = r.json()
        assert data["evidence"]["markers"] == ["[E1]"]
        assert data["evidence"]["citations"]["[E1]"] == "news:abc123"
        assert "dividend" in data["evidence"]["rendered"].lower()

    def test_search_symbol_filter_narrows(self, client):
        self._seed_docs(client)
        r = client.get("/api/rag/search?q=NABIL+dividend&symbol=scb")
        data = r.json()
        assert data["count"] == 1
        assert {h["symbol"] for h in data["hits"]} == {"SCB"}

    def test_search_kind_filter_narrows(self, client):
        self._seed_docs(client)
        r = client.get("/api/rag/search?q=NABIL+dividend&kind=news")
        assert {h["kind"] for h in r.json()["hits"]} == {"news"}

    def test_search_with_no_hits_is_empty_not_an_error(self, client):
        self._seed_docs(client)
        r = client.get("/api/rag/search?q=zzzzunmatchablezzzz")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 0
        assert data["hits"] == []
        assert data["evidence"]["markers"] == []
        assert data["evidence"]["rendered"] == "(no evidence available)"

    def test_search_on_empty_corpus(self, empty_client):
        r = empty_client.get("/api/rag/search?q=anything")
        assert r.status_code == 200
        assert r.json()["hits"] == []

    def test_search_limit_out_of_range_is_422(self, client):
        assert client.get("/api/rag/search?q=NABIL&limit=0").status_code == 422
        assert client.get("/api/rag/search?q=NABIL&limit=9999").status_code == 422

    def test_search_limit_caps_hits(self, client):
        self._seed_docs(client)
        r = client.get("/api/rag/search?q=NABIL+dividend&limit=1")
        assert len(r.json()["hits"]) == 1

    def test_stats_reports_per_kind(self, client):
        self._seed_docs(client)
        r = client.get("/api/rag/stats")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 2
        assert data["per_kind"] == {"news": 1, "price": 1}

    def test_stats_on_empty_corpus(self, empty_client):
        data = empty_client.get("/api/rag/stats").json()
        assert data["total"] == 0
        assert data["per_kind"] == {}


# ---------------------------------------------------------------------------
# GET /api/ai/budget
# ---------------------------------------------------------------------------
class TestAiBudget:
    def test_budget_on_empty_ledger(self, empty_client):
        r = empty_client.get("/api/ai/budget")
        assert r.status_code == 200
        data = r.json()
        assert data["calls"] == 0
        assert data["tokens"] == 0
        assert data["exhausted"] is False
        assert data["history"] == []
        # Caps come from the injected Settings, not the developer's .env.
        assert data["max_calls"] == 40
        assert data["max_tokens"] == 400_000
        assert data["max_deep_passes"] == 2

    def test_budget_reflects_recorded_calls(self, tmp_path):
        c, storage, settings = _make_client(tmp_path, seed=False)
        budget = TokenBudget(storage._conn, settings)
        budget.record(
            LLMResponse(
                text="ok", provider="openrouter", model="m", prompt_tokens=100,
                completion_tokens=40,
            ),
            task="symbol_note",
        )
        budget.record(LLMResponse(error="boom"), task="symbol_note")
        with c:
            data = c.get("/api/ai/budget").json()
        assert data["calls"] == 2
        assert data["tokens"] == 140
        assert data["tokens_left"] == 400_000 - 140
        assert data["failed_calls"] == 1
        assert len(data["history"]) == 2
        storage.close()
        from nepse_trader.web.api import _state

        _state.clear()

    def test_budget_honours_injected_caps(self, tmp_path):
        c, storage, _ = _make_client(
            tmp_path, seed=False, llm_max_calls_per_day=1, llm_max_tokens_per_day=10
        )
        with c:
            data = c.get("/api/ai/budget").json()
        assert data["max_calls"] == 1
        assert data["max_tokens"] == 10
        storage.close()
        from nepse_trader.web.api import _state

        _state.clear()


# ---------------------------------------------------------------------------
# GET /api/news
# ---------------------------------------------------------------------------
class TestNews:
    def _seed_news(self, client) -> None:
        _index(client).upsert(
            [
                Document(
                    doc_id="news:old",
                    kind=KIND_NEWS,
                    symbol="NABIL",
                    business_date=date(2026, 2, 1),
                    title="Older NABIL headline",
                    body="Older body.",
                    url="https://example.test/old",
                    source="sharesansar",
                    fetched_at=datetime(2026, 2, 1, 9, 0, tzinfo=UTC),
                ),
                Document(
                    doc_id="news:new",
                    kind=KIND_NEWS,
                    symbol="SCB",
                    business_date=date(2026, 2, 10),
                    title="Newer SCB headline",
                    body="Newer body.",
                    source="sharesansar",
                ),
                Document(
                    doc_id="price:NABIL:2026-02-10",
                    kind=KIND_PRICE,
                    symbol="NABIL",
                    business_date=date(2026, 2, 10),
                    title="NABIL price",
                    body="Not news.",
                ),
            ]
        )

    def test_news_newest_first_and_news_only(self, client):
        self._seed_news(client)
        r = client.get("/api/news")
        assert r.status_code == 200
        data = r.json()
        assert [d["doc_id"] for d in data] == ["news:new", "news:old"]
        assert data[0]["title"] == "Newer SCB headline"
        assert data[1]["fetched_at"] == "2026-02-01T09:00:00+00:00"

    def test_news_symbol_filter(self, client):
        self._seed_news(client)
        data = client.get("/api/news?symbol=nabil").json()
        assert [d["doc_id"] for d in data] == ["news:old"]

    def test_news_limit(self, client):
        self._seed_news(client)
        assert len(client.get("/api/news?limit=1").json()) == 1

    def test_news_missing_symbol_is_empty(self, client):
        self._seed_news(client)
        assert client.get("/api/news?symbol=NOSUCH").json() == []

    def test_news_on_empty_db(self, empty_client):
        r = empty_client.get("/api/news")
        assert r.status_code == 200
        assert r.json() == []

    def test_news_limit_out_of_range_is_422(self, client):
        assert client.get("/api/news?limit=0").status_code == 422
        assert client.get("/api/news?limit=201").status_code == 422


# ---------------------------------------------------------------------------
# GET/PUT /api/settings/watchlist
# ---------------------------------------------------------------------------
class TestWatchlist:
    def test_get_falls_back_to_env_watchlist(self, tmp_path):
        c, storage, _ = _make_client(tmp_path, seed=False, watchlist=["NABIL", "SCB"])
        with c:
            data = c.get("/api/settings/watchlist").json()
        assert data["symbols"] == ["NABIL", "SCB"]
        assert data["source"] == "env"
        assert data["updated_at"] is None
        storage.close()
        from nepse_trader.web.api import _state

        _state.clear()

    def test_get_is_empty_when_nothing_configured(self, empty_client):
        data = empty_client.get("/api/settings/watchlist").json()
        assert data["symbols"] == []
        assert data["source"] == "env"

    def test_put_persists_and_normalises(self, client):
        r = client.put(
            "/api/settings/watchlist",
            json={"symbols": [" nabil ", "scb", "NABIL", ""]},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["symbols"] == ["NABIL", "SCB"]
        assert data["source"] == "database"
        assert data["updated_at"] is not None
        assert client.get("/api/settings/watchlist").json()["symbols"] == ["NABIL", "SCB"]

    def test_put_survives_a_new_storage_over_the_same_file(self, tmp_path):
        """The whole point of the app_settings table: durability across restarts."""
        c, storage, _ = _make_client(tmp_path, seed=False)
        with c:
            c.put("/api/settings/watchlist", json={"symbols": ["HBL"]})
        storage.close()
        from nepse_trader.web.api import _state

        _state.clear()

        c2, storage2, _ = _make_client(tmp_path, seed=False)
        with c2:
            data = c2.get("/api/settings/watchlist").json()
        assert data["symbols"] == ["HBL"]
        assert data["source"] == "database"
        storage2.close()
        _state.clear()

    def test_put_empty_list_clears_the_override(self, tmp_path):
        c, storage, _ = _make_client(tmp_path, seed=False, watchlist=["NABIL"])
        with c:
            c.put("/api/settings/watchlist", json={"symbols": ["HBL"]})
            after = c.put("/api/settings/watchlist", json={"symbols": []}).json()
        assert after["symbols"] == ["NABIL"]
        assert after["source"] == "env"
        storage.close()
        from nepse_trader.web.api import _state

        _state.clear()

    def test_put_malformed_body_is_422(self, client):
        assert client.put("/api/settings/watchlist", json={}).status_code == 422
        assert (
            client.put("/api/settings/watchlist", json={"symbols": "NABIL"}).status_code == 422
        )
        assert (
            client.put("/api/settings/watchlist", json={"symbols": [{"a": 1}]}).status_code
            == 422
        )

    def test_get_ignores_a_corrupt_stored_value(self, client):
        from nepse_trader.web.api import _ensure_app_settings, _state

        conn = _state["storage"]._conn
        _ensure_app_settings(conn)
        conn.execute(
            "INSERT INTO app_settings (key, value, updated_at) VALUES ('watchlist', ?, ?)",
            ("not json at all", "2026-02-10T00:00:00+00:00"),
        )
        conn.commit()
        data = client.get("/api/settings/watchlist").json()
        assert data["symbols"] == []
        assert data["source"] == "env"


# ---------------------------------------------------------------------------
# Advisor
# ---------------------------------------------------------------------------
class TestAdvisor:
    def test_run_normal_mode_persists_and_returns(self, client):
        r = client.post("/api/advisor/run", json={"mode": "normal", "horizon": "week"})
        assert r.status_code == 200
        data = r.json()
        assert data["mode"] == "normal"
        assert data["horizon"] == "week"
        assert data["run_id"] is not None
        assert data["banner"] == ""
        assert data["degraded"] is False
        assert [c["symbol"] for c in data["cards"]] == ["NABIL"]
        assert data["cards"][0]["stop"] < data["cards"][0]["reference_price"]

    def test_run_defaults_are_applied(self, client):
        data = client.post("/api/advisor/run", json={}).json()
        assert data["mode"] == "normal"
        assert data["horizon"] == "week"
        assert data["online"] is False
        assert data["equity"] == 100_000.0

    def test_run_accepts_year_horizon(self, client):
        data = client.post("/api/advisor/run", json={"horizon": "year"}).json()
        assert data["horizon"] == "year"

    def test_run_honours_explicit_symbols(self, client):
        data = client.post("/api/advisor/run", json={"symbols": ["nabil"]}).json()
        assert [c["symbol"] for c in data["cards"]] == ["NABIL"]

    def test_run_reports_unknown_symbol_as_do_not_touch(self, client):
        data = client.post("/api/advisor/run", json={"symbols": ["NOSUCH"]}).json()
        assert data["cards"] == []
        assert data["do_not_touch"][0]["symbol"] == "NOSUCH"
        assert "bars" in data["do_not_touch"][0]["reason"]

    def test_run_ai_mode_degrades_with_a_banner(self, tmp_path):
        """No provider configured must still yield the deterministic numbers."""
        c, storage, _ = _make_client(
            tmp_path,
            llm_bulk_providers=[],
            llm_synthesis_providers=[],
            rag_enable_web=False,
        )
        with c:
            data = c.post("/api/advisor/run", json={"mode": "ai", "online": False}).json()
        assert data["mode"] == "ai"
        assert data["degraded"] is True
        assert data["banner"]
        # The engine's numbers survive the missing narrative.
        assert [card["symbol"] for card in data["cards"]] == ["NABIL"]
        assert data["cards"][0]["note"] == ""
        storage.close()
        from nepse_trader.web.api import _state

        _state.clear()

    def test_run_on_empty_db_is_400(self, empty_client):
        r = empty_client.post("/api/advisor/run", json={})
        assert r.status_code == 400
        assert "empty" in r.json()["detail"]

    def test_run_malformed_body_is_422(self, client):
        assert client.post("/api/advisor/run", json={"mode": "wizard"}).status_code == 422
        assert client.post("/api/advisor/run", json={"horizon": "decade"}).status_code == 422
        assert client.post("/api/advisor/run", json={"equity": -5}).status_code == 422
        assert client.post("/api/advisor/run", json={"online": "maybe"}).status_code == 422

    def test_latest_is_404_before_any_run(self, client):
        r = client.get("/api/advisor/latest")
        assert r.status_code == 404
        assert "not run yet" in r.json()["detail"]

    def test_latest_returns_the_run_with_cards(self, client):
        posted = client.post("/api/advisor/run", json={}).json()
        data = client.get("/api/advisor/latest").json()
        assert data["run_id"] == posted["run_id"]
        assert data["mode"] == "normal"
        assert [c["symbol"] for c in data["cards"]] == ["NABIL"]
        assert isinstance(data["cards"][0]["targets"], list)
        assert set(data["cards"][0]["confidence"]) >= {"value", "band", "label", "basis"}

    def test_doses_latest_is_404_before_any_run(self, client):
        r = client.get("/api/advisor/doses/latest")
        assert r.status_code == 404

    def test_doses_latest_returns_four_disjoint_horizons(self, client):
        client.post("/api/advisor/run", json={})
        data = client.get("/api/advisor/doses/latest").json()
        assert [dose["horizon"] for dose in data["doses"]] == ["day", "week", "month", "year"]
        assigned = [
            (card["symbol"], card["horizon_days"])
            for dose in data["doses"]
            for card in dose["cards"]
        ]
        assert len(assigned) == len(set(assigned))

    def test_history_is_empty_before_any_run(self, client):
        assert client.get("/api/advisor/history").json() == []

    def test_history_newest_first_without_cards(self, client):
        client.post("/api/advisor/run", json={"horizon": "day"})
        client.post("/api/advisor/run", json={"horizon": "month"})
        rows = client.get("/api/advisor/history").json()
        assert len(rows) == 2
        assert rows[0]["horizon"] == "month"
        assert "cards" not in rows[0]

    def test_history_limit(self, client):
        client.post("/api/advisor/run", json={})
        client.post("/api/advisor/run", json={})
        assert len(client.get("/api/advisor/history?limit=1").json()) == 1

    def test_history_limit_out_of_range_is_422(self, client):
        assert client.get("/api/advisor/history?limit=0").status_code == 422
        assert client.get("/api/advisor/history?limit=500").status_code == 422


class TestJournalHistory:
    def test_history_is_empty_and_supports_filters(self, client):
        assert client.get("/api/journal/history").json() == []
        client.post("/api/advisor/run", json={})
        rows = client.get("/api/journal/history?symbol=nabil&status=open").json()
        assert rows
        assert all(row["symbol"] == "NABIL" and row["status"] == "open" for row in rows)

    def test_history_limit_out_of_range_is_422(self, client):
        assert client.get("/api/journal/history?limit=0").status_code == 422
        assert client.get("/api/journal/history?limit=501").status_code == 422


class TestJournalLifecycleAPI:
    @staticmethod
    def _insert_prediction(client, prediction_id: str = "api-p1") -> str:
        from nepse_trader.web.api import _state

        conn = _state["storage"]._conn
        conn.execute(
            """
            INSERT INTO predictions (
                prediction_id, symbol, made_on, horizon, horizon_days, deadline,
                action, reference_price, entry_low, entry_high, stop, target_1,
                quantity, expected_net_pnl, confidence, confidence_band,
                confidence_basis, status, created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                prediction_id,
                "NABIL",
                "2026-01-01",
                "day",
                3,
                "2026-01-06",
                "accumulate",
                100.0,
                99.0,
                101.0,
                90.0,
                104.0,
                1,
                1.0,
                0.45,
                "COIN_FLIP",
                "test",
                "open",
                "2026-01-01T00:00:00+00:00",
            ),
        )
        conn.commit()
        return prediction_id

    def test_score_review_distill_retire_and_calibrate(self, client):
        prediction_id = self._insert_prediction(client)

        scored = client.post(
            f"/api/journal/{prediction_id}/score?as_of=2026-01-10"
        )
        assert scored.status_code == 200
        assert scored.json()[0]["outcome"] == "TARGET_HIT"
        assert scored.json()[0]["hit"] == 1

        reviewed = client.post(
            f"/api/journal/{prediction_id}/review",
            json={"text": "Target was reached in the local tape."},
        )
        assert reviewed.status_code == 200
        assert reviewed.json()["status"] == "reviewed"

        distilled = client.post(
            f"/api/journal/{prediction_id}/distill",
            json={"lesson": "Keep stop-first outcome scoring."},
        )
        assert distilled.status_code == 200
        assert distilled.json()["lesson_id"].startswith("prediction_lesson:")

        retired = client.post(f"/api/journal/{prediction_id}/retire")
        assert retired.status_code == 200
        assert retired.json()["status"] == "retired"

        history = client.get("/api/journal/history?status=retired").json()
        assert history[0]["prediction_id"] == prediction_id
        calibration = client.get("/api/journal/calibration?symbol=nabil&horizon=day")
        assert calibration.status_code == 200
        assert calibration.json()[0]["hits"] == 1

    def test_lifecycle_rejects_invalid_transition(self, client):
        prediction_id = self._insert_prediction(client, "api-p2")
        response = client.post(
            f"/api/journal/{prediction_id}/review", json={"review": "too early"}
        )
        assert response.status_code == 409
        assert "only scored" in response.json()["detail"]

    def test_batch_score_is_bounded_and_empty_safe(self, empty_client):
        response = empty_client.post("/api/journal/score", json={"limit": 1})
        assert response.status_code == 200
        assert response.json() == []
        assert empty_client.post("/api/journal/score", json={"limit": 0}).status_code == 422


class TestAuctionAPI:
    def test_advice_is_saved_and_explicitly_manual_only(self, client):
        response = client.post(
            "/api/auction/advice",
            json={
                "symbol": "nabil",
                "auction_date": "2026-08-24",
                "units": 10,
                "min_bid_price": 50,
                "market_price": 100,
                "expected_exit_price": 110,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "NABIL"
        assert data["manual_only"] is True
        assert data["bid_submitted"] is False
        assert data["verdict"] in {"bid", "skip"}

        listed = client.get("/api/auction/advice?symbol=nabil&limit=1")
        assert listed.status_code == 200
        assert listed.json()[0]["advice_id"] == data["advice_id"]
        assert client.get("/api/auction/latest?symbol=NABIL").json()["symbol"] == "NABIL"

    def test_advice_validation_rejects_bad_prices(self, client):
        response = client.post(
            "/api/auction/advice",
            json={"symbol": "NABIL", "units": 1, "min_bid_price": 0, "market_price": 100},
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# MeroShare — read-only, and no credential in any response
# ---------------------------------------------------------------------------
_PASSWORD = "sup3rs3cr3t-password"
_USERNAME = "some-username"


def _meroshare_client(tmp_path, **overrides):
    return _make_client(
        tmp_path,
        seed=False,
        meroshare_enabled=True,
        meroshare_dp_id="12300",
        meroshare_username=_USERNAME,
        meroshare_password=_PASSWORD,
        **overrides,
    )


class TestMeroShareStatus:
    def test_status_on_empty_db_with_no_credentials(self, empty_client):
        r = empty_client.get("/api/meroshare/status")
        assert r.status_code == 200
        data = r.json()
        assert data["enabled"] is False
        assert data["credentials_configured"] is False
        assert set(data["credentials_missing"]) == {"dp_id", "username", "password"}
        assert data["holdings"] == 0
        assert data["transactions"] == 0
        assert data["attempts"] == 0
        assert data["last_attempt_at"] is None
        assert data["last_success_at"] is None

    def test_status_reports_configured_without_values(self, tmp_path):
        c, storage, _ = _meroshare_client(tmp_path)
        with c:
            r = c.get("/api/meroshare/status")
        data = r.json()
        assert data["enabled"] is True
        assert data["credentials_configured"] is True
        assert data["credentials_missing"] == []
        assert data["credential_source"] == "settings"
        # The whole point: the values themselves are absent.
        body = r.text
        assert _PASSWORD not in body
        assert _USERNAME not in body
        assert "12300" not in body
        storage.close()
        from nepse_trader.web.api import _state

        _state.clear()

    def test_status_has_no_credential_keys_at_all(self, tmp_path):
        c, storage, _ = _meroshare_client(tmp_path)
        with c:
            data = c.get("/api/meroshare/status").json()
        forbidden = ("password", "username", "token", "dp_id", "session")
        for key in data:
            assert not any(f in key.lower() for f in forbidden), key
        storage.close()
        from nepse_trader.web.api import _state

        _state.clear()

    def test_holdings_never_expose_full_demat_number(self, tmp_path):
        c, storage, _ = _meroshare_client(tmp_path)
        demat = "1301230000000001"
        # Persist through the real write path: migration 0012 dropped the raw
        # ``demat_number`` column, so the fingerprint/last-four split happens
        # in ``sync_payload`` rather than at the SQL boundary.
        sync_payload(
            storage._conn,
            [
                MeroShareHolding(
                    symbol="NABIL",
                    current_balance=12,
                    demat_number=demat,
                    source="test",
                )
            ],
        )
        with c:
            response = c.get("/api/meroshare/holdings")
        data = response.json()
        assert response.status_code == 200
        assert data[0]["demat_last4"] == "0001"
        assert "demat_number" not in data[0]
        assert demat not in response.text
        storage.close()
        from nepse_trader.web.api import _state

        _state.clear()

    def test_toggle_uses_database_override_and_can_fall_back_to_env(self, tmp_path):
        c, storage, _ = _meroshare_client(tmp_path)
        with c:
            initial = c.get("/api/settings/meroshare")
            assert initial.status_code == 200
            assert initial.json()["enabled"] is True
            assert initial.json()["source"] == "env"

            disabled = c.put("/api/settings/meroshare", json={"enabled": False})
            assert disabled.status_code == 200
            assert disabled.json()["enabled"] is False
            assert disabled.json()["source"] == "database"
            assert c.get("/api/meroshare/status").json()["enabled"] is False

            cleared = c.put("/api/settings/meroshare", json={"enabled": None})
            assert cleared.status_code == 200
            assert cleared.json()["enabled"] is True
            assert cleared.json()["source"] == "env"
        storage.close()
        from nepse_trader.web.api import _state

        _state.clear()


class TestMeroShareSync:
    def test_sync_is_400_when_disabled(self, empty_client):
        r = empty_client.post("/api/meroshare/sync")
        assert r.status_code == 400
        assert "disabled" in r.json()["detail"].lower()

    def test_sync_failure_is_a_200_with_a_redacted_reason(self, tmp_path, monkeypatch):
        """A refused login must not 5xx, and must not echo the credential.

        404 rather than 401/403 or 500 on purpose: ``BaseClient._do_request``
        retries the latter with exponential backoff, and this client shares that
        degradation path without the ~5s of real sleep.
        """
        c, storage, settings = _meroshare_client(tmp_path)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"message": "nope"})

        from nepse_trader import meroshare as ms
        from nepse_trader.web import api as api_module

        real_client_cls = ms.MeroShareClient

        def _patched(settings_arg=None, **kwargs):
            kwargs.setdefault("http", httpx.Client(transport=httpx.MockTransport(handler)))
            return real_client_cls(settings_arg, **kwargs)

        monkeypatch.setattr(api_module, "MeroShareClient", _patched)

        with c:
            r = c.post("/api/meroshare/sync")
            # Same `with` block on purpose: leaving it runs lifespan shutdown,
            # which clears `_state` and would make the next request open the
            # developer's real database.
            status = c.get("/api/meroshare/status").json()
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is False
        assert data["method"] == "api"
        assert data["holdings"] == 0
        assert data["error"]
        assert _PASSWORD not in r.text
        assert _USERNAME not in r.text

        # The failed attempt is logged, and holdings are left alone.
        assert status["attempts"] == 1
        assert status["last_status"] == "error"
        assert status["last_success_at"] is None
        assert status["holdings"] == 0
        assert _PASSWORD not in status["last_error"]
        storage.close()
        from nepse_trader.web.api import _state

        _state.clear()

    def test_sync_success_persists_holdings(self, tmp_path, monkeypatch):
        c, storage, _ = _meroshare_client(tmp_path)

        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path.endswith("/auth/"):
                return httpx.Response(200, headers={"Authorization": "tok"}, json={})
            if path.endswith("/ownDetail/"):
                return httpx.Response(200, json={"demat": "1301230000000001"})
            if path.endswith("/myPortfolio/"):
                return httpx.Response(
                    200,
                    json={
                        "meroShareMyPortfolio": [
                            {"scrip": "NABIL", "currentBalance": 120, "valueAsOfLastTransactionPrice": 500.0}
                        ]
                    },
                )
            # WACC and transactions absent — tolerated by design.
            return httpx.Response(404, json={})

        from nepse_trader import meroshare as ms
        from nepse_trader.web import api as api_module

        real_client_cls = ms.MeroShareClient

        def _patched(settings_arg=None, **kwargs):
            kwargs.setdefault("http", httpx.Client(transport=httpx.MockTransport(handler)))
            return real_client_cls(settings_arg, **kwargs)

        monkeypatch.setattr(api_module, "MeroShareClient", _patched)

        with c:
            data = c.post("/api/meroshare/sync").json()
            holdings = c.get("/api/meroshare/holdings").json()
            status = c.get("/api/meroshare/status").json()

        assert data["ok"] is True
        assert data["holdings"] == 1
        assert [h["symbol"] for h in holdings] == ["NABIL"]
        assert holdings[0]["current_balance"] == 120
        assert status["holdings"] == 1
        assert status["last_status"] == "ok"
        assert status["last_success_at"] is not None
        storage.close()
        from nepse_trader.web.api import _state

        _state.clear()


class TestMeroShareImport:
    CSV = "Scrip,Current Balance,WACC\nNABIL,100,505.5\nSCB,50,420.0\n"

    def test_import_persists_and_shows_up_in_holdings(self, client):
        r = client.post("/api/meroshare/import", json={"csv_text": self.CSV})
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["method"] == "csv"
        assert data["holdings"] == 2

        holdings = client.get("/api/meroshare/holdings").json()
        assert [h["symbol"] for h in holdings] == ["NABIL", "SCB"]
        assert holdings[0]["wacc"] == 505.5
        assert holdings[0]["cost_basis"] == pytest.approx(50_550.0)

    def test_import_works_with_meroshare_disabled(self, client):
        """The CSV path needs no credentials, so the enabled flag is irrelevant."""
        r = client.post("/api/meroshare/import", json={"csv_text": self.CSV})
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_import_is_idempotent(self, client):
        client.post("/api/meroshare/import", json={"csv_text": self.CSV})
        client.post("/api/meroshare/import", json={"csv_text": self.CSV})
        assert len(client.get("/api/meroshare/holdings").json()) == 2

    def test_import_unrecognisable_csv_is_a_200_with_a_reason(self, client):
        r = client.post("/api/meroshare/import", json={"csv_text": "a,b,c\n1,2,3\n"})
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is False
        assert data["error"] == "MeroShare CSV import failed: missing symbol column"
        assert client.get("/api/meroshare/holdings").json() == []

    def test_import_malformed_body_is_422(self, client):
        assert client.post("/api/meroshare/import", json={}).status_code == 422
        assert (
            client.post("/api/meroshare/import", json={"csv_text": ""}).status_code == 422
        )
        assert (
            client.post("/api/meroshare/import", json={"csv_text": 42}).status_code == 422
        )


class TestMeroShareHoldings:
    def test_holdings_on_empty_db(self, empty_client):
        r = empty_client.get("/api/meroshare/holdings")
        assert r.status_code == 200
        assert r.json() == []

    def test_holdings_expose_no_credential_field(self, client):
        client.post(
            "/api/meroshare/import",
            json={"csv_text": "Scrip,Current Balance\nNABIL,10\n"},
        )
        row = client.get("/api/meroshare/holdings").json()[0]
        for key in row:
            assert "password" not in key.lower()
            assert "token" not in key.lower()

    def test_sync_history_and_compare_are_read_only_views(self, client):
        imported = client.post(
            "/api/meroshare/import",
            json={"csv_text": "Scrip,Current Balance,WACC\nNABIL,10,500\n"},
        )
        assert imported.json()["ok"] is True
        history = client.get("/api/meroshare/history").json()
        assert history[0]["method"] == "csv"
        comparison = client.get("/api/meroshare/compare").json()
        assert {"rows", "summary"} <= set(comparison)
        assert comparison["rows"][0]["symbol"] == "NABIL"


class TestMeroShareIsReadOnly:
    def test_no_order_or_ipo_endpoint_is_exposed(self):
        """The security invariant, asserted against the live route table."""
        paths = [r.path for r in app.routes if hasattr(r, "methods")]
        for path in paths:
            lowered = path.lower()
            for banned in ("order", "asba", "ipo", "apply", "bid", "buy-live", "execute"):
                assert banned not in lowered, f"{path} looks like an execution endpoint"

    def test_credentials_never_appear_in_any_meroshare_response(self, tmp_path):
        c, storage, _ = _meroshare_client(tmp_path)
        with c:
            bodies = [
                c.get("/api/meroshare/status").text,
                c.get("/api/meroshare/holdings").text,
                c.post(
                    "/api/meroshare/import",
                    json={"csv_text": "Scrip,Current Balance\nNABIL,10\n"},
                ).text,
            ]
        for body in bodies:
            assert _PASSWORD not in body
            assert _USERNAME not in body
        storage.close()
        from nepse_trader.web.api import _state

        _state.clear()

    def test_credentials_repr_stays_redacted(self):
        """Guards the assumption the status endpoint relies on."""
        creds = MeroShareCredentials("12300", _USERNAME, _PASSWORD)
        assert _PASSWORD not in repr(creds)
        assert _USERNAME not in repr(creds)
        assert _PASSWORD not in f"{creds}"
