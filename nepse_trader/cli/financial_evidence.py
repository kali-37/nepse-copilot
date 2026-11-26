"""CLI entry points for importing attributable public financial data."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from nepse_trader.config import get_settings
from nepse_trader.storage import Storage
from nepse_trader.storage.research import save_financial_evidence

console = Console()


def register(app: typer.Typer) -> None:
    app.command("verify-statement")(verify_statement)
    app.command("import-nrb")(import_nrb)


def verify_statement(
    manifest: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
) -> None:
    """Match cited rows to an official source and retain a copy by document hash."""
    from nepse_trader.analysis.financial_evidence import (
        StatementSubmission,
        verify_official_statement,
    )

    settings = get_settings()
    try:
        submission = StatementSubmission.model_validate_json(manifest.read_bytes())
        evidence = verify_official_statement(
            submission, settings=settings, archive_dir=settings.raw_cache_dir / "financial-evidence"
        )
        with Storage(settings.db_path) as storage:
            result = save_financial_evidence(storage, [evidence])
    except (ValueError, OSError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print_json(data={"symbol": evidence.symbol, **result})


def import_nrb() -> None:
    """Import reported capital and loan-quality measures from the central bank."""
    from nepse_trader.ingest.nrb_fundamentals import fetch_nrb_indicators

    settings = get_settings()
    try:
        evidence = fetch_nrb_indicators(
            settings, archive_dir=settings.raw_cache_dir / "financial-evidence"
        )
        with Storage(settings.db_path) as storage:
            result = save_financial_evidence(storage, evidence)
    except (ValueError, OSError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    console.print_json(data={"symbols": sorted({row.symbol for row in evidence}), **result})
