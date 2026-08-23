"""Tests for nepse_trader.reporting — all pure, no network."""

from __future__ import annotations

from datetime import date

import httpx
import pytest

from nepse_trader.models import (
    PriceBar,
    ReconciledPrice,
    Signal,
    SignalAction,
    SourceName,
)
from nepse_trader.reporting import (
    RASHIFAL_DISCLAIMER,
    Alerter,
    backtest_report,
    do_not_touch_md,
    plan_cards_md,
    portfolio_summary,
    price_bars_markdown,
    rashifal_md,
    reconciliation_report,
    sell_queue_md,
    signals_markdown,
    signals_table,
    write_markdown_report,
)


def _signal() -> Signal:
    return Signal(
        symbol="nabil",
        business_date=date(2026, 6, 10),
        action=SignalAction.BUY,
        strategy="sma_cross",
        strength=0.8,
        reason="fast above slow",
        price=512.5,
    )


def test_signals_markdown_has_header_and_row():
    md = signals_markdown([_signal()])
    assert "| Symbol | Action | Strategy | Strength | Price | Reason |" in md
    assert "| --- | --- | --- | --- | --- | --- |" in md
    # symbol auto-uppercased by the model
    assert "| NABIL | BUY | sma_cross | 0.80 | 512.50 | fast above slow |" in md


def test_signals_markdown_empty():
    md = signals_markdown([])
    assert "_no signals_" in md
    # header still present
    assert "| Symbol | Action | Strategy | Strength | Price | Reason |" in md


def test_signals_markdown_escapes_pipe():
    s = _signal()
    s = s.model_copy(update={"reason": "a|b crossing"})
    md = signals_markdown([s])
    assert "a\\|b crossing" in md
    # exactly one data row pipe-structure preserved
    assert md.count("| BUY |") == 1


def test_signals_table_renders_string():
    out = signals_table([_signal()])
    assert isinstance(out, str)
    assert "NABIL" in out
    assert "Signals" in out  # title
    assert "Symbol" in out and "Reason" in out


def test_reconciliation_report_flags_low_confidence():
    good = ReconciledPrice(
        symbol="NABIL",
        business_date=date(2026, 6, 10),
        close=500.0,
        sources_agreeing=[SourceName.SHARESANSAR, SourceName.MEROLAGANI],
        confidence=0.9,
    )
    bad = ReconciledPrice(
        symbol="ADBL",
        business_date=date(2026, 6, 10),
        close=250.0,
        sources_agreeing=[SourceName.CHUKUL],
        disputed_fields=["close", "volume"],
        confidence=0.3,
    )
    md = reconciliation_report([good, bad])
    assert "| Symbol | Close | Confidence | Sources Agreeing | Disputed Fields | Flag |" in md
    # good row marked OK
    assert "| NABIL | 500.00 | 0.90 | sharesansar, merolagani | - | OK |" in md
    # bad row flagged (low confidence AND disputed fields)
    assert "ADBL" in md
    assert "⚠️" in md
    assert "close, volume" in md


def test_reconciliation_report_flags_disputed_even_if_confident():
    p = ReconciledPrice(
        symbol="HBL",
        business_date=date(2026, 6, 10),
        close=300.0,
        sources_agreeing=[SourceName.SHARESANSAR, SourceName.MEROLAGANI],
        disputed_fields=["high"],
        confidence=0.9,
    )
    md = reconciliation_report([p])
    assert "⚠️" in md
    assert "OK |" not in md.split("\n")[-1]


def test_reconciliation_report_empty():
    md = reconciliation_report([])
    assert "_no prices_" in md


def test_portfolio_summary_metrics_and_positions():
    summary = {
        "cash": 100000.0,
        "equity": 251250.0,
        "realized_pnl": 1234.5,
        "unrealized_pnl": -560.0,
        "positions": [
            {"symbol": "NABIL", "quantity": 100, "avg_cost": 500.0},
            {"symbol": "ADBL", "quantity": 50, "avg_cost": 250.0},
        ],
    }
    md = portfolio_summary(summary)
    assert "| Cash | 100000.00 |" in md
    assert "| Equity | 251250.00 |" in md
    assert "| Realized PnL | 1234.50 |" in md
    assert "| Unrealized PnL | -560.00 |" in md
    assert "| Symbol | Quantity | Avg Cost | Cost Basis |" in md
    # cost basis = 100 * 500 = 50000
    assert "| NABIL | 100 | 500.00 | 50000.00 |" in md
    assert "| ADBL | 50 | 250.00 | 12500.00 |" in md


