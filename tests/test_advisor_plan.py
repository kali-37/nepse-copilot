"""Tests for the deterministic plan engine.

The point of these tests is that Normal mode is a complete product: every
number on a card is reproducible from bars alone, with no network and no LLM
anywhere in the call graph.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from nepse_trader.advisor.plan import (
    ACCUMULATE,
    AVOID,
    HOLD,
    REDUCE,
    PlanCard,
    Skipped,
    _decide,
    build_plan_card,
    build_plan_cards,
)
from nepse_trader.analysis.costs import CostEngine
from nepse_trader.models import PriceBar, Signal, SignalAction

# A Thursday. Chosen because T+2 from here crosses the Fri/Sat NEPSE weekend,
# so a naive "+2 calendar days" answer is visibly wrong.
THURSDAY = date(2026, 8, 20)


def _bars(
    n: int = 40,
    *,
    symbol: str = "NABIL",
    start: float = 500.0,
    step: float = 2.0,
    end_date: date = THURSDAY,
    high_gap: float = 6.0,
    low_gap: float = 6.0,
) -> list[PriceBar]:
    """A synthetic uptrend with a stable true range, so the ATR is predictable."""
    out: list[PriceBar] = []
    d = end_date - timedelta(days=n - 1)
    for i in range(n):
        close = start + step * i
        out.append(
            PriceBar(
                symbol=symbol,
                business_date=d + timedelta(days=i),
                open=close - step,
                high=close + high_gap,
                low=close - low_gap,
                close=close,
                previous_close=close - step,
                volume=10_000,
                turnover=close * 10_000,
                trades=100,
                source="manual",
            )
        )
    return out


def _signal(action: SignalAction, *, strategy: str = "sma_cross", strength: float = 0.8) -> Signal:
    return Signal(
        symbol="NABIL",
        business_date=THURSDAY,
        action=action,
        strategy=strategy,
        strength=strength,
        reason="test",
        price=500.0,
    )


BUY = _signal(SignalAction.BUY)
SELL = _signal(SignalAction.SELL)
HOLD_SIG = _signal(SignalAction.HOLD)


class TestDecide:
    def test_no_signals_is_a_low_conviction_hold(self):
        action, conviction, reasons = _decide([])
        assert (action, conviction) == (HOLD, 1)
        assert reasons == []

    def test_buy_majority_accumulates(self):
        action, conviction, _ = _decide([BUY, BUY, HOLD_SIG])
        assert action == ACCUMULATE
        # Two votes plus the strength bonus (0.8 >= 0.6).
        assert conviction == 3

    def test_sell_majority_reduces(self):
        action, _, _ = _decide([SELL, SELL, BUY])
        assert action == REDUCE

    def test_weak_agreement_gets_no_strength_bonus(self):
        weak = _signal(SignalAction.BUY, strength=0.2)
        _, conviction, _ = _decide([weak, _signal(SignalAction.BUY, strength=0.3)])
        assert conviction == 2

    def test_split_panel_is_an_honest_hold(self):
        action, conviction, _ = _decide([BUY, SELL])
        assert (action, conviction) == (HOLD, 2)

    def test_conviction_is_capped_at_five(self):
        many = [_signal(SignalAction.BUY, strategy=f"s{i}") for i in range(9)]
        _, conviction, _ = _decide(many)
        assert conviction == 5

    def test_holds_are_not_listed_as_reasons(self):
        _, _, reasons = _decide([BUY, HOLD_SIG])
        assert reasons == ["sma_cross:buy"]

    def test_avoid_is_never_produced_by_the_panel(self):
        """AVOID exists for the AI vocabulary; the engine has no rule that emits it."""
        for signals in ([], [BUY], [SELL], [BUY, SELL], [BUY, BUY, SELL]):
            action, _, _ = _decide(signals)
            assert action != AVOID


class TestSkips:
    def test_too_few_bars_is_skipped_with_a_count(self):
        result = build_plan_card("NABIL", _bars(5), [BUY], equity=1_000_000)
        assert isinstance(result, Skipped)
        assert "only 5 bars" in result.reason

    def test_no_usable_close_is_skipped(self):
        bars = _bars()
        bars[-1] = bars[-1].model_copy(update={"close": None})
        result = build_plan_card("NABIL", bars, [BUY], equity=1_000_000)
        assert isinstance(result, Skipped)
        assert "close" in result.reason

    def test_zero_close_is_skipped(self):
        bars = _bars()
        bars[-1] = bars[-1].model_copy(update={"close": 0.0})
        assert isinstance(build_plan_card("N", bars, [BUY], equity=1_000_000), Skipped)

    def test_missing_highs_make_the_atr_unavailable(self):
        bars = [b.model_copy(update={"high": None}) for b in _bars()]
        result = build_plan_card("NABIL", bars, [BUY], equity=1_000_000)
        assert isinstance(result, Skipped)
        assert "ATR" in result.reason

    def test_a_buy_too_small_for_one_lot_is_skipped_not_rounded_to_zero(self):
        """Silently returning quantity 0 would print an unactionable card."""
        result = build_plan_card("NABIL", _bars(), [BUY], equity=100.0)
        assert isinstance(result, Skipped)
        assert "less than one lot" in result.reason

    def test_a_hold_with_no_affordable_size_still_gets_a_card(self):
        """Only ACCUMULATE needs a tradeable size — a hold is information either way."""
        result = build_plan_card("NABIL", _bars(), [], equity=100.0)
        assert isinstance(result, PlanCard)
        assert result.action == HOLD


class TestCardNumbers:
    @pytest.fixture
    def card(self) -> PlanCard:
        result = build_plan_card("NABIL", _bars(), [BUY, BUY], equity=1_000_000, today=THURSDAY)
        assert isinstance(result, PlanCard)
        return result

    def test_reference_price_is_the_last_close(self, card):
        assert card.reference_price == _bars()[-1].close

    def test_entry_zone_straddles_the_last_close(self, card):
        assert card.entry_low < card.reference_price < card.entry_high

    def test_stop_is_below_the_entry_zone(self, card):
        assert card.stop < card.entry_low

    def test_stop_respects_the_ten_percent_circuit(self):
        """A stop the market cannot reach in one session would understate the risk."""
        wild = _bars(high_gap=400.0, low_gap=400.0)
        result = build_plan_card("NABIL", wild, [BUY], equity=100_000_000, today=THURSDAY)
        assert isinstance(result, PlanCard)
        assert result.stop >= result.reference_price * 0.9 - 0.01

    def test_targets_are_above_the_reference_and_ordered(self, card):
        assert len(card.targets) == 2
        assert card.reference_price < card.targets[0] < card.targets[1]
        assert card.target_1 == card.targets[0]
        assert card.target_2 == card.targets[1]

    def test_quantity_is_lot_rounded(self, card):
        assert card.quantity > 0
        assert card.quantity % 10 == 0

    def test_a_custom_lot_size_is_respected(self):
        result = build_plan_card(
            "NABIL", _bars(), [BUY], equity=1_000_000, today=THURSDAY, lot_size=50
        )
        assert isinstance(result, PlanCard)
        assert result.quantity % 50 == 0

    def test_risk_per_share_is_the_entry_to_stop_distance(self, card):
        assert card.risk_per_share == pytest.approx(card.entry_high - card.stop, abs=0.01)

    def test_conviction_is_within_the_documented_range(self, card):
        assert 1 <= card.conviction <= 5

    def test_rationale_names_the_strategies_that_fired(self, card):
        assert "sma_cross" in card.rationale

    def test_a_silent_panel_says_so_rather_than_leaving_it_blank(self):
        result = build_plan_card("NABIL", _bars(), [], equity=1_000_000, today=THURSDAY)
        assert isinstance(result, PlanCard)
        assert "no strategy fired" in result.rationale

    def test_note_starts_empty_because_the_engine_never_writes_prose(self, card):
        assert card.note == ""


class TestSettlement:
    """T+2 is *trading* days. Every case here is one a naive +2 gets wrong."""

    def test_thursday_buy_settles_monday(self):
        result = build_plan_card("N", _bars(end_date=THURSDAY), [BUY], equity=1_000_000)
        assert isinstance(result, PlanCard)
        # Naive +2 calendar days would say Saturday the 22nd.
        assert result.earliest_sell_date == date(2026, 8, 24)
        assert result.earliest_sell_date.strftime("%A") == "Monday"

    def test_wednesday_buy_settles_sunday(self):
        wednesday = date(2026, 8, 19)
        result = build_plan_card("N", _bars(end_date=wednesday), [BUY], equity=1_000_000)
        assert isinstance(result, PlanCard)
        # Naive +2 would say Friday the 21st, which is not a trading day.
        assert result.earliest_sell_date == date(2026, 8, 23)

    def test_settlement_skips_a_holiday(self):
        """Christmas 2026 falls on a Friday, already a weekend — use Constitution Day."""
        from nepse_trader.calendar import add_trading_days, is_trading_day

        constitution_day = date(2026, 9, 20)
        assert not is_trading_day(constitution_day)
        # The Friday before (18th) is a weekend; trade on Thursday the 17th.
        thursday = date(2026, 9, 17)
        assert is_trading_day(thursday)
        settle = add_trading_days(thursday, 2)
        # Sun 20th is the holiday, so T+1 is Mon 21st and T+2 is Tue 22nd.
        assert settle == date(2026, 9, 22)

        result = build_plan_card("N", _bars(end_date=thursday), [BUY], equity=1_000_000)
        assert isinstance(result, PlanCard)
        assert result.earliest_sell_date == settle

    def test_settlement_lands_on_a_trading_day_for_every_weekday(self):
        from nepse_trader.calendar import is_trading_day

        for offset in range(14):
            d = date(2026, 8, 3) + timedelta(days=offset)
            result = build_plan_card("N", _bars(end_date=d), [BUY], equity=1_000_000)
            assert isinstance(result, PlanCard)
            assert is_trading_day(result.earliest_sell_date)
            assert result.earliest_sell_date > d - timedelta(days=1)

    def test_today_defaults_to_the_last_bar_not_the_wall_clock(self):
        """A report generated late still settles from the session it describes."""
        old = date(2026, 3, 10)
        result = build_plan_card("N", _bars(end_date=old), [BUY], equity=1_000_000)
        assert isinstance(result, PlanCard)
        assert result.earliest_sell_date.year == 2026
        assert result.earliest_sell_date.month == 3

    def test_explicit_today_overrides_the_bar_date(self):
        result = build_plan_card(
            "N", _bars(end_date=date(2026, 3, 10)), [BUY], equity=1_000_000, today=THURSDAY
        )
        assert isinstance(result, PlanCard)
        assert result.earliest_sell_date == date(2026, 8, 24)


class TestExpectedOutcome:
    @pytest.fixture
    def card(self) -> PlanCard:
        result = build_plan_card("NABIL", _bars(), [BUY, BUY], equity=1_000_000, today=THURSDAY)
        assert isinstance(result, PlanCard)
        return result

    def test_money_fields_are_decimal_not_float(self, card):
        for value in (
            card.gross_pnl,
            card.net_pnl,
            card.entry_cost,
            card.exit_cost,
            card.capital_gains_tax,
        ):
            assert isinstance(value, Decimal)

    def test_net_is_below_gross_because_nepal_costs_are_real(self, card):
        assert card.gross_pnl > 0
        assert card.net_pnl < card.gross_pnl

    def test_the_cost_gap_equals_the_fees_and_tax(self, card):
        gap = card.gross_pnl - card.net_pnl
        assert gap == pytest.approx(
            card.entry_cost + card.exit_cost + card.capital_gains_tax, abs=Decimal("0.02")
        )

    def test_short_holds_pay_the_higher_cgt_rate(self):
        """7.5% under a year vs 5% over it — the horizon must change the tax."""
        short = build_plan_card(
            "N", _bars(), [BUY], equity=1_000_000, today=THURSDAY, horizon_days=10
        )
        long = build_plan_card(
            "N", _bars(), [BUY], equity=1_000_000, today=THURSDAY, horizon_days=400
        )
        assert isinstance(short, PlanCard) and isinstance(long, PlanCard)
        assert short.capital_gains_tax > long.capital_gains_tax

    def test_money_is_rounded_to_paisa(self, card):
        for value in (card.gross_pnl, card.net_pnl):
            assert value == value.quantize(Decimal("0.01"))

    def test_an_injected_cost_engine_is_used(self):
        engine = CostEngine()
        result = build_plan_card(
            "N", _bars(), [BUY], equity=1_000_000, today=THURSDAY, cost_engine=engine
        )
        assert isinstance(result, PlanCard)
        assert result.net_pnl != Decimal("0.00")

    def test_a_hold_with_no_size_reports_zero_rather_than_a_fake_profit(self):
        result = build_plan_card("N", _bars(), [], equity=100.0)
        assert isinstance(result, PlanCard)
        assert result.quantity == 0
        assert result.net_pnl == Decimal("0.00")
        assert result.gross_pnl == Decimal("0.00")


class TestAsDict:
    def test_round_trips_every_field_json_safely(self):
        import json

        result = build_plan_card("NABIL", _bars(), [BUY], equity=1_000_000, today=THURSDAY)
        assert isinstance(result, PlanCard)
        payload = result.as_dict()
        json.dumps(payload)  # must not raise
        assert payload["earliest_sell_date"] == "2026-08-24"
        assert isinstance(payload["gross_pnl"], float)
        assert payload["symbol"] == "NABIL"

    def test_targets_are_copied_not_aliased(self):
        result = build_plan_card("N", _bars(), [BUY], equity=1_000_000, today=THURSDAY)
        assert isinstance(result, PlanCard)
        result.as_dict()["targets"].append(9999.0)
        assert len(result.targets) == 2


class TestBuildPlanCards:
    def test_cards_and_skips_are_returned_separately(self):
        bars = {"GOOD": _bars(symbol="GOOD"), "SHORT": _bars(3, symbol="SHORT")}
        cards, skipped = build_plan_cards(
            ["GOOD", "SHORT"],
            lambda s: bars[s],
            lambda s: [BUY],
            equity=1_000_000,
            today=THURSDAY,
        )
        assert [c.symbol for c in cards] == ["GOOD"]
        assert [s.symbol for s in skipped] == ["SHORT"]

    def test_an_empty_symbol_list_yields_nothing_and_raises_nothing(self):
        cards, skipped = build_plan_cards(
            [], lambda s: [], lambda s: [], equity=1_000_000, today=THURSDAY
        )
        assert (cards, skipped) == ([], [])

    def test_kwargs_reach_the_individual_cards(self):
        cards, _ = build_plan_cards(
            ["A"],
            lambda s: _bars(symbol=s),
            lambda s: [BUY],
            equity=1_000_000,
            today=THURSDAY,
            horizon_days=33,
        )
        assert cards[0].horizon_days == 33

    def test_callables_are_invoked_once_per_symbol(self):
        seen: list[str] = []

        def bars_for(symbol: str):
            seen.append(symbol)
            return _bars(symbol=symbol)

        build_plan_cards(
            ["A", "B", "C"], bars_for, lambda s: [], equity=1_000_000, today=THURSDAY
        )
        assert seen == ["A", "B", "C"]


class TestNoNetworkAndNoLLM:
    """The load-bearing guarantee: Normal mode is fully offline."""

    def test_building_a_card_makes_no_http_call(self, monkeypatch):
        import httpx

        def explode(*args, **kwargs):
            raise AssertionError("the deterministic engine must not touch the network")

        monkeypatch.setattr(httpx.Client, "request", explode)
        monkeypatch.setattr(httpx.Client, "send", explode)
        result = build_plan_card("NABIL", _bars(), [BUY], equity=1_000_000, today=THURSDAY)
        assert isinstance(result, PlanCard)

    def test_building_a_card_spawns_no_subprocess(self, monkeypatch):
        """The Claude leg is a subprocess; the engine must never reach it."""
        import subprocess

        def explode(*args, **kwargs):
            raise AssertionError("the deterministic engine must not spawn a subprocess")

        monkeypatch.setattr(subprocess, "run", explode)
        monkeypatch.setattr(subprocess, "Popen", explode)
        result = build_plan_card("NABIL", _bars(), [BUY], equity=1_000_000, today=THURSDAY)
        assert isinstance(result, PlanCard)

    def test_the_plan_module_imports_nothing_from_the_ai_package(self):
        import nepse_trader.advisor.plan as plan

        source = plan.__file__
        with open(source, encoding="utf-8") as fh:
            text = fh.read()
        assert "nepse_trader.ai" not in text


class TestDeterminism:
    def test_the_same_inputs_give_byte_identical_cards(self):
        args = dict(equity=1_000_000, today=THURSDAY)
        first = build_plan_card("NABIL", _bars(), [BUY, BUY], **args)
        second = build_plan_card("NABIL", _bars(), [BUY, BUY], **args)
        assert isinstance(first, PlanCard) and isinstance(second, PlanCard)
        assert first.as_dict() == second.as_dict()

    def test_more_equity_buys_more_shares(self):
        small = build_plan_card("N", _bars(), [BUY], equity=1_000_000, today=THURSDAY)
        large = build_plan_card("N", _bars(), [BUY], equity=10_000_000, today=THURSDAY)
        assert isinstance(small, PlanCard) and isinstance(large, PlanCard)
        assert large.quantity > small.quantity

    def test_higher_volatility_widens_the_entry_zone(self):
        calm = build_plan_card(
            "N", _bars(high_gap=2.0, low_gap=2.0), [BUY], equity=1_000_000, today=THURSDAY
        )
        rough = build_plan_card(
            "N", _bars(high_gap=20.0, low_gap=20.0), [BUY], equity=1_000_000, today=THURSDAY
        )
        assert isinstance(calm, PlanCard) and isinstance(rough, PlanCard)
        assert (rough.entry_high - rough.entry_low) > (calm.entry_high - calm.entry_low)
