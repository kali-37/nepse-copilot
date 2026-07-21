"""Tests for the centralised run-logging (nepse_trader.logging_setup)."""

from __future__ import annotations

import logging
from datetime import datetime

import pytest

from nepse_trader.config import get_settings
from nepse_trader.logging_setup import (
    ROOT_LOGGER_NAME,
    get_logger,
    log_path,
    run_logger,
    slugify,
)


@pytest.fixture(autouse=True)
def _log_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("NEPSE_LOG_DIR", str(tmp_path / "logs"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# --- slugify ----------------------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("run-daily", "run-daily"),
        ("run daily 2026-05-18", "run-daily-2026-05-18"),
        ("paper buy NABIL", "paper-buy-NABIL"),
        ("weird/<>:name", "weird-name"),
        ("///", "run"),       # all-symbol -> fallback
        ("", "run"),          # empty -> fallback
        ("--leading--", "leading"),
    ],
)
def test_slugify(raw, expected):
    assert slugify(raw) == expected


# --- log_path scheme --------------------------------------------------------

def test_log_path_scheme():
    now = datetime(2026, 5, 18, 9, 7, 3)
    p = log_path("cli", "run-daily 2026-05-18", now=now)
    # logs/<component>/<HH-MM-SS>-<YYYY-MM-DD>-<about>.log
    assert p.parent.name == "cli"
    assert p.name == "09-07-03-2026-05-18-run-daily-2026-05-18.log"
    assert p.suffix == ".log"


def test_log_path_component_slugified():
    now = datetime(2026, 1, 2, 3, 4, 5)
    p = log_path("paper buy", "NABIL", now=now)
    assert p.parent.name == "paper-buy"
    assert p.name == "03-04-05-2026-01-02-NABIL.log"


# --- run_logger behaviour ---------------------------------------------------

def test_run_logger_writes_file_and_captures_records():
    now = datetime(2026, 5, 18, 12, 0, 0)
    with run_logger("cli", "demo", now=now) as path:
        logging.getLogger("nepse_trader.demo").info("hello-from-test")
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "hello-from-test" in text
    assert "run start" in text
    assert "run end" in text


def test_run_logger_detaches_handler_on_exit():
    # Default capture_root=True attaches to the ROOT logger (it still receives
    # nepse_trader.* via propagation, without double-writing).
    root = logging.getLogger()
    before = list(root.handlers)
    with run_logger("cli", "detach", now=datetime(2026, 1, 1, 0, 0, 0)):
        during = list(root.handlers)
        assert len(during) == len(before) + 1
    after = list(root.handlers)
    assert after == before  # handler removed, none leaked


def test_run_logger_scoped_attaches_to_package_logger():
    pkg = logging.getLogger(ROOT_LOGGER_NAME)
    before = list(pkg.handlers)
    with run_logger("cli", "scoped-attach", capture_root=False,
                    now=datetime(2026, 1, 1, 0, 0, 0)):
        assert len(pkg.handlers) == len(before) + 1
    assert pkg.handlers == before


def test_run_logger_no_duplicate_handlers_across_runs():
    pkg = logging.getLogger(ROOT_LOGGER_NAME)
    root = logging.getLogger()
    before_pkg, before_root = len(pkg.handlers), len(root.handlers)
    for i in range(3):
        with run_logger("cli", f"run{i}", now=datetime(2026, 1, 1, 0, 0, i)):
            pass
    assert len(pkg.handlers) == before_pkg  # each run cleans up after itself
    assert len(root.handlers) == before_root


def test_run_logger_no_double_write():
    # A single nepse_trader.* record must appear exactly once in the file even
    # though it propagates pkg -> root (the handler lives on only one logger).
    now = datetime(2026, 6, 6, 6, 6, 6)
    with run_logger("cli", "once", now=now) as path:
        logging.getLogger("nepse_trader.dedup").info("UNIQUE-MARKER-XYZ")
    text = path.read_text(encoding="utf-8")
    assert text.count("UNIQUE-MARKER-XYZ") == 1


def test_run_logger_logs_then_reraises_on_error():
    now = datetime(2026, 3, 3, 3, 3, 3)
    with pytest.raises(ValueError):
        with run_logger("cli", "boom", now=now) as path:
            raise ValueError("kaboom")
    text = path.read_text(encoding="utf-8")
    assert "run failed" in text
    assert "kaboom" in text
    # handler detached from both candidate loggers after the exception
    for lg in (logging.getLogger(), logging.getLogger(ROOT_LOGGER_NAME)):
        assert all(getattr(h, "baseFilename", None) != str(path) for h in lg.handlers)


def test_run_logger_isolates_concurrent_files():
    a_now = datetime(2026, 1, 1, 1, 1, 1)
    b_now = datetime(2026, 1, 1, 2, 2, 2)
    with run_logger("cli", "alpha", now=a_now) as a:
        logging.getLogger("nepse_trader.x").info("alpha-line")
    with run_logger("cli", "beta", now=b_now) as b:
        logging.getLogger("nepse_trader.x").info("beta-line")
    assert "alpha-line" in a.read_text() and "beta-line" not in a.read_text()
    assert "beta-line" in b.read_text() and "alpha-line" not in b.read_text()


def test_capture_root_false_excludes_foreign_loggers():
    now = datetime(2026, 4, 4, 4, 4, 4)
    with run_logger("cli", "scoped", capture_root=False, now=now) as path:
        logging.getLogger("some_third_party").warning("foreign")
        logging.getLogger("nepse_trader.mine").info("mine")
    text = path.read_text(encoding="utf-8")
    assert "mine" in text
    assert "foreign" not in text


# --- get_logger -------------------------------------------------------------

def test_run_logger_control_flow_exit_is_calm():
    # typer.Exit is normal CLI control flow — logged calmly, NOT as "run failed".
    import typer

    now = datetime(2026, 7, 7, 7, 7, 7)
    with pytest.raises(typer.Exit):
        with run_logger("cli", "graceful", now=now) as path:
            raise typer.Exit(code=1)
    text = path.read_text(encoding="utf-8")
    assert "run failed" not in text
    assert "run exited" in text
    assert "Traceback" not in text


def test_get_logger_prefixes_package_root():
    assert get_logger("ingest").name == "nepse_trader.ingest"
    assert get_logger("nepse_trader.x").name == "nepse_trader.x"
    assert get_logger(ROOT_LOGGER_NAME).name == ROOT_LOGGER_NAME