def test_portfolio_summary_no_positions():
    md = portfolio_summary({"cash": 0.0, "equity": 0.0, "realized_pnl": 0.0, "unrealized_pnl": 0.0})
    assert "_no positions_" in md


def test_backtest_report_substrings():
    summary = {
        "total_return_pct": 23.4,
        "cagr_pct": 11.1,
        "max_drawdown_pct": -8.2,
        "sharpe": 1.45,
        "num_trades": 42,
        "win_rate_pct": 57.1,
    }
    md = backtest_report(summary)
    assert "| Total Return % | 23.40 |" in md
    assert "| CAGR % | 11.10 |" in md
    assert "| Max Drawdown % | -8.20 |" in md
    assert "| Sharpe | 1.45 |" in md
    assert "| Num Trades | 42 |" in md
    assert "| Win Rate % | 57.10 |" in md


def test_backtest_report_handles_missing_keys():
    md = backtest_report({})
    # missing -> "-" placeholder, no crash
    assert "| Sharpe | - |" in md


def test_price_bars_markdown():
    bar = PriceBar(
        symbol="nabil",
        business_date=date(2026, 6, 10),
        open=500.0,
        high=520.0,
        low=495.0,
        close=512.5,
        volume=1000,
        source=SourceName.SHARESANSAR,
    )
    md = price_bars_markdown([bar])
    assert "| NABIL | 2026-06-10 | 500.00 | 520.00 | 495.00 | 512.50 | 1000 | sharesansar |" in md


def test_write_markdown_report(tmp_path):
    sections = {
        "Signals": signals_markdown([_signal()]),
        "Backtest": backtest_report({"sharpe": 1.0}),
    }
    out = tmp_path / "report.md"
    write_markdown_report(out, sections)
    text = out.read_text(encoding="utf-8")
    assert text.startswith("# NEPSE Trader Daily Report")
    assert "## Signals" in text
    assert "## Backtest" in text
    assert "NABIL" in text
    assert "| Sharpe | 1.00 |" in text


def test_write_markdown_report_creates_parent_dirs(tmp_path):
    out = tmp_path / "nested" / "deep" / "report.md"
    write_markdown_report(out, {"Empty": "body"})
    assert out.exists()
    assert "## Empty" in out.read_text(encoding="utf-8")


def test_alerter_no_webhook_returns_false_no_network(monkeypatch):
    def _boom(*args, **kwargs):
        raise AssertionError("httpx must not be called without a webhook")

    # Any httpx network entry point would explode if touched.
    monkeypatch.setattr(httpx, "post", _boom)
    monkeypatch.setattr(httpx, "Client", _boom)

    alerter = Alerter()
    assert alerter.send("title", "body") is False


def test_alerter_with_webhook_posts(monkeypatch):
    captured: dict = {}

    def fake_post(payload):
        captured["payload"] = payload
        return httpx.Response(200, request=httpx.Request("POST", "https://hook.example/x"))

    alerter = Alerter(webhook_url="https://hook.example/x")
    monkeypatch.setattr(alerter, "_post", fake_post)
    assert alerter.send("hello", "world") is True
    assert captured["payload"] == {"title": "hello", "body": "world"}


def test_alerter_with_webhook_failure_returns_false(monkeypatch):
    def fake_post(payload):
        return httpx.Response(500, request=httpx.Request("POST", "https://hook.example/x"))

    alerter = Alerter(webhook_url="https://hook.example/x")
    monkeypatch.setattr(alerter, "_post", fake_post)
    assert alerter.send("t", "b") is False


def test_alerter_with_webhook_httperror_returns_false(monkeypatch):
    def fake_post(payload):
        raise httpx.ConnectError("boom")

    alerter = Alerter(webhook_url="https://hook.example/x")
    monkeypatch.setattr(alerter, "_post", fake_post)
    assert alerter.send("t", "b") is False


