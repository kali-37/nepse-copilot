"""Read-only HTTP client for the user's own MeroShare/CDSC account.

**Read-only means read-only.** This module can log in, list holdings, read WACC
and read transaction history. There is no code here — not even unused, not even
commented out — that applies for an IPO (ASBA), places an order, or mutates
anything on the CDSC side. ``tests/test_meroshare.py`` asserts that by scanning
the package's public callables, so adding one later breaks the build.

Automating a login-gated portal may conflict with CDSC's terms of service. This
is the user's own data and the choice is theirs;
``nepse_trader.meroshare.importer`` exists for anyone who would rather paste a
CSV export than store a password.

Why this is not a :class:`nepse_trader.ingest.base.BaseClient` subclass
----------------------------------------------------------------------
``BaseClient`` is the right tool for public market data and the wrong one here:

* It caches **every response body** to ``data/raw/<date>_<sha16>.txt``. On this
  endpoint that is the user's entire portfolio, and on the login call it is a
  response carrying a session token — written to disk in plaintext. Passing
  ``cache_raw=False`` fixes today's code, but the default is ``True``, so one
  refactor that drops the kwarg silently starts writing account data to disk.
  For a secret-handling client the safe default must be the *only* behaviour.
* Its error paths embed ``resp.text[:200]`` in the exception message. This
  package's headline guarantee is that no response body and no credential
  reaches a log or an exception, so those paths would all need overriding.
* Its tenacity policy retries 403 as "rate limited". On a login form, retrying a
  rejected password three times is how an account gets locked. A wrong password
  must fail once, immediately.
* It has no notion of a bearer token carried across requests, which is the whole
  shape of this interaction.

What remains is small enough to be obvious: one injectable ``httpx.Client``, no
retries, no disk writes, and a single conversion point where every ``httpx``
exception becomes a domain error with a redacted, body-free message.

One login per run
-----------------
CDSC throttles logins per account: after a successful login — even one followed
by a confirmed logout — the next login attempt answers 500 for a cooldown
period. So :meth:`MeroShareClient.login` is called once and the session reused,
:meth:`MeroShareClient.close` always logs out to release it, and back-to-back
commands (``meroshare connect`` immediately followed by ``meroshare sync``) will
hit the throttle. That is CDSC's rule, not this client's, and the error message
says so rather than retrying into it.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import httpx

from nepse_trader.config import Settings, get_settings
from nepse_trader.meroshare.credentials import (
    MeroShareCredentialError,
    MeroShareCredentials,
    redact,
    resolve_credentials,
)
from nepse_trader.meroshare.models import (
    MeroShareHolding,
    MeroSharePortfolio,
    MeroShareTransaction,
)

log = logging.getLogger("nepse_trader.meroshare.client")

# ===========================================================================
# VERIFIED ENDPOINT MAP — captured 2026-08-23 against a live CDSC account.
# ===========================================================================
# Every path, body key and response key below was confirmed by making the call
# and reading the response, cross-checked against the MeroShare SPA bundle
# (``main.<hash>.bundle.js``, which is where the request shapes are literally
# spelled out). This is not reconstructed from hearsay.
#
# Three findings that are not guessable and will waste a day if lost:
#
# 1. **Cookies must not be replayed.** The login response sets eight F5/BigIP
#    cookies (TS01c40bbd, F0BNM, zqb6o9, …). Sending them back on a
#    ``meroShareView/*`` POST makes the WAF answer **HTTP 200 with an HTML
#    "Request Rejected" page** instead of JSON — a success status carrying a
#    failure. ``_request`` clears the cookie jar before every call, which is why
#    ``curl`` (no cookie jar by default) worked while a stock ``httpx.Client``
#    did not. See :data:`_WAF_MARKER`.
# 2. **``clientId`` is an integer.** ``{"clientId": "146"}`` is refused;
#    ``{"clientId": 146}`` succeeds.
# 3. **``myTransaction`` wants the 16-digit demat in its ``boid`` field**, not
#    the 8-digit BOID that ``ownDetail`` reports as ``boid``. Passing the real
#    BOID returns ``404 {"message": "Unauthorized"}``, which reads like an auth
#    problem and is not one.
#
# Response parsing stays defensive: unknown keys are ignored and missing keys
# yield ``None`` rather than raising, so a future shape drift degrades to "fewer
# fields" instead of a crash.
#
# Not reachable, and therefore not implemented: **WACC / cost basis.** Every
# purchase-history path the SPA uses (``myPurchase/waccSummaryReport/``,
# ``myPurchase/search/wacc/``, ``myPurchase/view/``, ``myPurchase/check/``)
# answers 500 or trips the WAF for this account. Holdings from the API therefore
# carry ``wacc=None``; cost basis comes from ``meroshare import`` reading a CSV
# export. Inventing a number here would be worse than admitting the gap.
ENDPOINTS: dict[str, str] = {
    "auth": "/meroShare/auth/",
    "logout": "/meroShare/auth/logout/",
    "own_detail": "/meroShare/ownDetail/",
    "portfolio": "/meroShareView/myPortfolio/",
    "transactions": "/meroShareView/myTransaction/",
}

PORTFOLIO_PAGE_SIZE = 200

# The header set the browser sends. The WAF in front of CDSC scores requests on
# header shape, and this is the combination captured passing; the project's own
# ``settings.user_agent`` is deliberately not used on this host.
BROWSER_HEADERS: dict[str, str] = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Content-Type": "application/json",
    "Origin": "https://meroshare.cdsc.com.np",
    "Referer": "https://meroshare.cdsc.com.np/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/151.0.0.0 Safari/537.36"
    ),
}

# The SPA sends the literal string "null" here before it holds a token.
UNAUTHENTICATED_TOKEN = "null"

# The WAF's rejection page, which arrives with status 200. Matched on the title
# so a genuine holding named "Request" can't trigger it.
_WAF_MARKER = "<title>Request Rejected</title>"

# Response keys we read. Aliases are tried in order, first hit wins.
HOLDINGS_LIST_KEYS = ("meroShareMyPortfolio", "data", "items")
TRANSACTIONS_LIST_KEYS = ("transactionView", "meroShareMyTransaction", "data", "items")
# ====================== end of verified endpoint map =======================


class MeroShareError(Exception):
    """Base for every failure in this package. Messages carry no credential."""


class MeroShareDisabledError(MeroShareError):
    """MeroShare integration is switched off in settings."""


class MeroShareAuthError(MeroShareError):
    """Login was refused, or the session expired."""


class MeroShareFetchError(MeroShareError):
    """A read failed: transport, bad status, or an unparseable body."""


def ensure_enabled(settings: Settings | None = None) -> Settings:
    """Return settings, or refuse cleanly when MeroShare is switched off.

    Refusing here rather than half-working is deliberate: a disabled
    integration that silently returns an empty portfolio looks exactly like an
    empty account.
    """
    settings = settings or get_settings()
    if not settings.meroshare_enabled:
        raise MeroShareDisabledError(
            "MeroShare integration is disabled. Set NEPSE_MEROSHARE_ENABLED=true "
            "to enable it, or use `meroshare import` to load a CSV export instead."
        )
    return settings


def connection_disclosure(settings: Settings | None = None) -> str:
    """Exactly what will be sent where, for the CLI to show before connecting.

    Returned as text rather than printed, and with no ``input()`` anywhere in
    this package, so the confirmation prompt lives in the CLI where the user can
    see it. Shows the username's *length* and never the password at all.
    """
    settings = settings or get_settings()
    resolution = resolve_credentials(settings)
    creds = resolution.credentials
    host = httpx.URL(settings.meroshare_base_url).host or settings.meroshare_base_url
    dp_shape = f"{len(creds.dp_id)} characters" if creds.dp_id else "NOT SET"
    user_shape = f"{len(creds.username)} characters" if creds.username else "NOT SET"
    pw_source = {
        "keyring": f"OS keyring (service {settings.meroshare_keyring_service!r})",
        "argument": "passed on this invocation",
        "settings": "environment / .env",
    }.get(creds.source, creds.source)
    pw_shape = f"{len(creds.reveal_password())} characters" if creds.complete else "NOT SET"

    lines = [
        "MeroShare connection — what is about to happen:",
        "",
        f"  Destination host   : {host}  (CDSC, over HTTPS)",
        f"  Login endpoint     : POST {settings.meroshare_base_url}{ENDPOINTS['auth']}",
        "  Sent in that call  : your DP/client id, your username, your password",
        f"  DP / client id     : {dp_shape} (not shown)",
        f"  Username           : {user_shape} (not shown)",
        f"  Password           : {pw_shape}, read from {pw_source} (never shown)",
        "",
        "  Then, READ-ONLY:",
        f"    GET  {ENDPOINTS['own_detail']}     your demat number",
        f"    POST {ENDPOINTS['portfolio']}   holdings and balances",
        f"    POST {ENDPOINTS['transactions']} transaction history",
        "",
        "  Cost basis (WACC) is NOT read: every CDSC purchase-history endpoint",
        "  refuses this account. Use `meroshare import` with a CSV export for it.",
        "",
        "  This tool CANNOT apply for an IPO (ASBA) and CANNOT place an order.",
        "  Nothing on the CDSC side is modified.",
        "",
        "  Stored locally     : holdings and transactions, in your own database.",
        "  NEVER stored       : your password, username, or session token —",
        "                       no database column exists for them.",
        "  Logged             : endpoint names and row counts only, never a",
        "                       response body and never a credential.",
        "",
        "  Note: this automates a login-gated portal. It is your own account and",
        "  your own data, but CDSC's terms of service may not permit automation.",
        "  That call is yours. `meroshare import` reads a CSV/pasted export",
        "  instead, with no credentials stored at all.",
    ]
    if resolution.notes:
        lines += ["", "  Credential resolution notes:"]
        lines += [f"    - {n}" for n in resolution.notes]
    if not creds.complete:
        lines += [
            "",
            "  INCOMPLETE: missing " + ", ".join(creds.missing()) + ".",
            "  Connecting will fail until those are set.",
        ]
    return "\n".join(lines)


@dataclass(frozen=True)
class OwnDetail:
    """The account identifiers a portfolio read needs. Not a credential."""

    demat: str = ""
    client_code: str = ""
    boid: str = ""


@dataclass(frozen=True)
class ConnectionResult:
    """Outcome of :func:`connect` — a login probe that fetches nothing else."""

    ok: bool
    detail: OwnDetail | None = None
    message: str = ""


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(str(value).replace(",", "")))
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _as_date(value: Any) -> date | None:
    if not value:
        return None
    text = str(value).strip()
    for cut in (" ", "T"):
        if cut in text:
            text = text.split(cut)[0]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _first(payload: dict, keys: tuple[str, ...]) -> list[dict]:
    """First list-valued key present, or ``[]``. Tolerates a bare list body."""
    for key in keys:
        got = payload.get(key)
        if isinstance(got, list):
            return [row for row in got if isinstance(row, dict)]
    return []


def _pick(row: dict, *names: str) -> Any:
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
    return None


class MeroShareClient:
    """Logs in once, then reads. Every boundary is injectable for testing.

    ``http`` takes an ``httpx.Client``; tests pass one built on
    ``httpx.MockTransport`` so the whole suite runs with no network and no
    credentials. ``credentials`` overrides resolution entirely.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        credentials: MeroShareCredentials | None = None,
        http: httpx.Client | None = None,
        require_enabled: bool = True,
    ) -> None:
        self.settings = ensure_enabled(settings) if require_enabled else (
            settings or get_settings()
        )
        if credentials is None:
            credentials = resolve_credentials(self.settings).credentials
        self.credentials = credentials
        self._owns_http = http is None
        self._http = http or httpx.Client(timeout=self.settings.request_timeout)
        self._token: str | None = None
        self._detail: OwnDetail | None = None

    # ---- lifecycle ------------------------------------------------------
    def logout(self) -> bool:
        """Release the server-side session. Returns whether CDSC confirmed it.

        This matters more than it looks: **CDSC permits one live session per
        account.** Abandoning a token instead of logging out makes the *next*
        login fail with a 500 until the old session ages out, which reads like a
        broken client and is really an un-hung-up phone. Failure is swallowed —
        a logout that didn't land must not mask the work that already succeeded.
        """
        if not self._token:
            return False
        try:
            response = self._request("GET", self._url("logout"), what="logout")
            ok = response.status_code < 400
        except MeroShareError:
            ok = False
        self._token = None
        log.debug("meroshare: logout %s", "ok" if ok else "not confirmed")
        return ok

    def close(self) -> None:
        """Log out, then drop the connection. Safe to call twice."""
        self.logout()
        if self._owns_http:
            self._http.close()
        self._token = None

    def __enter__(self) -> MeroShareClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @property
    def logged_in(self) -> bool:
        return bool(self._token)

    def _url(self, key: str) -> str:
        return self.settings.meroshare_base_url.rstrip("/") + ENDPOINTS[key]

    def _safe(self, text: object) -> str:
        """Redact, then strip anything that could be a response body."""
        return self.credentials.redact(redact(text))

    # ---- transport ------------------------------------------------------
    def _request(
        self,
        method: str,
        url: str,
        *,
        json_body: dict | None = None,
        authorised: bool = True,
        what: str = "",
    ) -> httpx.Response:
        """One request. The only place an ``httpx`` exception is allowed to exist.

        No retries: a rejected login must fail once (retrying locks accounts),
        and a read is cheap to re-run by hand. Exception messages are built from
        the endpoint name and status code only — never from the response body,
        and never from ``exc`` itself, since ``httpx.HTTPStatusError`` carries
        ``.request`` whose ``.content`` is the login JSON.

        The cookie jar is cleared before every call. That is not tidiness: the
        login sets F5 cookies which, replayed on a read, make the WAF return an
        HTML rejection page under status 200. See the endpoint map.
        """
        headers = {**BROWSER_HEADERS}
        if authorised:
            if not self._token:
                raise MeroShareAuthError("not logged in — call login() first")
            headers["Authorization"] = self._token
        else:
            headers["Authorization"] = UNAUTHENTICATED_TOKEN
        label = what or url.rsplit("/", 2)[-2:][0]
        log.debug("meroshare: %s %s", method, label)  # endpoint name only
        try:
            self._http.cookies.clear()
        except AttributeError:  # a stub transport without a jar
            pass
        transport_error: str | None = None
        try:
            return self._http.request(method, url, json=json_body, headers=headers)
        except httpx.TimeoutException:
            transport_error = (
                f"MeroShare timed out on {label} after {self.settings.request_timeout}s"
            )
        except httpx.HTTPError as exc:
            transport_error = (
                f"MeroShare transport failure on {label}: {type(exc).__name__}"
            )
        except Exception as exc:  # noqa: BLE001 - third-party transports are duck-typed
            # A custom/mock transport is allowed to raise outside httpx's
            # hierarchy.  Do not let its message (which may contain the login
            # JSON, a token, or an arbitrary response body) escape through the
            # client.  Keep only the exception type.
            transport_error = (
                f"MeroShare transport failure on {label}: {type(exc).__name__}"
            )
        # Raise after leaving the ``except`` block.  Besides ``from None``, this
        # prevents Python from retaining the original exception as
        # ``__context__`` where a caller could inspect its request/body.
        if transport_error is not None:
            raise MeroShareFetchError(transport_error)

    def _json(self, response: httpx.Response, what: str) -> Any:
        try:
            return response.json()
        except ValueError:
            raise MeroShareFetchError(
                f"MeroShare returned a non-JSON body for {what} "
                f"(status {response.status_code}, {len(response.content)} bytes)"
            ) from None

    def _check_status(self, response: httpx.Response, what: str) -> None:
        if response.status_code in (401, 403):
            raise MeroShareAuthError(
                f"MeroShare refused {what} with {response.status_code} — the session "
                "may have expired, or the credentials are wrong"
            )
        if response.status_code >= 400:
            # Status only. The body is not included anywhere, at any level.
            raise MeroShareFetchError(
                f"MeroShare returned {response.status_code} for {what}"
            )
        # A 200 that is really a WAF block. Checked after the status checks so a
        # genuine 4xx still reports its status, and phrased so the reader knows
        # this is infrastructure between us and CDSC, not CDSC saying no.
        if _WAF_MARKER in response.text:
            raise MeroShareFetchError(
                f"MeroShare's web firewall rejected {what} (HTTP 200 with an HTML "
                "rejection page). This is the CDSC edge, not a login problem — the "
                "usual cause is replayed cookies or an unrecognised header set."
            )

    # ---- login ----------------------------------------------------------
    def login(self) -> None:
        """Authenticate and hold the session token in memory only.

        The token is never written to disk, never logged, and has no database
        column. It lives on this instance and dies with :meth:`close`.
        """
        creds = self.credentials
        try:
            creds.require_complete()
        except MeroShareCredentialError as exc:
            raise MeroShareAuthError(self._safe(exc)) from None

        # `clientId` must be an int — the string form is refused outright.
        body = {
            "clientId": _as_int(creds.dp_id),
            "username": creds.username,
            "password": creds.reveal_password(),
        }
        response = self._request(
            "POST", self._url("auth"), json_body=body, authorised=False, what="login"
        )
        if response.status_code in (401, 403):
            raise MeroShareAuthError(
                "MeroShare rejected the login (bad DP id, username or password). "
                "Not retrying — repeated failures can lock the account."
            )
        if response.status_code >= 500:
            # Verified live: after a successful login (even one followed by a
            # clean logout) CDSC answers the next login with
            # 500 "Unable to process request at the moment" for a cooldown
            # period. It is a throttle, not a broken request, and it does NOT
            # consume a password attempt — but retrying it in a loop is still
            # abuse, so this raises once with the actual remedy.
            raise MeroShareAuthError(
                f"MeroShare returned {response.status_code} for login. CDSC throttles "
                "repeated logins: wait a few minutes before trying again. Log in once "
                "per run and reuse the session — this is not a credential problem."
            )
        self._check_status(response, "login")

        token = response.headers.get("Authorization") or response.headers.get("authorization")
        if not token:
            payload = self._json(response, "login")
            if isinstance(payload, dict):
                token = payload.get("accessToken") or payload.get("token") or ""
        if not token:
            raise MeroShareAuthError(
                "MeroShare login returned no Authorization token "
                f"(status {response.status_code}) — the login response shape may have "
                "changed; see the endpoint map in nepse_trader/meroshare/client.py"
            )
        self._token = str(token)
        log.debug("meroshare: login ok")  # no token, no username

    # ---- reads ----------------------------------------------------------
    def own_detail(self) -> OwnDetail:
        """The demat/client identifiers the portfolio read needs. Cached."""
        if self._detail is not None:
            return self._detail
        response = self._request("GET", self._url("own_detail"), what="own detail")
        self._check_status(response, "own detail")
        payload = self._json(response, "own detail")
        if not isinstance(payload, dict):
            raise MeroShareFetchError("MeroShare own-detail body was not a JSON object")
        self._detail = OwnDetail(
            demat=str(_pick(payload, "demat", "dematNumber") or ""),
            client_code=str(_pick(payload, "clientCode", "clientCodeId") or ""),
            boid=str(_pick(payload, "boid", "boId") or ""),
        )
        return self._detail

    def fetch_holdings(self) -> list[MeroShareHolding]:
        """Current holdings and balances.

        ``wacc`` is ``None`` on every row: CDSC's purchase-history endpoints are
        not reachable (see the endpoint map). Cost basis comes from
        :mod:`nepse_trader.meroshare.importer`, and a ``None`` here is what lets
        the advisor say "cost basis unknown" instead of assuming zero.
        """
        detail = self.own_detail()
        rows = self._paged(
            self._url("portfolio"),
            "portfolio",
            lambda page: {
                "sortBy": "script",
                "sortAsc": True,
                "script": None,
                "clientCode": detail.client_code,
                "demat": [detail.demat] if detail.demat else [],
                "page": page,
                "size": PORTFOLIO_PAGE_SIZE,
            },
            HOLDINGS_LIST_KEYS,
        )
        holdings = [self._to_holding(row, detail) for row in rows]
        holdings = [h for h in holdings if h is not None]
        log.debug("meroshare: %d holdings", len(holdings))  # count only
        return holdings

    def fetch_portfolio(self) -> MeroSharePortfolio:
        return MeroSharePortfolio(
            holdings=self.fetch_holdings(), fetched_at=datetime.now(UTC), source="meroshare"
        )

    def fetch_transactions(self) -> list[MeroShareTransaction]:
        """Demat transaction history. Returns ``[]`` when the read fails.

        A missing history must not sink a holdings sync — holdings are the thing
        the user asked for, history is a bonus.

        ``boid`` carries the **16-digit demat**, not ``OwnDetail.boid``. CDSC
        answers the real BOID with ``404 Unauthorized``, which looks like an auth
        failure and isn't one.
        """
        detail = self.own_detail()
        try:
            rows = self._paged(
                self._url("transactions"),
                "transactions",
                lambda page: {
                    "boid": detail.demat,
                    "clientCode": detail.client_code,
                    "script": None,
                    "requestTypeScript": False,
                    "fromDate": None,
                    "toDate": None,
                    "page": page,
                    "size": PORTFOLIO_PAGE_SIZE,
                },
                TRANSACTIONS_LIST_KEYS,
            )
        except MeroShareFetchError as exc:
            log.debug("meroshare: transaction history unavailable: %s", self._safe(exc))
            return []
        out = [self._to_transaction(row, detail) for row in rows]
        return [t for t in out if t is not None]

    def _paged(
        self,
        url: str,
        what: str,
        body_for_page: Callable[[int], dict[str, Any]],
        list_keys: tuple[str, ...],
    ) -> list[dict]:
        """Walk pages until a short page arrives. Bounded, so a broken
        ``totalItems`` can't spin forever.

        The two endpoints take genuinely different bodies — ``myPortfolio`` wants
        ``demat`` as a list, ``myTransaction`` wants ``boid`` as a string — so the
        caller supplies the body rather than patching a shared template.
        """
        collected: list[dict] = []
        for page in range(1, 21):
            response = self._request("POST", url, json_body=body_for_page(page), what=what)
            self._check_status(response, what)
            payload = self._json(response, what)
            if isinstance(payload, list):
                rows = [r for r in payload if isinstance(r, dict)]
            elif isinstance(payload, dict):
                rows = _first(payload, list_keys)
            else:
                raise MeroShareFetchError(f"MeroShare {what} body was neither list nor object")
            collected.extend(rows)
            if len(rows) < PORTFOLIO_PAGE_SIZE:
                break
        return collected

    # ---- row mapping ----------------------------------------------------
    def _to_holding(self, row: dict, detail: OwnDetail) -> MeroShareHolding | None:
        # "script" (not "scrip") is what the live API returns. Both are accepted:
        # the CSV importer's headers use "Scrip", and this mapper serves neither
        # exclusively.
        symbol = _pick(row, "script", "scrip", "symbol", "scripName")
        if not symbol:
            return None
        return MeroShareHolding(
            symbol=str(symbol),
            current_balance=_as_int(_pick(row, "currentBalance", "balance", "quantity")) or 0,
            wacc=_as_float(_pick(row, "wacc", "waccValue", "averageBuyRate")),
            demat_number=str(_pick(row, "demat", "dematNumber") or detail.demat or ""),
            isin=_pick(row, "isin", "isinNumber"),
            script_desc=_pick(row, "scriptDesc", "scripDesc", "companyName", "description"),
            previous_balance=_as_int(_pick(row, "previousBalance")),
            pledged_balance=_as_int(_pick(row, "pledgedBalance", "haltedBalance")),
            previous_closing_price=_as_float(
                _pick(row, "previousClosingPrice", "lastTransactionPrice")
            ),
            last_transaction_date=_as_date(_pick(row, "lastTransactionDate")),
            source="meroshare",
        )

    def _to_transaction(self, row: dict, detail: OwnDetail) -> MeroShareTransaction | None:
        symbol = _pick(row, "script", "scrip", "symbol", "scripName")
        when = _as_date(_pick(row, "transactionDate", "date", "txnDate"))
        if not symbol or when is None:
            return None
        kind = str(_pick(row, "historyDesc", "transactionType", "type", "historyDescription") or "")
        # Live rows carry separate creditQty/debitQty columns, with "-" in the one
        # that doesn't apply. Those columns decide the sign; the description text
        # is only consulted when neither is populated.
        credit = _as_float(_pick(row, "creditQty"))
        debit = _as_float(_pick(row, "debitQty"))
        if credit:
            quantity = int(abs(credit))
        elif debit:
            quantity = -int(abs(debit))
        else:
            quantity = _as_int(_pick(row, "tranactionQty", "quantity", "transactionQuantity")) or 0
            if quantity > 0 and any(
                w in kind.upper() for w in ("DEBIT", "SELL", "TRANSFER OUT")
            ):
                quantity = -quantity
        return MeroShareTransaction(
            symbol=str(symbol),
            transaction_date=when,
            quantity=quantity,
            transaction_type=str(_pick(row, "transCode", "transactionType", "type") or ""),
            description=kind or None,
            price=_as_float(_pick(row, "rate", "price")),
            balance_after=_as_int(
                _pick(row, "balAfterTrans", "balanceAfterTransaction", "balance")
            ),
            reference=(
                str(_pick(row, "transCode", "referenceNumber", "reference") or "") or None
            ),
            demat_number=str(_pick(row, "demat", "dematNumber") or detail.demat or ""),
            source="meroshare",
        )


def connect(
    settings: Settings | None = None,
    *,
    credentials: MeroShareCredentials | None = None,
    http: httpx.Client | None = None,
) -> ConnectionResult:
    """Log in and read the account identifiers — nothing else. The other half of
    the confirmation flow: the CLI prints :func:`connection_disclosure`, gets a
    yes, then calls this. Never prompts; there is no ``input()`` in this package.
    """
    settings = ensure_enabled(settings)
    client = MeroShareClient(settings, credentials=credentials, http=http)
    try:
        client.login()
        detail = client.own_detail()
        return ConnectionResult(
            ok=True,
            detail=detail,
            # The detail object is needed internally for the subsequent read,
            # but its demat/client identifiers are account data.  Keep the
            # public status message generic so a caller cannot accidentally
            # log or display a full identifier.
            message="connected; account detail read successfully",
        )
    except MeroShareError as exc:
        return ConnectionResult(ok=False, message=client._safe(exc))
    finally:
        client.close()
