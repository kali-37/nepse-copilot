from __future__ import annotations

from collections.abc import Iterable
from typing import TypeVar

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

T = TypeVar("T")


def progress_spinner(console: Console, msg: str):
    """A simple spinner context for indeterminate tasks."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    )


def progress_bars(console: Console) -> Progress:
    """Reusable Progress instance with standard columns."""
    return Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=True,
    )


def track(
    seq: Iterable[T],
    console: Console,
    description: str = "Working...",
    total: int | None = None,
) -> Iterable[T]:
    """Iterate over *seq* with a live progress bar."""
    with progress_bars(console) as p:
        yield from p.track(seq, description=description, total=total)
