"""Offline coverage for the advisor, journal, auction and MeroShare CLI surface."""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from nepse_trader.advisor.journal import log_prediction
from nepse_trader.cli.main import app
from nepse_trader.config import get_settings
from nepse_trader.models import PriceBar, ReconciledPrice, SourceName
from nepse_trader.storage import Storage

runner = CliRunner()
START = date(2026, 1, 1)


def _seed_prices(storage: Storage) -> None:
    raw: list[PriceBar] = []
    reconciled: list[ReconciledPrice] = []
    for offset, symbol in enumerate(("NABIL", "NICA")):
        price = 500.0 + offset * 100
        for day in range(60):
            business_date = START + timedelta(days=day)
            previous = price
            price = round(price * (1.01 if (day + offset) % 2 == 0 else 0.995), 2)
            raw.append(
                PriceBar(
                    symbol=symbol,
                    business_date=business_date,
                    open=previous,
                    high=max(previous, price) + 2,
                    low=min(previous, price) - 2,
                    close=price,
                    previous_close=previous,
                    volume=1_000 + day,
                    turnover=price * (1_000 + day),
                    source=SourceName.MANUAL,
                )
            )
            reconciled.append(
                ReconciledPrice(
                    symbol=symbol,
                    business_date=business_date,
                    open=previous,
                    high=max(previous, price) + 2,
                    low=min(previous, price) - 2,
                    close=price,
                    previous_close=previous,
                    volume=1_000 + day,
                    turnover=price * (1_000 + day),
                    sources_agreeing=[SourceName.MANUAL],
                    sources_present=[SourceName.MANUAL],
                    confidence=1.0,
                )
            )
    storage.upsert_price_bars(raw)
    storage.upsert_reconciled(reconciled)


@pytest.fixture(autouse=True)
def _temp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("NEPSE_DB_PATH", str(tmp_path / "cli-advisor.db"))
    monkeypatch.setenv("NEPSE_RAW_CACHE_DIR", str(tmp_path / "raw"))
    monkeypatch.setenv("NEPSE_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("NEPSE_MEROSHARE_ENABLED", "false")
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


def _storage() -> Storage:
    return Storage(get_settings().db_path)


def test_top_level_help_exposes_the_complete_assistant_surface():
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0, result.output
    for command in ("rashifal", "advise", "doses", "journal", "auction", "meroshare", "mcp"):
        assert command in result.output


def test_group_help_exposes_the_required_subcommands():
    expected = {
        "journal": ("history", "score", "review", "distill", "retire", "calibration"),
        "auction": ("advise", "list"),
        "meroshare": ("connect", "sync", "import", "holdings", "status", "toggle"),
        "mcp": ("serve",),
    }
    for group, commands in expected.items():
        result = runner.invoke(app, [group, "--help"])
        assert result.exit_code == 0, result.output
        for command in commands:
            assert command in result.output


def test_rashifal_and_doses_are_offline_and_include_all_four_horizons():
    storage = _storage()
    try:
        _seed_prices(storage)
    finally:
        storage.close()

    result = runner.invoke(
        app,
        [
            "rashifal",
            "--symbols",
            "NABIL,NICA",
            "--equity",
            "100000",
            "--offline",
            "--no-save",
        ],
    )

    assert result.exit_code == 0, result.output
    for horizon in ("DAY", "WEEK", "MONTH", "YEAR"):
        assert horizon in result.output

    doses = runner.invoke(
        app,
        ["doses", "--symbols", "NABIL,NICA", "--equity", "100000", "--offline"],
    )
    assert doses.exit_code == 0, doses.output
    assert "Investment doses" in doses.output
    assert "DAY" in doses.output and "YEAR" in doses.output


def test_journal_score_review_distill_and_retire_lifecycle():
    storage = _storage()
    try:
        _seed_prices(storage)
        card = SimpleNamespace(
            symbol="NABIL",
            action="accumulate",
            reference_price=500.0,
            entry_low=499.0,
            entry_high=500.0,
            stop=450.0,
            targets=[501.0],
            quantity=10,
            horizon_days=10,
            net_pnl=10.0,
            rationale="offline test",
        )
        prediction = log_prediction(storage._conn, card, made_on=START - timedelta(days=1), horizon="week")
    finally:
        storage.close()

    scored = runner.invoke(app, ["journal", "score", prediction.prediction_id])
    assert scored.exit_code == 0, scored.output
    assert "TARGET_HIT" in scored.output

    reviewed = runner.invoke(
        app,
        ["journal", "review", prediction.prediction_id, "--text", "Target was reached on the first bar."],
    )
    assert reviewed.exit_code == 0, reviewed.output
    assert "reviewed" in reviewed.output

    distilled = runner.invoke(
        app,
        ["journal", "distill", prediction.prediction_id, "--lesson", "Keep stop-first scoring."],
    )
    assert distilled.exit_code == 0, distilled.output
    assert "prediction_lesson:" in distilled.output

    retired = runner.invoke(app, ["journal", "retire", prediction.prediction_id])
    assert retired.exit_code == 0, retired.output
    assert "retired" in retired.output

    history = runner.invoke(app, ["journal", "history", "--status", "retired"])
    assert history.exit_code == 0, history.output
    assert prediction.prediction_id in history.output


def test_auction_advice_persists_without_submitting_a_bid():
    advice = runner.invoke(
        app,
        [
            "auction",
            "advise",
            "NABIL",
            "--auction-date",
            "2026-03-01",
            "--units",
            "100",
            "--min-bid-price",
            "100",
            "--market-price",
            "120",
        ],
    )
    assert advice.exit_code == 0, advice.output
    assert "No auction bid was submitted" in advice.output
    assert '"symbol": "NABIL"' in advice.output

    listing = runner.invoke(app, ["auction", "list", "--symbol", "NABIL"])
    assert listing.exit_code == 0, listing.output
    assert '"symbol": "NABIL"' in listing.output


def test_meroshare_csv_import_and_local_views_redact_account_identifier(tmp_path):
    export = tmp_path / "holdings.csv"
    demat = "1301230000000001"
    export.write_text(
        f"Scrip,Current Balance,WACC,Demat\nNABIL,25,500,{demat}\n",
        encoding="utf-8",
    )

    imported = runner.invoke(app, ["meroshare", "import", "--file", str(export)])
    assert imported.exit_code == 0, imported.output
    assert "Imported 1 holding" in imported.output

    holdings = runner.invoke(app, ["meroshare", "holdings"])
    assert holdings.exit_code == 0, holdings.output
    assert "NABIL" in holdings.output
    assert demat not in holdings.output
    assert '"demat_last4": "0001"' in holdings.output

    status = runner.invoke(app, ["meroshare", "status"])
    assert status.exit_code == 0, status.output
    assert "last_error" not in status.output


def test_meroshare_toggle_changes_only_the_selected_env_setting(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("UNRELATED=value\nNEPSE_MEROSHARE_ENABLED=false\n", encoding="utf-8")

    result = runner.invoke(app, ["meroshare", "toggle", "on", "--env-file", str(env_file)])

    assert result.exit_code == 0, result.output
    assert env_file.read_text(encoding="utf-8") == "UNRELATED=value\nNEPSE_MEROSHARE_ENABLED=true\n"
