from datetime import date
from decimal import Decimal

import httpx
import pytest

from nepse_trader.config import Settings
from nepse_trader.ingest.base import BaseClient
from nepse_trader.ingest.history import backfill_history
from nepse_trader.ingest.sharesansar import ShareSansarClient, parse_company_ref
from nepse_trader.models import CorporateAction, CorporateActionType, PriceBar, SourceName
from nepse_trader.pipeline import DailyPipeline
from nepse_trader.storage import Storage


def test_company_reference_handles_meta_and_attribute_order():
    assert parse_company_ref("<meta content='public-csrf' name='csrf-token'><div id='companyid'>16</div>") == (16, "public-csrf")
    assert parse_company_ref("<div id='companyid'>16</div>") is None


def test_history_sorts_deduplicates_and_uses_previous_valid_session():
    payload = {"data": [
        {"published_date": "2026-01-04", "close": "110"},
        {"published_date": "junk", "close": "99"},
        {"published_date": "2026-01-01", "close": "100"},
        {"published_date": "2026-01-04", "close": "111"}, None,
    ]}
    bars = ShareSansarClient.parse_price_history(payload, "nabil")
    assert len(bars) == 2
    assert bars[0].close == 111
    assert bars[0].previous_close == 100
    assert bars[0].business_date == date(2026, 1, 4)
    assert bars[1].previous_close is None
    assert ShareSansarClient.parse_price_history([], "NABIL") == []


def test_history_fetch_uses_same_session_and_source_dates(tmp_path):
    def respond(request):
        if request.method == "GET":
            return httpx.Response(200, text='<input value="csrf" name="_token"><div id="companyid">16</div>',
                                  headers={"Set-Cookie": "session=public; Path=/"})
        assert request.headers["X-CSRF-TOKEN"] == "csrf"
        assert "session=public" in request.headers["Cookie"]
        return httpx.Response(200, json={"data": [
            {"published_date": "2026-01-04", "close": "100", "traded_quantity": "1,200"},
            {"published_date": "2026-01-01", "close": "90"},
        ]})
    settings = Settings(_env_file=None, min_request_interval=0, db_path=tmp_path / "db")
    with httpx.Client(transport=httpx.MockTransport(respond)) as http:
        source = ShareSansarClient(client=BaseClient(settings, client=http, cache_raw=False))
        bars = source.fetch_company_history("NABIL", since=date(2026, 1, 3))
        assert len(bars) == 1
        assert bars[0].previous_close == 90
        assert bars[0].volume == 1200


def test_backfill_range_idempotence_isolation_and_adjustments(tmp_path):
    storage = Storage(tmp_path / "db")
    pipe = DailyPipeline(Settings(_env_file=None), storage=storage, clients=[])
    storage.upsert_corporate_action(CorporateAction(symbol="NABIL", ex_date=date(2026, 1, 4),
        action_type=CorporateActionType.BONUS, ratio_numerator=1, factor=Decimal("0.5"), source=SourceName.MANUAL))

    class Client:
        def fetch_company_history(self, symbol, since=None):
            if symbol == "BAD":
                raise RuntimeError("private response/token should never escape")
            return [PriceBar(symbol=symbol, business_date=d, close=c, open=c, high=c, low=c,
                             source=SourceName.SHARESANSAR)
                    for d, c in [(date(2026, 1, 1), 200), (date(2026, 1, 4), 100), (date(2026, 1, 5), 101)]]

    for _ in range(2):
        result = backfill_history(pipe, ["NABIL", "BAD"], until=date(2026, 1, 4), client=Client())
        assert result.bars == 2
        assert "token" not in result.errors["BAD"]
        assert result.last_date == "2026-01-04"
    prices = storage.reconciled_history("NABIL")
    assert len(prices) == 2
    assert prices[0].close == 200
    assert prices[0].adjusted_close == 100
    assert pipe.reconciled_bars("NABIL")[0].high == 100
    assert pipe.reconciled_bars("NABIL", adjusted=False)[0].close == 200
    assert storage.reconciled_history_for_date(date(2026, 1, 1))[0].adjusted_close == 100


def test_future_events_do_not_adjust_current_history(tmp_path):
    storage = Storage(tmp_path / "db")
    pipe = DailyPipeline(Settings(_env_file=None), storage=storage, clients=[])
    storage.upsert_price_bars([PriceBar(symbol="NABIL", business_date=date(2026, 1, 1),
                                      close=200, source=SourceName.SHARESANSAR)])
    storage.upsert_corporate_action(CorporateAction(symbol="NABIL", ex_date=date(2026, 2, 1),
        action_type=CorporateActionType.BONUS, ratio_numerator=1, factor=Decimal("0.5"), source=SourceName.MANUAL))
    assert pipe.reconcile(date(2026, 1, 1))[0].adjusted_close == 200


def test_backfill_rejects_invalid_range_and_offline(tmp_path):
    pipe = DailyPipeline(Settings(_env_file=None, online=False), storage=Storage(tmp_path / "db"), clients=[])
    with pytest.raises(ValueError, match="online"):
        backfill_history(pipe, ["NABIL"])
    with pytest.raises(ValueError, match="Start date"):
        backfill_history(pipe, ["NABIL"], since=date(2026, 2, 1), until=date(2026, 1, 1))


def test_sparse_live_previous_close_is_not_replaced_by_matching_old_price(tmp_path):
    storage = Storage(tmp_path / "db")
    pipe = DailyPipeline(Settings(_env_file=None), storage=storage, clients=[])
    storage.upsert_price_bars([
        PriceBar(symbol="A", business_date=date(2026, 1, 4), close=100, source=SourceName.SHARESANSAR),
        PriceBar(symbol="A", business_date=date(2026, 6, 1), close=110, previous_close=100, source=SourceName.SHARESANSAR),
    ])
    storage.upsert_corporate_action(CorporateAction(symbol="A", ex_date=date(2026, 1, 5),
        action_type=CorporateActionType.BONUS, ratio_numerator=1, factor=Decimal("0.5"), source=SourceName.MANUAL))
    pipe.reconcile(date(2026, 1, 4))
    pipe.reconcile(date(2026, 6, 1))
    latest = pipe.reconciled_bars("A")[-1]
    assert latest.previous_close == 100
    assert latest.change_percent == 10


def test_ex_date_adjusted_previous_close_is_continuous(tmp_path):
    storage = Storage(tmp_path / "db")
    pipe = DailyPipeline(Settings(_env_file=None), storage=storage, clients=[])
    storage.upsert_price_bars([
        PriceBar(symbol="A", business_date=date(2026, 1, 4), close=200, source=SourceName.SHARESANSAR),
        PriceBar(symbol="A", business_date=date(2026, 1, 5), close=100, previous_close=200, source=SourceName.SHARESANSAR),
    ])
    storage.upsert_corporate_action(CorporateAction(symbol="A", ex_date=date(2026, 1, 5),
        action_type=CorporateActionType.BONUS, ratio_numerator=1, factor=Decimal("0.5"), source=SourceName.MANUAL))
    pipe.reconcile(date(2026, 1, 4))
    pipe.reconcile(date(2026, 1, 5))
    assert pipe.reconciled_bars("A")[-1].change_percent == 0
