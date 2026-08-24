"""Offline contracts for the read-only MeroShare mirror.

Every HTTP interaction here uses ``httpx.MockTransport``. These tests must stay
offline: a regression that turns a unit test into a login attempt would expose
an account and make the suite depend on CDSC availability.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date

import httpx
import pytest

from nepse_trader.config import Settings
from nepse_trader.meroshare.client import (
    ENDPOINTS,
    MeroShareAuthError,
    MeroShareClient,
    MeroShareDisabledError,
    MeroShareFetchError,
    connect,
    connection_disclosure,
)
from nepse_trader.meroshare.credentials import MeroShareCredentials, resolve_credentials
from nepse_trader.meroshare.importer import MeroShareImportError, parse_holdings_csv
from nepse_trader.meroshare.models import MeroShareHolding, MeroShareTransaction
from nepse_trader.meroshare.privacy import demat_fingerprint
from nepse_trader.meroshare.sync import (
    compare_with_paper,
    stored_holdings,
    sync_from_client,
    sync_from_csv,
    sync_payload,
)
from nepse_trader.storage import Storage
from nepse_trader.storage.migrations import (
    _m0006_meroshare,
    _m0010_meroshare_privacy,
    _m0012_meroshare_demat_privacy,
)

DP_ID = "12345"
USERNAME = "offline-user"
PASSWORD = "offline-password"
TOKEN = "Bearer offline-token"
DEMAT = "1301230000000001"


def _settings(**overrides) -> Settings:
    values = {
        "meroshare_enabled": True,
        "meroshare_base_url": "https://meroshare.test/api",
        "meroshare_dp_id": DP_ID,
        "meroshare_username": USERNAME,
        "meroshare_password": PASSWORD,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _holding(
    symbol: str = "NABIL",
    quantity: int = 10,
    *,
    demat: str = DEMAT,
    wacc: float | None = 500.0,
) -> MeroShareHolding:
    return MeroShareHolding(
        symbol=symbol,
        current_balance=quantity,
        demat_number=demat,
        wacc=wacc,
        source="test",
    )


def _transaction(symbol: str = "NABIL") -> MeroShareTransaction:
    return MeroShareTransaction(
        symbol=symbol,
        transaction_date=date(2026, 8, 23),
        quantity=10,
        transaction_type="CR",
        demat_number=DEMAT,
        reference="offline-ref",
        source="test",
    )


@pytest.fixture
def storage(tmp_path):
    instance = Storage(tmp_path / "meroshare.sqlite")
    try:
        yield instance
    finally:
        instance.close()


class TestCredentials:
    def test_explicit_password_wins_over_keyring_and_settings(self):
        settings = _settings(meroshare_use_keyring=True)
        result = resolve_credentials(
            settings,
            password="argument-password",
            keyring_getter=lambda *_: ("keyring-password", ""),
        )

        assert result.credentials.source == "argument"
        assert result.credentials.reveal_password() == "argument-password"

    def test_keyring_password_wins_over_settings(self):
        settings = _settings(meroshare_use_keyring=True)
        result = resolve_credentials(
            settings,
            keyring_getter=lambda *_: ("keyring-password", ""),
        )

        assert result.credentials.source == "keyring"
        assert result.credentials.reveal_password() == "keyring-password"

    def test_redacted_rendering_and_messages_hide_full_login_triple(self):
        credentials = MeroShareCredentials(DP_ID, USERNAME, PASSWORD)
        rendered = f"{credentials!r} {credentials} {credentials:>20}"
        masked = credentials.redact(f"{DP_ID} {USERNAME} {PASSWORD}")

        for secret in (DP_ID, USERNAME, PASSWORD):
            assert secret not in rendered
            assert secret not in masked

    def test_redaction_does_not_skip_short_credentials(self):
        credentials = MeroShareCredentials("d", "u", "p")

        masked = credentials.redact("d u p")

        assert masked == "***REDACTED*** ***REDACTED*** ***REDACTED***"

    def test_disclosure_describes_read_only_scope_without_identifiers(self):
        disclosure = connection_disclosure(_settings())

        for secret in (DP_ID, USERNAME, PASSWORD):
            assert secret not in disclosure
        assert "READ-ONLY" in disclosure
        assert "not shown" in disclosure
        assert "CANNOT place an order" in disclosure

    def test_disabled_integration_refuses_client_construction(self):
        settings = _settings(meroshare_enabled=False)

        with pytest.raises(MeroShareDisabledError, match="disabled"):
            MeroShareClient(settings)


class TestClient:
    def test_login_read_logout_contract_uses_only_mock_transport(self):
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            path = request.url.path
            if path.endswith(ENDPOINTS["auth"]):
                body = json.loads(request.content)
                assert body == {
                    "clientId": int(DP_ID),
                    "username": USERNAME,
                    "password": PASSWORD,
                }
                return httpx.Response(
                    200,
                    headers={"Authorization": TOKEN, "Set-Cookie": "session=unsafe; Path=/"},
                    json={},
                )
            assert request.headers.get("authorization") == TOKEN
            assert request.headers.get("cookie") is None
            if path.endswith(ENDPOINTS["own_detail"]):
                return httpx.Response(
                    200,
                    json={"demat": DEMAT, "clientCode": "C-01", "boid": "eight-digit"},
                )
            if path.endswith(ENDPOINTS["portfolio"]):
                body = json.loads(request.content)
                assert body["demat"] == [DEMAT]
                assert body["clientCode"] == "C-01"
                return httpx.Response(
                    200,
                    json={
                        "meroShareMyPortfolio": [
                            {"script": "NABIL", "currentBalance": "120"}
                        ]
                    },
                )
            if path.endswith(ENDPOINTS["transactions"]):
                body = json.loads(request.content)
                assert body["boid"] == DEMAT
                assert body["boid"] != "eight-digit"
                return httpx.Response(
                    200,
                    json={
                        "transactionView": [
                            {
                                "script": "NABIL",
                                "transactionDate": "2026-08-20",
                                "creditQty": "20",
                                "debitQty": "-",
                                "transCode": "CR",
                            },
                            {
                                "script": "NABIL",
                                "transactionDate": "2026-08-21",
                                "creditQty": "-",
                                "debitQty": "5",
                                "transCode": "DR",
                            },
                        ]
                    },
                )
            if path.endswith(ENDPOINTS["logout"]):
                return httpx.Response(200, json={})
            raise AssertionError(f"unexpected offline request {request.method} {path}")

        http = httpx.Client(transport=httpx.MockTransport(handler))
        client = MeroShareClient(
            _settings(),
            credentials=MeroShareCredentials(DP_ID, USERNAME, PASSWORD),
            http=http,
        )
        client.login()
        holdings = client.fetch_holdings()
        transactions = client.fetch_transactions()
        assert client.logout() is True

        assert [h.current_balance for h in holdings] == [120]
        assert [t.quantity for t in transactions] == [20, -5]
        assert client.logged_in is False
        assert [request.url.path for request in seen] == [
            "/api/meroShare/auth/",
            "/api/meroShare/ownDetail/",
            "/api/meroShareView/myPortfolio/",
            "/api/meroShareView/myTransaction/",
            "/api/meroShare/auth/logout/",
        ]

    @pytest.mark.parametrize("status", [401, 403])
    def test_refused_login_never_echoes_response_body_or_credentials(self, status):
        remote_body = f"remote says {PASSWORD} {USERNAME} {DP_ID}"

        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(status, text=remote_body)

        client = MeroShareClient(
            _settings(), http=httpx.Client(transport=httpx.MockTransport(handler))
        )
        with pytest.raises(MeroShareAuthError) as caught:
            client.login()

        text = str(caught.value)
        for secret in (remote_body, DP_ID, USERNAME, PASSWORD):
            assert secret not in text

    def test_waf_html_on_200_is_not_treated_as_a_success_or_echoed(self):
        remote_body = f"<title>Request Rejected</title>{PASSWORD} raw remote response"

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith(ENDPOINTS["auth"]):
                return httpx.Response(200, headers={"Authorization": TOKEN}, json={})
            return httpx.Response(200, text=remote_body)

        client = MeroShareClient(
            _settings(), http=httpx.Client(transport=httpx.MockTransport(handler))
        )
        client.login()
        with pytest.raises(MeroShareFetchError) as caught:
            client.own_detail()

        assert "web firewall" in str(caught.value)
        assert remote_body not in str(caught.value)
        assert PASSWORD not in str(caught.value)

    def test_transport_error_never_echoes_exception_text(self):
        body = f"transport response {PASSWORD} {USERNAME}"

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError(body, request=request)

        client = MeroShareClient(
            _settings(), http=httpx.Client(transport=httpx.MockTransport(handler))
        )
        with pytest.raises(MeroShareFetchError) as caught:
            client.login()

        assert body not in str(caught.value)
        assert PASSWORD not in str(caught.value)
        assert "ConnectError" in str(caught.value)

    def test_unexpected_transport_error_does_not_echo_text_or_retain_context(self):
        body = f"custom transport leaked {PASSWORD} {USERNAME}"

        def handler(request: httpx.Request) -> httpx.Response:
            raise RuntimeError(body)

        client = MeroShareClient(
            _settings(), http=httpx.Client(transport=httpx.MockTransport(handler))
        )
        with pytest.raises(MeroShareFetchError) as caught:
            client.login()

        assert str(caught.value) == "MeroShare transport failure on login: RuntimeError"
        assert caught.value.__context__ is None
        for secret in (body, PASSWORD, USERNAME, DP_ID):
            assert secret not in str(caught.value)

    def test_transaction_history_failure_returns_empty_after_holdings_succeed(self):
        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path.endswith(ENDPOINTS["auth"]):
                return httpx.Response(200, headers={"Authorization": TOKEN}, json={})
            if path.endswith(ENDPOINTS["own_detail"]):
                return httpx.Response(200, json={"demat": DEMAT, "clientCode": "C-01"})
            if path.endswith(ENDPOINTS["portfolio"]):
                return httpx.Response(
                    200, json={"meroShareMyPortfolio": [{"script": "NABIL", "currentBalance": 3}]}
                )
            if path.endswith(ENDPOINTS["transactions"]):
                return httpx.Response(404, text=f"do not leak {PASSWORD}")
            raise AssertionError(path)

        client = MeroShareClient(
            _settings(), http=httpx.Client(transport=httpx.MockTransport(handler))
        )
        client.login()
        assert [h.symbol for h in client.fetch_holdings()] == ["NABIL"]
        assert client.fetch_transactions() == []

    def test_endpoint_map_has_only_login_logout_and_read_routes(self):
        paths = " ".join(ENDPOINTS.values()).lower()
        for forbidden in ("asba", "ipo", "order", "apply", "bid", "buy", "sell"):
            assert forbidden not in paths
        assert set(ENDPOINTS) == {"auth", "logout", "own_detail", "portfolio", "transactions"}

    def test_connect_status_message_does_not_expose_account_identifier(self):
        def handler(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path.endswith(ENDPOINTS["auth"]):
                return httpx.Response(200, headers={"Authorization": TOKEN}, json={})
            if path.endswith(ENDPOINTS["own_detail"]):
                return httpx.Response(200, json={"demat": DEMAT, "clientCode": "C-01"})
            if path.endswith(ENDPOINTS["logout"]):
                return httpx.Response(200, json={})
            raise AssertionError(path)

        result = connect(
            _settings(),
            credentials=MeroShareCredentials(DP_ID, USERNAME, PASSWORD),
            http=httpx.Client(transport=httpx.MockTransport(handler)),
        )

        assert result.ok is True
        assert result.message == "connected; account detail read successfully"
        assert DEMAT not in result.message
        assert DP_ID not in result.message


class TestImporter:
    def test_csv_parser_handles_bom_semicolon_aliases_money_and_total(self):
        text = (
            "\ufeffScrip;Kitta;Weighted Average Cost;Previous Close;ISIN;BOID\n"
            "nabil;1,234;Rs. 505.50;NPR 550.25;NP0000000001;1301230000000001\n"
            "Total;1,234;;;;\n"
        )

        holdings = parse_holdings_csv(text)

        assert len(holdings) == 1
        holding = holdings[0]
        assert holding.symbol == "NABIL"
        assert holding.current_balance == 1234
        assert holding.wacc == pytest.approx(505.5)
        assert holding.previous_closing_price == pytest.approx(550.25)
        assert holding.demat_number == DEMAT

    def test_csv_parser_refuses_unrecognisable_headers(self):
        with pytest.raises(MeroShareImportError, match="symbol column"):
            parse_holdings_csv("a,b,c\n1,2,3\n")


class TestPersistence:
    def test_idempotent_sync_keeps_one_row_per_holding_and_transaction(self, storage):
        holdings = [_holding()]
        transactions = [_transaction()]

        assert sync_payload(storage._conn, holdings, transactions).ok
        assert sync_payload(storage._conn, holdings, transactions).ok

        assert storage._conn.execute("SELECT COUNT(*) FROM ms_holdings").fetchone()[0] == 1
        assert storage._conn.execute("SELECT COUNT(*) FROM ms_transactions").fetchone()[0] == 1
        holding_columns = {
            row[1] for row in storage._conn.execute("PRAGMA table_info(ms_holdings)")
        }
        transaction_columns = {
            row[1] for row in storage._conn.execute("PRAGMA table_info(ms_transactions)")
        }
        for forbidden in (
            "dp_id",
            "password",
            "username",
            "token",
            "session",
            "demat_number",
        ):
            assert forbidden not in holding_columns | transaction_columns
        stored_dump = " ".join(
            str(value)
            for table in ("ms_holdings", "ms_transactions")
            for row in storage._conn.execute(f"SELECT * FROM {table}")
            for value in row
        )
        assert DEMAT not in stored_dump
        assert demat_fingerprint(DEMAT) in stored_dump

    def test_demat_migration_hashes_legacy_rows_and_keeps_multiple_demats(self):
        import sqlite3

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        _m0006_meroshare(conn)
        conn.execute(
            """INSERT INTO ms_holdings
               (symbol, demat_number, current_balance, source, synced_at)
               VALUES (?,?,?,?,?)""",
            ("NABIL", DEMAT, 10, "legacy", "2026-08-24T00:00:00Z"),
        )
        second_demat = "1301230000000002"
        conn.execute(
            """INSERT INTO ms_holdings
               (symbol, demat_number, current_balance, source, synced_at)
               VALUES (?,?,?,?,?)""",
            ("NABIL", second_demat, 20, "legacy", "2026-08-24T00:00:00Z"),
        )
        conn.execute(
            """INSERT INTO ms_transactions
               (txn_id, symbol, demat_number, transaction_date, source, synced_at)
               VALUES (?,?,?,?,?,?)""",
            ("txn-1", "NABIL", DEMAT, "2026-08-23", "legacy", "2026-08-24T00:00:00Z"),
        )
        conn.commit()

        _m0012_meroshare_demat_privacy(conn)

        holding_columns = {row[1] for row in conn.execute("PRAGMA table_info(ms_holdings)")}
        transaction_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(ms_transactions)")
        }
        assert "demat_number" not in holding_columns | transaction_columns
        assert {row[0] for row in conn.execute("SELECT demat_hash FROM ms_holdings")} == {
            demat_fingerprint(DEMAT),
            demat_fingerprint(second_demat),
        }
        dump = " ".join(
            str(value)
            for table in ("ms_holdings", "ms_transactions")
            for row in conn.execute(f"SELECT * FROM {table}")
            for value in row
        )
        assert DEMAT not in dump
        assert second_demat not in dump
        assert "0001" in dump and "0002" in dump

    def test_legacy_privacy_migration_removes_identifier_and_preserves_holdings(self, storage):
        conn = storage._conn
        sync_payload(conn, [_holding(quantity=42)])
        conn.execute("ALTER TABLE ms_holdings ADD COLUMN dp_id TEXT")
        conn.execute("ALTER TABLE ms_holdings ADD COLUMN client_id TEXT")
        conn.execute("ALTER TABLE ms_holdings ADD COLUMN client_code TEXT")
        conn.execute("UPDATE ms_holdings SET dp_id=?", (DP_ID,))
        conn.execute("UPDATE ms_holdings SET client_id=?, client_code=?", ("client-secret", "code-secret"))
        conn.commit()

        _m0010_meroshare_privacy(conn)
        conn.commit()

        columns = {row[1] for row in conn.execute("PRAGMA table_info(ms_holdings)")}
        assert "dp_id" not in columns
        assert "client_id" not in columns
        assert "client_code" not in columns
        assert stored_holdings(conn)[0].current_balance == 42
        dumped = " ".join(str(value) for row in conn.execute("SELECT * FROM ms_holdings") for value in row)
        for secret in (DP_ID, "client-secret", "code-secret"):
            assert secret not in dumped

    def test_csv_import_failure_uses_safe_stable_message(self, storage):
        private_header = "ACCOUNT-CLIENT-12345,private-password-column"
        result = sync_from_csv(storage._conn, f"{private_header}\naccount,secret")

        assert result.ok is False
        assert result.error == "MeroShare CSV import failed: invalid holdings export"
        row = storage._conn.execute(
            "SELECT status, error FROM ms_sync_log ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert tuple(row) == ("error", result.error)
        assert "ACCOUNT-CLIENT-12345" not in result.error
        assert "private-password-column" not in row[1]

    def test_failed_payload_sync_is_atomic_and_logs_only_a_safe_error(self, storage):
        conn = storage._conn
        assert sync_payload(conn, [_holding(quantity=10)]).ok
        conn.execute("""
            CREATE TRIGGER reject_test_transaction
            BEFORE INSERT ON ms_transactions
            BEGIN
                SELECT RAISE(ABORT, 'untrusted trigger text must not be stored');
            END
        """)
        conn.commit()

        result = sync_payload(conn, [_holding(quantity=99)], [_transaction()])

        assert result.ok is False
        assert result.error == "MeroShare persistence failed: IntegrityError"
        assert stored_holdings(conn)[0].current_balance == 10
        assert conn.execute("SELECT COUNT(*) FROM ms_transactions").fetchone()[0] == 0
        row = conn.execute("SELECT status, error FROM ms_sync_log ORDER BY id DESC LIMIT 1").fetchone()
        assert tuple(row) == ("error", result.error)
        assert "untrusted trigger text" not in row["error"]

    def test_unexpected_client_exception_does_not_reach_result_log_or_database(self, storage, caplog):
        class FailingClient:
            logged_in = False
            credentials = MeroShareCredentials(DP_ID, USERNAME, PASSWORD)

            def login(self):
                raise RuntimeError(f"remote body: {PASSWORD}; internal=do-not-store")

        assert sync_payload(storage._conn, [_holding(quantity=10)]).ok
        caplog.set_level(logging.WARNING, logger="nepse_trader.meroshare.sync")
        result = sync_from_client(storage._conn, FailingClient())
        stored_error = storage._conn.execute(
            "SELECT error FROM ms_sync_log ORDER BY id DESC LIMIT 1"
        ).fetchone()[0]

        assert result.ok is False
        assert result.error == "MeroShare fetch failed: RuntimeError"
        assert stored_error == result.error
        assert stored_holdings(storage._conn)[0].current_balance == 10
        for leaked in (PASSWORD, USERNAME, DP_ID, "internal=do-not-store", "remote body"):
            assert leaked not in result.error
            assert leaked not in stored_error
            assert leaked not in caplog.text


@dataclass
class _PaperPosition:
    symbol: str
    quantity: int
    avg_cost: float


class TestComparison:
    def test_multiple_demats_aggregate_quantity_and_weighted_wacc(self):
        real = [
            _holding(quantity=70, demat="1301230000000001", wacc=500.0),
            _holding(quantity=30, demat="1301230000000002", wacc=600.0),
        ]
        paper = [_PaperPosition("NABIL", 100, 530.0)]

        diff = compare_with_paper(real, paper)[0]

        assert diff.real_quantity == 100
        assert diff.paper_quantity == 100
        assert diff.real_wacc == pytest.approx(530.0)
        assert diff.agrees is True

    def test_unknown_wacc_on_any_demat_keeps_aggregate_wacc_unknown(self):
        real = [_holding(quantity=70, wacc=500.0), _holding(quantity=30, demat="other", wacc=None)]

        diff = compare_with_paper(real, [])[-1]

        assert diff.real_quantity == 100
        assert diff.real_wacc is None
