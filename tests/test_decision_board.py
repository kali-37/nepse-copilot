"""Financial and date boundaries of the decision-first dashboard."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from math import sin

import pytest
from fastapi.testclient import TestClient
from freezegun import freeze_time

from nepse_trader.advisor.decision_signals import (
    ChartState,
    chart_states,
    evidence_confidence,
    historical_evidence,
)
from nepse_trader.advisor.decisions import build_decisions
from nepse_trader.advisor.positions import available_cash, owned_positions, record_trade, set_cash
from nepse_trader.analysis.costs import CostEngine
from nepse_trader.calendar import add_trading_days
from nepse_trader.config import Settings
from nepse_trader.ingest.reconcile import reconcile_bars
from nepse_trader.models import (
    CorporateAction,
    CorporateActionType,
    FundamentalData,
    OrderSide,
    PriceBar,
    SourceName,
)
from nepse_trader.pipeline import DailyPipeline
from nepse_trader.storage import Storage
from nepse_trader.web.api import _state, app
from nepse_trader.web.jobs import registry

TODAY = date(2026, 11, 20)
LAST = date(2026, 11, 19)


@pytest.fixture
def pipe(tmp_path):
    storage = Storage(tmp_path / 'decisions.db')
    settings = Settings(_env_file=None, db_path=storage.db_path, online=False)
    p = DailyPipeline(settings, storage, clients=[])
    days = [LAST]
    from datetime import timedelta

    from nepse_trader.calendar import previous_trading_day
    for _ in range(159):
        days.append(previous_trading_day(days[-1] - timedelta(days=1)))
    rows = []
    for symbol, slope in [('AAA', .7), ('BBB', .9), ('CCC', .5), ('DDD', 1.2), ('EEE', 1.1), ('FFF', .6)]:
        for i, day in enumerate(reversed(days)):
            close = 100 + i * slope + sin(i / 4)
            for source in [SourceName.SHARESANSAR, SourceName.CHUKUL]:
                rows.append(PriceBar(symbol=symbol, business_date=day, open=close-.5, high=close+1,
                                     low=close-1, close=close, volume=30000+i*50, source=source))
    storage.upsert_price_bars(rows)
    storage.upsert_reconciled(reconcile_bars(rows))
    for symbol in ['AAA','BBB','CCC','DDD','EEE','FFF']:
        storage.upsert_fundamental(FundamentalData(symbol=symbol,eps=15,book_value=200), LAST)
    yield p
    storage.close()


def test_scores_vary_with_evidence_and_quality_and_stay_bounded():
    strong = ChartState(120, 2, 55, 110, 100, .03, 1.5, 30000)
    weak = ChartState(90, 2, 80, 100, 110, -.04, .3, 300)
    good = evidence_confidence(strong, 3, 18, 20, .95)
    bad = evidence_confidence(weak, 3, 3, 20, .5)
    assert 0 <= bad['value'] < good['value'] <= .9
    assert good['historical_samples'] == 20 and good['historical_hits'] == 18
    assert '100-share benchmark' in good['basis']
    assert evidence_confidence(strong, 3, 18, 20, .4)['value'] < good['value']


def test_budget_shared_daily_monthly_and_dates_honest(pipe):
    with freeze_time('2026-11-20 03:00:00'):
        board = build_decisions(pipe)
    assert board['session'] == 'trading_day' and not board['stale']
    assert board['market_date'] == LAST.isoformat() and board['requested_date'] == TODAY.isoformat()
    ideas = board['buys']['day'] + board['buys']['month']
    assert ideas and board['buys']['month']
    assert len({i['symbol'] for i in ideas}) == len(ideas)
    assert sum(Decimal(str(i['outlay'])) for i in ideas) <= available_cash(pipe.storage)
    assert all(i['quantity'] % 10 == 0 and i['estimated_net'] > 0 for i in ideas)
    assert all(i['earliest_sell_date'] == '2026-11-24' for i in ideas)
    assert all(i['horizon_days'] == 3 for i in board['buys']['day'])
    assert all(i['horizon_days'] == 22 for i in board['buys']['month'])


def test_preopen_previous_session_usable_and_postclose_entry_moves(pipe):
    with freeze_time('2026-11-20 03:00:00'):  # 08:45 NPT before Friday open
        board = build_decisions(pipe)
    assert board['session_phase'] == 'pre_open' and not board['stale']
    assert board['earliest_entry_date'] == '2026-11-20'
    with freeze_time('2026-11-20 10:00:00'):  # 15:45 NPT
        board = build_decisions(pipe)
    assert board['session_phase'] == 'after_close'
    assert board['earliest_entry_date'] == '2026-11-23'


def test_saved_exit_does_not_move_and_target_triggers_sell(pipe):
    with freeze_time('2026-11-20'):
        record_trade(pipe, symbol='AAA', side='buy', quantity=100, price=Decimal('100'),
                     bought_on=date(2026, 1, 1), stop=95, target=120)
        first = build_decisions(pipe)
        second = build_decisions(pipe)
    for b in [first, second]:
        held = b['holdings'][0]
        assert held['stop'] == 95 and held['target'] == 120 and held['action'] == 'sell'
        assert held['net_exit_pnl'] is not None
        assert all(i['symbol'] != 'AAA' for items in b['buys'].values() for i in items)


def test_tiny_buy_does_not_trigger_fee_induced_stop(pipe):
    with freeze_time('2026-11-20'):
        record_trade(pipe, symbol='TINY', side='buy', quantity=1, price=Decimal('100'), bought_on=LAST)
    p = next(p for p in owned_positions(pipe) if p['symbol'] == 'TINY')
    assert p['stop'] < 100 < p['target']
    sell = CostEngine().compute(OrderSide.SELL, p['target'], 1, buy_cost_basis=Decimal(p['cost_basis']))
    assert sell.net_amount > Decimal(p['cost_basis'])


def test_stale_and_short_history_quotes_are_reviewed(pipe):
    with freeze_time('2026-11-20'):
        record_trade(pipe, symbol='SHORT', side='buy', quantity=10, price=Decimal('100'), bought_on=LAST)
        row = PriceBar(symbol='SHORT', business_date=LAST, close=100, high=101, low=99, source=SourceName.CHUKUL)
        pipe.storage.upsert_reconciled(reconcile_bars([row]))
        held = next(p for p in build_decisions(pipe)['holdings'] if p['symbol'] == 'SHORT')
        assert held['reference_price'] == 100 and held['action'] == 'review'
    with freeze_time('2026-11-23 12:00:00'):
        stale = build_decisions(pipe)
    assert stale['stale'] and not stale['buys']['day'] and not stale['buys']['month']
    assert all(p['action'] == 'review' for p in stale['holdings'])


def test_missing_basis_preserved_on_topup_and_sale(pipe):
    with pipe.storage._tx() as conn:
        conn.execute("INSERT INTO tracked_positions(symbol,quantity,cost_basis,horizon_days,updated_at) VALUES('UNKNOWN',100,NULL,22,'now')")
    with freeze_time('2026-11-20'):
        record_trade(pipe, symbol='UNKNOWN', side='buy', quantity=10, price=Decimal('200'), bought_on=LAST)
        p = next(p for p in owned_positions(pipe) if p['symbol'] == 'UNKNOWN')
        assert p['cost_basis'] is None and p['stop'] < 200 < p['target']
        record_trade(pipe, symbol='UNKNOWN', side='sell', quantity=10, price=Decimal('210'), bought_on=LAST)
        assert next(p for p in owned_positions(pipe) if p['symbol'] == 'UNKNOWN')['cost_basis'] is None


def test_reject_oversell_and_invalid_prices_without_mutation(pipe):
    with freeze_time('2026-11-20'):
        record_trade(pipe, symbol='AAA', side='buy', quantity=10, price=Decimal('100'), bought_on=LAST)
        cash = available_cash(pipe.storage)
        for values in [dict(side='sell', quantity=11), dict(side='buy', quantity=10, price=Decimal('NaN')),
                       dict(side='buy', quantity=10, stop=float('inf'))]:
            args = dict(symbol='AAA', price=Decimal('100'), bought_on=LAST)
            args.update(values)
            with pytest.raises(ValueError):
                record_trade(pipe, **args)
        assert available_cash(pipe.storage) == cash
        assert owned_positions(pipe)[0]['quantity'] == 10
        assert pipe.storage._conn.execute('SELECT COUNT(*) FROM position_records').fetchone()[0] == 1


def test_concurrent_buys_preserve_both_cash_and_quantity(pipe):
    def buy(_):
        with Storage(pipe.storage.db_path) as storage:
            p = DailyPipeline(pipe.settings, storage, clients=[])
            return record_trade(p, symbol='AAA', side='buy', quantity=10, price=Decimal('100'), bought_on=LAST)
    with ThreadPoolExecutor(2) as pool:
        list(pool.map(buy, [1, 2]))
    assert owned_positions(pipe)[0]['quantity'] == 20
    fee = CostEngine().compute(OrderSide.BUY, Decimal('100'), 10).net_amount
    assert available_cash(pipe.storage) == Decimal(100000) - 2 * fee


def test_sold_tombstone_does_not_resurrect_mirror(pipe, monkeypatch):
    from types import SimpleNamespace
    holding = SimpleNamespace(symbol='AAA', current_balance=10, cost_basis=Decimal(1000), last_transaction_date=None)
    monkeypatch.setattr('nepse_trader.advisor.positions.stored_holdings', lambda _: [holding])
    with freeze_time('2026-11-20'):
        record_trade(pipe, symbol='AAA', side='sell', quantity=10, price=Decimal('120'), bought_on=LAST)
    assert not owned_positions(pipe)


def test_long_term_sale_uses_actual_calendar_holding_days(pipe):
    with freeze_time('2026-11-20'):
        record_trade(pipe, symbol='AAA', side='buy', quantity=100, price=Decimal('100'), bought_on=date(2024, 1, 1))
        basis = Decimal(owned_positions(pipe)[0]['cost_basis'])
        cash = available_cash(pipe.storage)
        record_trade(pipe, symbol='AAA', side='sell', quantity=100, price=Decimal('200'), bought_on=LAST)
    expected = CostEngine().compute(OrderSide.SELL, Decimal('200'), 100, buy_cost_basis=basis, holding_days=1053)
    assert available_cash(pipe.storage) == cash + expected.net_amount


def test_corporate_action_suppresses_false_stop_exit(pipe):
    with freeze_time('2026-11-20'):
        record_trade(pipe, symbol='AAA', side='buy', quantity=100, price=Decimal('100'), bought_on=date(2026, 1, 1))
        pipe.storage.upsert_corporate_action(CorporateAction(symbol='AAA', ex_date=date(2026, 11, 1),
            action_type=CorporateActionType.BONUS, ratio_numerator=1, ratio_denominator=1,
            factor=Decimal('.5'), source=SourceName.MANUAL))
        held = build_decisions(pipe)['holdings'][0]
    assert held['action'] == 'review' and 'corporate action' in held['reason']


def test_historical_evidence_never_uses_same_session_target_or_overlap():
    days = [add_trading_days(date(2026, 1, 4), i) for i in range(100)]
    bars = [PriceBar(symbol='A', business_date=d, open=100, close=100, high=105, low=99.9,
                     volume=3000, source=SourceName.MANUAL) for d in days]
    # Only each setup's entry-session candle spikes above target; the two
    # later candles are flat. Early exits would make this history look perfect.
    for i, bar in enumerate(bars):
        bar.high = 105 if i % 4 == 2 else 100
    states = [ChartState(100, 1, 55, 99, 98, .01, 1, 3000) if i % 4 == 1 else None for i in range(100)]
    states[-1] = states[49]
    hits, total = historical_evidence(bars, states, 3)
    assert total > 0 and hits == 0
    assert total <= (100-49)//4


def test_incomplete_ohlc_does_not_invent_volatility():
    rows = [PriceBar(symbol='A', business_date=add_trading_days(date(2026,1,4), i), close=100+i,
                     source=SourceName.MANUAL) for i in range(80)]
    assert chart_states(rows)[-1] is None


def test_cash_zero_produces_no_forced_buys(pipe):
    set_cash(pipe.storage, Decimal(0))
    assert build_decisions(pipe, today=TODAY)['buys'] == {'day': [], 'month': []}


def test_api_records_actual_trades_and_offline_refresh_never_fetches(pipe, monkeypatch):
    _state.update(storage=pipe.storage, settings=pipe.settings)
    registry.reset()
    monkeypatch.setattr(DailyPipeline, 'ingest', lambda *a, **k: pytest.fail('offline network call'))
    with freeze_time('2026-11-20'), TestClient(app) as client:
        board = client.get('/api/decisions').json()
        assert board['market_date'] == LAST.isoformat()
        response = client.post('/api/decisions/trades', json={'symbol':'AAA','side':'buy','quantity':10,'price':100,'business_date':LAST.isoformat()})
        assert response.status_code == 200 and response.json()['record']['order_submitted'] is False
        assert response.json()['board']['holdings'][0]['symbol'] == 'AAA'
        assert client.post('/api/decisions/trades', json={'symbol':'AAA','side':'sell','quantity':100,'price':120,'business_date':LAST.isoformat()}).status_code == 400
        assert client.put('/api/decisions/cash', json={'cash':-1}).status_code == 422
        assert client.put('/api/decisions/cash', json={'cash':250000}).json()['available_cash'] == 250000
        job = client.post('/api/jobs',json={'kind':'refresh-today'}).json()
        registry.join(job['id'])
        status = client.get(f"/api/jobs/{job['id']}").json()
        assert status['status'] == 'failed' and 'Online mode is disabled' in status['error']
    registry.reset()
    _state.clear()


def test_refresh_isolates_source_failures_and_reconciles_published_dates(pipe, monkeypatch):
    from nepse_trader.ingest.base import SourceClient
    from nepse_trader.web.jobs import JobContext
    class Good(SourceClient):
        name = SourceName.CHUKUL
        def fetch_prices(self, business_date=None):
            assert business_date is None
            return [PriceBar(symbol='AAA', business_date=LAST, open=201, high=205, low=200, close=203,
                             volume=35000, source=self.name)]
        def fetch_indices(self, business_date=None):
            return []
    class Bad(Good):
        name = SourceName.SHARESANSAR
        def fetch_prices(self, business_date=None):
            raise RuntimeError('source unavailable')
    pipe.settings.online = True
    pipe.clients = [Good(), Bad()]
    monkeypatch.setattr(JobContext, 'pipeline', lambda self, **kwargs: pipe)
    monkeypatch.setattr('nepse_trader.ingest.fundamentals.MeroLaganiFundamentalsClient.fetch_fundamentals', lambda *a: None)
    monkeypatch.setattr('nepse_trader.ingest.chukul.ChukulClient.fetch_floorsheet', lambda *a: [])
    registry.reset()
    with freeze_time('2026-11-20'):
        job = registry.submit('refresh-today', {}, pipe.settings)
        registry.join(job.id)
    status = registry.snapshot(job.id)
    assert status['status'] == 'done', status['error']
    board = status['result']['board']
    assert board['market_date'] == LAST.isoformat() and board['refresh']['sources']['chukul'] == 1
    assert status['result']['ingest']['business_dates'] == [LAST.isoformat()]
    assert any('sharesansar' in w for w in status['result']['warnings'])
    assert [s['status'] for s in status['stages']] == ['ok'] * 6
    assert not pipe.storage.bars_for_date(TODAY)
    registry.reset()


def test_cached_advice_is_invalidated_by_purchase_even_if_cash_remains_zero(pipe):
    from nepse_trader.advisor.decision_state import decision_state
    from nepse_trader.advisor.decisions import DecisionsChanged, publish_decisions, save_decisions
    set_cash(pipe.storage, Decimal(0))
    with freeze_time('2026-11-20'):
        old = publish_decisions(pipe)
        record_trade(pipe, symbol='AAA', side='buy', quantity=10, price=Decimal('100'), bought_on=LAST)
        assert available_cash(pipe.storage) == 0
        assert old['state_key'] != decision_state(pipe, TODAY)
        with pytest.raises(DecisionsChanged):
            save_decisions(pipe, old)
        new = publish_decisions(pipe, old)
    assert new['holdings'][0]['symbol'] == 'AAA'


def test_first_reconciliation_during_analysis_retries_instead_of_missing_metadata_error(pipe, monkeypatch):
    from nepse_trader.advisor.decisions import DecisionsChanged, publish_decisions

    raw = PriceBar(symbol='LATE',business_date=LAST,open=100,high=102,low=99,close=100,
        volume=30000,source=SourceName.MANUAL)
    pipe.storage.upsert_price_bars([raw])
    original = pipe.reconciled_bars
    changed = False

    def raced(symbol, **kwargs):
        nonlocal changed
        if symbol == 'LATE' and not changed:
            changed = True
            pipe.storage.upsert_reconciled(reconcile_bars([raw]))
        return original(symbol,**kwargs)

    monkeypatch.setattr(pipe,'reconciled_bars',raced)
    with freeze_time('2026-11-20'):
        with pytest.raises(DecisionsChanged):
            build_decisions(pipe)
        board = publish_decisions(pipe)
    assert changed and board['market_date'] == LAST.isoformat()


def test_refresh_report_survives_retry_and_later_concurrent_publication(pipe):
    import json

    from nepse_trader.advisor.decisions import publish_decisions

    with freeze_time('2026-11-20 15:00:00'):
        old_reader = build_decisions(pipe)
        refresh_board = build_decisions(pipe)
        refresh_board['refresh'] = {'sources': {'chukul': 1}, 'warnings': ['history unavailable']}
        # A real mutation invalidates the worker's first analysis.
        set_cash(pipe.storage, Decimal(120000))
    with freeze_time('2026-11-20 15:01:00'):
        refreshed = publish_decisions(pipe, refresh_board)
        assert refreshed['refresh'] == refresh_board['refresh']
    with freeze_time('2026-11-20 15:02:00'):
        latest = publish_decisions(pipe, old_reader)
        assert latest['refresh'] == refreshed['refresh']
        assert latest['available_cash'] == 120000
        stored = pipe.storage._conn.execute(
            'SELECT payload FROM decision_runs ORDER BY generated_at DESC LIMIT 1'
        ).fetchone()
        assert json.loads(stored[0])['id'] == latest['id']
        assert latest['generated_at'] > refreshed['generated_at']


def test_changing_market_returns_actionable_conflict_instead_of_server_error(pipe, monkeypatch):
    from nepse_trader.advisor.decisions import DecisionsChanged

    def changing(*args):
        raise DecisionsChanged('Market changed')

    monkeypatch.setattr('nepse_trader.web.decisions.publish_decisions', changing)
    _state.update(storage=pipe.storage, settings=pipe.settings)
    with freeze_time('2026-11-20'), TestClient(app) as client:
        response = client.get('/api/decisions')
        assert response.status_code == 409
        assert 'refresh to finish' in response.json()['detail']
    _state.clear()


def test_mutation_conflicts_report_saved_changes_and_keep_trade_retry_idempotent(pipe, monkeypatch):
    from nepse_trader.advisor.decisions import DecisionsChanged

    def changing(*args):
        raise DecisionsChanged('Market changed')

    monkeypatch.setattr('nepse_trader.web.decisions.publish_decisions', changing)
    _state.update(storage=pipe.storage, settings=pipe.settings)
    with freeze_time('2026-11-20'), TestClient(app) as client:
        cash = client.put('/api/decisions/cash', json={'cash': 120000})
        assert cash.status_code == 409 and 'cash was saved' in cash.json()['detail']
        assert available_cash(pipe.storage) == 120000
        trade = {'symbol': 'AAA', 'side': 'buy', 'quantity': 10, 'price': 100,
                 'business_date': LAST.isoformat(), 'record_id': 'b' * 32}
        for _ in range(2):
            response = client.post('/api/decisions/trades', json=trade)
            assert response.status_code == 409 and 'recorded successfully' in response.json()['detail']
        assert owned_positions(pipe)[0]['quantity'] == 10
        assert pipe.storage._conn.execute('SELECT COUNT(*) FROM position_records').fetchone()[0] == 1
        plan = client.put('/api/decisions/holdings/AAA/plan', json={
            'quantity': 10, 'stop': 90, 'target': 150, 'horizon_days': 22
        })
        assert plan.status_code == 409 and 'exit plan was saved' in plan.json()['detail']
        assert owned_positions(pipe)[0]['stop'] == 90
    _state.clear()


def test_retry_same_execution_id_does_not_double_purchase(pipe):
    args = dict(symbol='AAA', side='buy', quantity=10, price=Decimal('100'), bought_on=LAST,
                record_id='a'*32)
    with freeze_time('2026-11-20'):
        first = record_trade(pipe, **args)
        second = record_trade(pipe, **args)
        with pytest.raises(ValueError):
            record_trade(pipe, **{**args, 'quantity':20})
    assert first['available_cash'] == second['available_cash']
    assert second['already_recorded']
    assert owned_positions(pipe)[0]['quantity'] == 10


def test_asof_board_excludes_future_price_rows(pipe):
    future = PriceBar(symbol='AAA', business_date=date(2027,1,1), open=900,high=1000,low=800,close=950,
                      volume=30000,source=SourceName.CHUKUL)
    pipe.storage.upsert_reconciled(reconcile_bars([future]))
    with freeze_time('2026-11-20'):
        board = build_decisions(pipe)
    assert board['market_date'] == LAST.isoformat()
    assert all(point['date'] <= TODAY.isoformat() for ideas in board['buys'].values() for idea in ideas for point in idea['chart'])


def test_existing_holding_exit_plan_preserves_shares_and_cash(pipe):
    from nepse_trader.advisor.positions import set_position_plan
    with freeze_time('2026-11-20'):
        record_trade(pipe, symbol='AAA', side='buy', quantity=10, price=Decimal('100'), bought_on=LAST)
        cash = available_cash(pipe.storage)
        set_position_plan(pipe, symbol='AAA', quantity=10, stop=98, target=140, average_cost=Decimal('104'), bought_on=LAST)
        held = owned_positions(pipe)[0]
        assert held['quantity'] == 10 and held['cost_basis'] == '1040.00'
        assert held['stop'] == 98 and held['target'] == 140
        assert available_cash(pipe.storage) == cash
        assert pipe.storage._conn.execute('SELECT COUNT(*) FROM position_records').fetchone()[0] == 1


def test_historical_high_low_corrections_invalidate_cached_evidence(pipe):
    from nepse_trader.advisor.decision_state import decision_state
    with freeze_time('2026-11-20'):
        before = decision_state(pipe, TODAY)
        history = pipe.storage.reconciled_history('AAA')
        history[30].high += 4
        pipe.storage.upsert_reconciled([history[30]])
        assert decision_state(pipe, TODAY) != before


def test_live_bar_is_not_a_completed_historical_expiry(pipe):
    bars = pipe.reconciled_bars('AAA')
    states = chart_states(bars)
    _, mature = historical_evidence(bars, states, 3, completed_through=bars[80].business_date)
    _, all_windows = historical_evidence(bars, states, 3)
    assert mature < all_windows


def test_future_quote_and_corporate_action_do_not_change_asof_scores(pipe):
    with freeze_time('2026-11-20'):
        before = build_decisions(pipe)
        future = PriceBar(symbol='AAA', business_date=date(2027,1,1), open=900, high=1000, low=800,
                          close=950, volume=30000, source=SourceName.CHUKUL)
        pipe.storage.upsert_reconciled(reconcile_bars([future]))
        pipe.storage.upsert_corporate_action(CorporateAction(symbol='AAA', ex_date=date(2027,1,2),
            action_type=CorporateActionType.BONUS, ratio_numerator=1,ratio_denominator=1,
            factor=Decimal('.5'),source=SourceName.MANUAL))
        pipe.refresh_adjustments({'AAA'})
        after = build_decisions(pipe)
    assert before['buys'] == after['buys']


def test_zero_live_quote_is_unavailable_not_a_stop_hit(pipe):
    with freeze_time('2026-11-20'):
        record_trade(pipe, symbol='ZERO', side='buy', quantity=10, price=Decimal('100'), bought_on=LAST)
        zero = PriceBar(symbol='ZERO',business_date=LAST,close=0,high=0,low=0,source=SourceName.CHUKUL)
        pipe.storage.upsert_reconciled(reconcile_bars([zero]))
        held = next(p for p in build_decisions(pipe)['holdings'] if p['symbol'] == 'ZERO')
    assert held['action'] == 'review' and held['reference_price'] is None


def test_wacc_plan_edit_then_topup_preserves_gross_entry_and_stop(pipe):
    from nepse_trader.advisor.positions import set_position_plan
    with freeze_time('2026-11-20'):
        record_trade(pipe, symbol='TINY', side='buy', quantity=1, price=Decimal('100'), bought_on=LAST)
        p = owned_positions(pipe)[0]
        set_position_plan(pipe, symbol='TINY', quantity=1, stop=p['stop'], target=p['target'],
                          average_cost=Decimal(p['cost_basis']))
        record_trade(pipe, symbol='TINY', side='buy', quantity=1, price=Decimal('100'), bought_on=LAST)
        held = owned_positions(pipe)[0]
    assert held['entry_price'] == 100 and held['stop'] < 100