@pytest.mark.parametrize("places", [2])
def test_signals_markdown_one_line_per_signal(places):
    sigs = [_signal(), _signal().model_copy(update={"action": SignalAction.SELL})]
    md = signals_markdown(sigs)
    body_lines = [ln for ln in md.splitlines() if ln.startswith("| NABIL")]
    assert len(body_lines) == 2


# ---------------------------------------------------------------------------
# Alerting backend tests (mocked network)
# ---------------------------------------------------------------------------


def test_alerter_send_telegram_ok(monkeypatch):
    def fake_post(url, json, timeout):
        return httpx.Response(200, json={"ok": True})

    monkeypatch.setattr(httpx, "post", fake_post)
    assert Alerter.send_telegram("token123", "chat456", "Hello") is True


def test_alerter_send_telegram_fail(monkeypatch):
    def fake_post(url, json, timeout):
        return httpx.Response(200, json={"ok": False})

    monkeypatch.setattr(httpx, "post", fake_post)
    assert Alerter.send_telegram("token123", "chat456", "Hello") is False


def test_alerter_send_telegram_http_error(monkeypatch):
    def fake_post(url, json, timeout):
        raise httpx.ConnectError("fail")

    monkeypatch.setattr(httpx, "post", fake_post)
    assert Alerter.send_telegram("token123", "chat456", "Hello") is False


def test_alerter_send_discord_ok(monkeypatch):
    def fake_post(url, json, timeout):
        return httpx.Response(204)

    monkeypatch.setattr(httpx, "post", fake_post)
    assert Alerter.send_discord("https://discord.webhook/xyz", "Hello") is True


def test_alerter_send_discord_fail(monkeypatch):
    def fake_post(url, json, timeout):
        return httpx.Response(400)

    monkeypatch.setattr(httpx, "post", fake_post)
    assert Alerter.send_discord("https://discord.webhook/xyz", "Hello") is False


def test_alerter_send_email_success(monkeypatch):
    class FakeSMTP:
        def __init__(self, host, port, timeout):
            pass

        def starttls(self):
            pass

        def login(self, user, pwd):
            pass

        def send_message(self, msg):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)
    assert (
        Alerter.send_email(
            "smtp.example.com",
            587,
            "from@example.com",
            "to@example.com",
            "Test",
            "Body",
            username="user",
            password="pass",
        )
        is True
    )


def test_alerter_send_email_failure(monkeypatch):
    class BrokenSMTP:
        def __init__(self, host, port, timeout):
            raise ConnectionError("refused")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    monkeypatch.setattr("smtplib.SMTP", BrokenSMTP)
    assert (
        Alerter.send_email(
            "smtp.example.com",
            587,
            "from@example.com",
            "to@example.com",
            "Test",
            "Body",
        )
        is False
    )


# --------------------------------------------------------------------------
# Advisor / rashifal builders
# --------------------------------------------------------------------------


def _card(**overrides) -> dict:
    payload = {
        "symbol": "NABIL",
        "action": "accumulate",
        "reference_price": 578.0,
        "entry_low": 574.5,
        "entry_high": 581.5,
        "stop": 553.0,
        "targets": [605.0, 625.75],
        "quantity": 70,
        "horizon_days": 10,
        "earliest_sell_date": "2026-08-24",
        "conviction": 3,
        "rationale": "sma_cross:buy; rsi:buy",
        "gross_pnl": 1638.0,
        "net_pnl": 1180.45,
        "entry_cost": 210.3,
        "exit_cost": 205.1,
        "capital_gains_tax": 42.15,
        "note": "",
        "signals": ["sma_cross:buy"],
    }
    payload.update(overrides)
    return payload


def _rashifal(**overrides) -> dict:
    payload = {
        "run_id": 1,
        "run_date": "2026-08-20",
        "mode": "normal",
        "horizon": "week",
        "online": True,
        "equity": 1_000_000.0,
        "regime": "broad advance",
        "sector_of_the_day": "Hydropower (+3.10%)",
        "cards": [_card()],
        "sell_queue": [],
        "do_not_touch": [],
        "breadth": {"advancers": 90, "decliners": 10},
        "banner": "",
        "thesis": "",
        "degraded": False,
        "generated_at": "2026-08-20T10:00:00+00:00",
    }
    payload.update(overrides)
    return payload


