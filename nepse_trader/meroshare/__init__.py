"""Read-only mirror of the user's own MeroShare/CDSC account.

Four modules, each testable offline:

* :mod:`nepse_trader.meroshare.credentials` — resolution (argument → OS keyring →
  env) plus the redaction machinery every other module uses.
* :mod:`nepse_trader.meroshare.client` — login, holdings, WACC, transaction
  history. No retries on auth, no raw-response cache, no request body in any
  exception.
* :mod:`nepse_trader.meroshare.importer` — the no-credentials path: a CSV or
  pasted export parsed into the same model.
* :mod:`nepse_trader.meroshare.sync` — idempotent persistence, an attempt log
  that records failures, and the real-vs-paper comparison.

Two invariants hold across all of it:

1. **Read-only.** No IPO/ASBA application and no order placement exists here,
   not even unused. ``tests/test_meroshare.py`` scans for it.
2. **Credentials never leave memory.** Not to a log, not into an exception
   message, not to the raw-response cache, and not into any database column —
   the ``0006_meroshare`` schema has nowhere to put one.

Automating a login-gated portal may conflict with CDSC's terms of service. It is
the user's own data and the user's own call; the importer is there for anyone who
would rather not store a password at all.
"""

from nepse_trader.meroshare.client import (
    ENDPOINTS,
    ConnectionResult,
    MeroShareAuthError,
    MeroShareClient,
    MeroShareDisabledError,
    MeroShareError,
    MeroShareFetchError,
    OwnDetail,
    connect,
    connection_disclosure,
    ensure_enabled,
)
from nepse_trader.meroshare.credentials import (
    MeroShareCredentialError,
    MeroShareCredentials,
    Resolution,
    keyring_available,
    redact,
    resolve_credentials,
)
from nepse_trader.meroshare.importer import (
    MeroShareImportError,
    import_portfolio,
    parse_holdings_csv,
    parse_holdings_file,
)
from nepse_trader.meroshare.models import (
    HoldingDiff,
    MeroShareHolding,
    MeroSharePortfolio,
    MeroShareTransaction,
)
from nepse_trader.meroshare.sync import (
    SyncResult,
    compare_with_paper,
    comparison_summary,
    stored_holdings,
    stored_transactions,
    sync_from_client,
    sync_from_csv,
    sync_history,
    sync_payload,
    sync_status,
)

__all__ = [
    "ENDPOINTS",
    "ConnectionResult",
    "MeroShareAuthError",
    "MeroShareClient",
    "MeroShareDisabledError",
    "MeroShareError",
    "MeroShareFetchError",
    "OwnDetail",
    "connect",
    "connection_disclosure",
    "ensure_enabled",
    "MeroShareCredentialError",
    "MeroShareCredentials",
    "Resolution",
    "keyring_available",
    "redact",
    "resolve_credentials",
    "MeroShareImportError",
    "import_portfolio",
    "parse_holdings_csv",
    "parse_holdings_file",
    "HoldingDiff",
    "MeroShareHolding",
    "MeroSharePortfolio",
    "MeroShareTransaction",
    "SyncResult",
    "compare_with_paper",
    "comparison_summary",
    "stored_holdings",
    "stored_transactions",
    "sync_from_client",
    "sync_from_csv",
    "sync_history",
    "sync_payload",
    "sync_status",
]
