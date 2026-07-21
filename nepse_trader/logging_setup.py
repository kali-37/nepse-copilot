"""Centralised run-logging for NEPSE Trader.

Every meaningful thing the project *runs* — each CLI command, the daily pipeline,
and the test suite — opens a :func:`run_logger` context that writes a dedicated,
timestamped logfile under ``logs/<component>/``. The filename follows the project
convention requested by the operator::

    logs/<component>/<HH-MM-SS>-<YYYY-MM-DD>-<about>.log
                     └ time ──┘ └─ date ──┘ └ what it was about

Design goals:

* **One file per run.** A context manager attaches a :class:`FileHandler` to the
  package root logger (``nepse_trader``) on enter and detaches it on exit, so
  concurrent or nested runs never bleed into each other and handlers never leak.
* **Capture everything.** The handler is attached to the ``nepse_trader`` logger
  at ``DEBUG`` and the root logger is given a handler too, so third-party libs
  (httpx, urllib3, …) that log under their own names are captured as well.
* **Honest filenames.** ``<about>`` is slugified so a free-form description like
  ``"run-daily 2026-05-18"`` becomes ``run-daily-2026-05-18`` — filesystem safe.
* **Never fatal.** Logging is observability; if the log directory cannot be
  created the run still proceeds (a warning is emitted to stderr once).

The time/date come from ``datetime.now()`` deliberately: these are wall-clock run
markers, not business dates, so local time is what an operator scanning ``logs/``
expects to see.
"""

from __future__ import annotations

import contextlib
import logging
import re
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

from nepse_trader.config import get_settings

#: The package-root logger. Every module logger (``nepse_trader.*``) propagates
#: here, so attaching one handler captures the whole project.
ROOT_LOGGER_NAME = "nepse_trader"

_FILE_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_SLUG_RE = re.compile(r"[^A-Za-z0-9._-]+")


def slugify(text: str) -> str:
    """Make ``text`` safe for a filename segment.

    Collapses any run of non ``[A-Za-z0-9._-]`` characters to a single dash and
    trims leading/trailing dashes. Empty / all-symbol input becomes ``"run"`` so
    a filename is always produced.
    """
    slug = _SLUG_RE.sub("-", str(text)).strip("-._")
    return slug or "run"


def log_path(component: str, about: str, *, now: datetime | None = None) -> Path:
    """Compute the logfile path for a run without creating anything.

    ``logs/<component>/<HH-MM-SS>-<YYYY-MM-DD>-<about>.log`` under the configured
    ``log_dir``. ``component`` is also slugified so callers can pass values like
    ``"paper buy"`` safely.
    """
    stamp = now or datetime.now()
    settings = get_settings()
    folder = Path(settings.log_dir) / slugify(component)
    filename = f"{stamp:%H-%M-%S}-{stamp:%Y-%m-%d}-{slugify(about)}.log"
    return folder / filename


def _make_handler(path: Path) -> logging.FileHandler:
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(path, encoding="utf-8")
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter(_FILE_FORMAT, datefmt=_DATE_FORMAT))
    return handler


def _is_control_flow_exit(exc: BaseException) -> bool:
    """True for typer/click ``Exit``/``Abort`` — normal CLI control flow, not errors.

    Detected structurally (class name + an ``exit_code``/``code`` attribute) so we
    don't hard-depend on click internals; falls back to a guarded import.
    """
    name = type(exc).__name__
    if name in ("Exit", "Abort") and (
        hasattr(exc, "exit_code") or hasattr(exc, "code")
    ):
        return True
    try:  # pragma: no cover - exercised indirectly via the CLI
        import click

        return isinstance(exc, (click.exceptions.Exit, click.exceptions.Abort))
    except Exception:  # pragma: no cover - click always present with typer
        return False


@contextlib.contextmanager
def run_logger(
    component: str,
    about: str,
    *,
    capture_root: bool = True,
    now: datetime | None = None,
) -> Iterator[Path]:
    """Context manager: log everything during the block to one timestamped file.

    Parameters
    ----------
    component:
        Sub-folder under ``logs/`` grouping related runs (e.g. ``"cli"``,
        ``"pipeline"``, ``"tests"``).
    about:
        Free-form description of this run; slugified into the filename.
    capture_root:
        When true (default) the handler is also attached to the *root* logger so
        third-party library logs are captured. When false only ``nepse_trader.*``
        records are written.
    now:
        Inject a fixed timestamp (tests use this for deterministic filenames).

    Yields
    ------
    Path
        The logfile being written. On a filesystem error the file may not exist;
        the block still runs (logging must never break a run).
    """
    path = log_path(component, about, now=now)
    pkg_logger = logging.getLogger(ROOT_LOGGER_NAME)
    pkg_logger.setLevel(logging.DEBUG)

    handler: logging.FileHandler | None = None
    target: logging.Logger | None = None
    try:
        handler = _make_handler(path)
    except OSError as exc:  # pragma: no cover - defensive; logging is non-fatal
        logging.getLogger(__name__).warning("could not open logfile %s: %s", path, exc)

    if handler is not None:
        # Attach to EXACTLY ONE logger in the propagation chain to avoid writing
        # each record twice. With capture_root the handler sits on the root
        # logger, which still receives nepse_trader.* records via propagation
        # *plus* third-party library records. Otherwise it sits on the package
        # logger and only nepse_trader.* is captured.
        target = logging.getLogger() if capture_root else pkg_logger
        target.addHandler(handler)

    started = now or datetime.now()
    pkg_logger.info("=== run start: %s/%s @ %s ===", component, about, started.isoformat())
    try:
        yield path
    except (KeyboardInterrupt, SystemExit) as exc:
        # Genuine interruption / process-level exit — note it, no noisy traceback.
        pkg_logger.warning("run interrupted: %s: %s", type(exc).__name__, exc)
        raise
    except BaseException as exc:
        if _is_control_flow_exit(exc):
            # typer/click Exit & Abort are normal control flow (graceful exits,
            # non-zero status for "nothing to do"); record calmly, no traceback.
            code = getattr(exc, "exit_code", getattr(exc, "code", None))
            pkg_logger.info("run exited: %s (code=%s)", type(exc).__name__, code)
        else:
            pkg_logger.error("run failed: %s: %s", type(exc).__name__, exc, exc_info=True)
        raise
    finally:
        pkg_logger.info("=== run end:   %s/%s ===", component, about)
        if handler is not None:
            handler.close()
            if target is not None:
                with contextlib.suppress(ValueError):
                    target.removeHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Return a module logger under the package root (``nepse_trader.<name>``).

    Convenience so call-sites don't hard-code the prefix; records flow to
    whatever :func:`run_logger` file is active.
    """
    if name == ROOT_LOGGER_NAME or name.startswith(ROOT_LOGGER_NAME + "."):
        return logging.getLogger(name)
    return logging.getLogger(f"{ROOT_LOGGER_NAME}.{name}")