class TestPlanCardsMd:
    def test_renders_a_row_per_card(self):
        out = plan_cards_md([_card(), _card(symbol="ADBL")])
        assert out.count("\n") == 3  # header + separator + two rows
        assert "NABIL" in out and "ADBL" in out

    def test_shows_both_targets_and_the_settlement_date(self):
        out = plan_cards_md([_card()])
        assert "605.00" in out
        assert "625.75" in out
        assert "2026-08-24" in out

    def test_a_single_target_leaves_the_second_column_blank(self):
        out = plan_cards_md([_card(targets=[605.0])])
        assert "605.00" in out
        assert out.rstrip().endswith("| 2026-08-24 |")

    def test_no_targets_renders_dashes_not_a_crash(self):
        out = plan_cards_md([_card(targets=[])])
        assert "-" in out

    def test_an_empty_list_says_so(self):
        out = plan_cards_md([])
        assert "no actionable cards today" in out

    def test_a_missing_key_renders_a_dash(self):
        out = plan_cards_md([{"symbol": "NABIL"}])
        assert "NABIL" in out


class TestSellQueueMd:
    def test_renders_the_reason_and_the_legal_date(self):
        out = sell_queue_md(
            [
                {
                    "symbol": "NABIL",
                    "quantity": 100,
                    "reference_price": 470.0,
                    "reason": "price 470.0 at or below stop 480.0",
                    "earliest_sell_date": "2026-08-24",
                }
            ]
        )
        assert "at or below stop" in out
        assert "2026-08-24" in out

    def test_an_empty_queue_says_nothing_to_exit(self):
        assert "nothing to exit" in sell_queue_md([])


class TestDoNotTouchMd:
    def test_renders_the_reason(self):
        out = do_not_touch_md([{"symbol": "NICA", "reason": "only 3 bars"}])
        assert "NICA" in out
        assert "only 3 bars" in out

    def test_an_empty_list_confirms_full_coverage(self):
        assert "every requested symbol got a card" in do_not_touch_md([])


class TestRashifalMd:
    def test_includes_the_header_facts(self):
        out = rashifal_md(_rashifal())
        assert "2026-08-20" in out
        assert "broad advance" in out
        assert "Hydropower" in out
        assert "online" in out

    def test_offline_is_labelled(self):
        assert "offline" in rashifal_md(_rashifal(online=False))

    def test_the_disclaimer_is_always_present(self):
        out = rashifal_md(_rashifal())
        assert RASHIFAL_DISCLAIMER in out

    def test_the_disclaimer_denies_astrological_input(self):
        assert "No astrological" in RASHIFAL_DISCLAIMER
        assert "investment advice" in RASHIFAL_DISCLAIMER.lower()

    def test_a_banner_appears_before_anything_else(self):
        out = rashifal_md(_rashifal(banner="AI narrative unavailable — daily cap reached"))
        assert out.index("daily cap reached") < out.index("Buy candidates")

    def test_no_banner_means_no_warning_block(self):
        assert "⚠️" not in rashifal_md(_rashifal())

    def test_buys_and_holds_are_separate_sections(self):
        out = rashifal_md(_rashifal(cards=[_card(), _card(symbol="ADBL", action="hold")]))
        assert "Buy candidates" in out
        assert "Hold / reduce" in out

    def test_no_holds_means_no_hold_section(self):
        assert "Hold / reduce" not in rashifal_md(_rashifal())

    def test_the_thesis_section_appears_only_when_there_is_one(self):
        assert "This week's thesis" not in rashifal_md(_rashifal())
        out = rashifal_md(_rashifal(thesis="Breadth improved but turnover is thin."))
        assert "This week's thesis" in out
        assert "turnover is thin" in out

    def test_commentary_appears_only_when_a_card_has_a_note(self):
        assert "### Commentary" not in rashifal_md(_rashifal())
        out = rashifal_md(_rashifal(cards=[_card(note="Deposit mix improved.")]))
        assert "### Commentary" in out
        assert "Deposit mix improved." in out

    def test_the_sell_queue_and_skips_are_always_shown(self):
        out = rashifal_md(_rashifal())
        assert "Sell queue" in out
        assert "Do not touch" in out

    def test_an_empty_run_still_renders(self):
        out = rashifal_md({})
        assert RASHIFAL_DISCLAIMER in out
        assert "no actionable cards today" in out
