"""Shared pytest fixtures + test-run logging.

Two responsibilities:

1. **Isolate run-logs during tests.** The CLI and pipeline now open a
   :func:`nepse_trader.logging_setup.run_logger` on every invocation, which would
   otherwise spray files into the real ``logs/`` tree each test run. A
   session-autouse fixture points ``NEPSE_LOG_DIR`` at a temp directory so those
   under-test logs land in scratch space, not the repo.

2. **Log the test run itself** to ``logs/tests/<HH-MM-SS>-<YYYY-MM-DD>-pytest.log``
   — satisfying "everything we run should be logged". This file is written to the
   *real* logs tree (computed from the project root, before the env override) and
   records one line per test plus a pass/fail summary.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

import pytest

# Real project logs/ dir — resolved before any env override so the test-run log
# always lands in the repo, not the per-session temp dir.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_REAL_LOG_DIR = _PROJECT_ROOT / "logs"

# Module-level state for the test-run log (TestReport has no back-ref to config,
# so the per-test hook appends here directly).
_RUN_STATE: dict[str, object] = {}


@pytest.fixture(scope="session", autouse=True)
def _isolate_run_logs(tmp_path_factory):
    """Redirect under-test run-logs into a temp dir for the whole session."""
    from nepse_trader.config import get_settings

    scratch = tmp_path_factory.mktemp("run_logs")
    prev = os.environ.get("NEPSE_LOG_DIR")
    os.environ["NEPSE_LOG_DIR"] = str(scratch)
    get_settings.cache_clear()
    yield
    if prev is None:
        os.environ.pop("NEPSE_LOG_DIR", None)
    else:
        os.environ["NEPSE_LOG_DIR"] = prev
    get_settings.cache_clear()


# --- test-run logging -------------------------------------------------------

def _test_log_path() -> Path:
    now = datetime.now()
    return _REAL_LOG_DIR / "tests" / f"{now:%H-%M-%S}-{now:%Y-%m-%d}-pytest.log"


def pytest_configure(config: pytest.Config) -> None:
    """Open the session logfile and attach a handler capturing nepse_trader logs."""
    path = _test_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                          datefmt="%Y-%m-%d %H:%M:%S")
    )
    logging.getLogger("nepse_trader").addHandler(handler)
    logging.getLogger("nepse_trader").setLevel(logging.DEBUG)
    _RUN_STATE["handler"] = handler
    _RUN_STATE["path"] = path
    _RUN_STATE["lines"] = [f"pytest session start @ {datetime.now().isoformat()}"]


def pytest_runtest_logreport(report: pytest.TestReport) -> None:
    """Record one line per test outcome (call phase, plus any setup/teardown error)."""
    if report.when == "call" or (report.when in ("setup", "teardown") and report.failed):
        lines = _RUN_STATE.get("lines")
        if isinstance(lines, list):
            lines.append(f"{report.outcome.upper():7} {report.when:9} {report.nodeid}")


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Flush the per-test lines + a summary into the session logfile, then detach."""
    handler = _RUN_STATE.get("handler")
    path = _RUN_STATE.get("path")
    lines = _RUN_STATE.get("lines", [])
    if handler is None or path is None:
        return

    tr = session.config.pluginmanager.get_plugin("terminalreporter")
    counts = {}
    if tr is not None:
        for key in ("passed", "failed", "error", "skipped", "xfailed", "xpassed"):
            got = tr.stats.get(key, [])
            if got:
                counts[key] = len(got)
    summary = ", ".join(f"{k}={v}" for k, v in counts.items()) or "no tests"
    lines.append(f"summary: {summary}  exitstatus={exitstatus}")  # type: ignore[union-attr]
    lines.append(f"pytest session end   @ {datetime.now().isoformat()}")  # type: ignore[union-attr]

    # The per-test lines are plain text; write them directly to the file so the
    # log is readable even when no nepse_trader.* records were emitted.
    with path.open("a", encoding="utf-8") as fh:  # type: ignore[union-attr]
        fh.write("\n".join(lines) + "\n")  # type: ignore[arg-type]

    logging.getLogger("nepse_trader").removeHandler(handler)  # type: ignore[arg-type]
    handler.close()  # type: ignore[union-attr]
