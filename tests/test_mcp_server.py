"""Server-layer tests: tool registry, tool call semantics, and the stdio loop.

Everything runs against a temp SQLite file seeded with a handful of reconciled
bars, so it is fully offline — the server is constructed with an explicit
``Storage``, and its pipeline is built with no source clients, so nothing here can
reach the network.

The end-to-end test drives :func:`serve_stdio` over ``io.StringIO`` rather than a
subprocess. That covers the framing (one JSON object per line, notifications
answered with silence) while staying fast and debuggable; the real subprocess path
is verified by hand with a shell pipe.
"""

from __future__ import annotations

import io
import json
import sys
from datetime import date, timedelta

import pytest

from nepse_trader.config import Settings
from nepse_trader.mcp_server.protocol import INVALID_PARAMS, METHOD_NOT_FOUND
from nepse_trader.mcp_server.server import (
    DEFAULT_PROTOCOL_VERSION,
    MAX_PRICE_BARS,
    MAX_QUANT_SYMBOLS,
    MAX_SCREEN_ROWS,
    MAX_SEARCH_RESULTS,
    MAX_SIGNAL_SYMBOLS,
    MAX_TOP_MOVERS,
    SERVER_NAME,
    MCPServer,
    build_server,
    serve_stdio,
)
from nepse_trader.meroshare.models import MeroShareHolding
from nepse_trader.meroshare.sync import sync_payload
from nepse_trader.models import PriceBar, ReconciledPrice, SourceName
from nepse_trader.rag.corpus import KIND_NEWS, Document
from nepse_trader.rag.index import DocumentIndex
from nepse_trader.storage import Storage

SYMBOLS = ("NABIL", "NICA")
START = date(2026, 1, 1)
BARS_PER_SYMBOL = 60  # >= sma_cross's slow period (50), so signals actually fire


def _seed(storage: Storage) -> None:
    """Write both raw and reconciled bars: tools read from each side."""
    raw: list[PriceBar] = []
    reconciled: list[ReconciledPrice] = []
    for i, symbol in enumerate(SYMBOLS):
        price = 500.0 + i * 100.0
        for day in range(BARS_PER_SYMBOL):
            business_date = START + timedelta(days=day)
            previous = price
            # Deterministic zig-zag so signals and quant stats have something to
            # chew on, and so NABIL/NICA move in opposite directions on day 0.
            price = round(price * (1.01 if (day + i) % 2 == 0 else 0.995), 2)
            raw.append(
                PriceBar(
                    symbol=symbol,
                    business_date=business_date,
                    open=previous,
                    high=max(previous, price) + 1,
                    low=min(previous, price) - 1,
                    close=price,
                    previous_close=previous,
                    volume=1_000 + day,
                    turnover=price * (1_000 + day),
                    source=SourceName.SHARESANSAR,
                )
            )
            reconciled.append(
                ReconciledPrice(
                    symbol=symbol,
                    business_date=business_date,
                    open=previous,
                    high=max(previous, price) + 1,
                    low=min(previous, price) - 1,
                    close=price,
                    previous_close=previous,
                    volume=1_000 + day,
                    turnover=price * (1_000 + day),
                    sources_agreeing=[SourceName.SHARESANSAR],
                    sources_present=[SourceName.SHARESANSAR],
                    confidence=1.0,
                )
            )
    storage.upsert_price_bars(raw)
    storage.upsert_reconciled(reconciled)


@pytest.fixture
def storage(tmp_path) -> Storage:
    st = Storage(tmp_path / "mcp.db")
    _seed(st)
    yield st
    st.close()


@pytest.fixture
def server(tmp_path, storage) -> MCPServer:
    settings = Settings(_env_file=None, db_path=tmp_path / "mcp.db")
    return build_server(settings=settings, storage=storage)


def _call(server: MCPServer, name: str, **arguments) -> dict:
    """Invoke a tool through the dispatcher and return the raw MCP result."""
    resp = server.dispatcher.handle_request(
        _request("tools/call", {"name": name, "arguments": arguments}, request_id=1)
    )
    assert "error" not in resp, resp
    return resp["result"]


def _request(method: str, params: dict | None = None, request_id: object = 1):
    from nepse_trader.mcp_server.protocol import Request

    return Request(method=method, params=params or {}, id=request_id)


def _payload(result: dict) -> dict:
    """Parse the JSON a tool rendered into its single text content block."""
    assert result["isError"] is False, result
    assert len(result["content"]) == 1
    assert result["content"][0]["type"] == "text"
    return json.loads(result["content"][0]["text"])


# --------------------------------------------------------------- handshake


def test_initialize_advertises_tools_capability_and_server_info(server):
    result = server.initialize({})
    assert result["protocolVersion"] == DEFAULT_PROTOCOL_VERSION
    assert result["capabilities"] == {"tools": {}}
    assert result["serverInfo"]["name"] == SERVER_NAME
    assert result["serverInfo"]["version"]


def test_initialize_echoes_a_supported_client_protocol_version(server):
    result = server.initialize({"protocolVersion": "2024-11-05"})
    assert result["protocolVersion"] == "2024-11-05"


def test_initialize_falls_back_for_an_unknown_protocol_version(server):
    result = server.initialize({"protocolVersion": "1999-01-01"})
    assert result["protocolVersion"] == DEFAULT_PROTOCOL_VERSION


def test_ping_returns_an_empty_result(server):
    resp = server.dispatcher.handle_request(_request("ping"))
    assert resp["result"] == {}


def test_initialized_notification_produces_no_response(server):
    from nepse_trader.mcp_server.protocol import Request

    notification = Request(
        method="notifications/initialized", params={}, id=None, is_notification=True
    )
    assert server.dispatcher.handle_request(notification) is None


def test_unknown_method_is_method_not_found(server):
    resp = server.dispatcher.handle_request(_request("resources/list"))
    assert resp["error"]["code"] == METHOD_NOT_FOUND


# ------------------------------------------------------------- tools/list


def test_tools_list_returns_every_registered_tool(server):
    listed = server.tools_list({})["tools"]
    assert {t["name"] for t in listed} == {t.name for t in server.tools}
    assert len(listed) >= 6


def test_tools_list_includes_the_complete_trading_assistant_surface(server):
    names = {tool["name"] for tool in server.tools_list({})["tools"]}
    assert {
        "backtest",
        "screen",
        "portfolio",
        "meroshare_holdings",
        "rashifal",
        "doses",
    } <= names


def test_every_tool_has_a_description_and_a_valid_object_schema(server):
    for tool in server.tools_list({})["tools"]:
        assert tool["description"].strip(), tool["name"]
        schema = tool["inputSchema"]
        assert schema["type"] == "object", tool["name"]
        assert isinstance(schema["properties"], dict), tool["name"]
        for prop, spec in schema["properties"].items():
            assert "type" in spec, f"{tool['name']}.{prop}"
        for required in schema.get("required", []):
            assert required in schema["properties"], f"{tool['name']}.{required}"


def test_tools_list_is_json_serialisable(server):
    json.dumps(server.tools_list({}))


# ------------------------------------------------------------- tools/call


def test_tools_call_requires_a_name(server):
    resp = server.dispatcher.handle_request(_request("tools/call", {"arguments": {}}))
    assert resp["error"]["code"] == INVALID_PARAMS


def test_tools_call_rejects_an_unknown_tool_name(server):
    resp = server.dispatcher.handle_request(_request("tools/call", {"name": "drop_tables"}))
    assert resp["error"]["code"] == INVALID_PARAMS
    assert "drop_tables" in resp["error"]["message"]


def test_tools_call_rejects_non_object_arguments(server):
    resp = server.dispatcher.handle_request(
        _request("tools/call", {"name": "list_symbols", "arguments": [1, 2]})
    )
    assert resp["error"]["code"] == INVALID_PARAMS


def test_a_raising_tool_returns_is_error_not_a_jsonrpc_error(server):
    result = _call(server, "price_history", symbol="NOSUCHSYMBOL")
    assert result["isError"] is True
    assert "NOSUCHSYMBOL" in result["content"][0]["text"]


def test_the_server_survives_a_failing_tool_and_serves_the_next_call(server):
    _call(server, "price_history", symbol="NOSUCHSYMBOL")
    payload = _payload(_call(server, "list_symbols"))
    assert payload["count"] == len(SYMBOLS)


def test_bad_argument_type_is_reported_as_is_error(server):
    result = _call(server, "price_history", symbol="NABIL", limit="sixty")
    assert result["isError"] is True
    assert "limit" in result["content"][0]["text"]


def test_bad_date_string_is_reported_as_is_error(server):
    result = _call(server, "market_breadth", business_date="not-a-date")
    assert result["isError"] is True


# ------------------------------------------------------- individual tools


def test_list_symbols_returns_seeded_symbols(server):
    payload = _payload(_call(server, "list_symbols"))
    assert payload["symbols"] == sorted(SYMBOLS)
    assert payload["count"] == len(SYMBOLS)


def test_list_symbols_substring_filter_is_case_insensitive(server):
    payload = _payload(_call(server, "list_symbols", contains="nab"))
    assert payload["symbols"] == ["NABIL"]


def test_price_history_returns_bars_oldest_first_with_confidence(server):
    payload = _payload(_call(server, "price_history", symbol="nabil"))
    assert payload["symbol"] == "NABIL"
    assert payload["total_rows"] == BARS_PER_SYMBOL
    bars = payload["bars"]
    assert bars[0]["business_date"] == START.isoformat()
    assert bars[0]["business_date"] < bars[-1]["business_date"]
    assert bars[0]["confidence"] == 1.0


def test_price_history_limit_takes_the_most_recent_window(server):
    payload = _payload(_call(server, "price_history", symbol="NABIL", limit=5))
    assert payload["returned"] == 5
    assert payload["total_rows"] == BARS_PER_SYMBOL
    last_date = (START + timedelta(days=BARS_PER_SYMBOL - 1)).isoformat()
    assert payload["bars"][-1]["business_date"] == last_date


def test_market_breadth_defaults_to_the_latest_reconciled_date(server):
    payload = _payload(_call(server, "market_breadth"))
    assert payload["business_date"] == (START + timedelta(days=BARS_PER_SYMBOL - 1)).isoformat()
    assert payload["symbols"] == len(SYMBOLS)
    assert payload["advancers"] + payload["decliners"] + payload["unchanged"] == len(SYMBOLS)


def test_market_breadth_honours_an_explicit_date(server):
    target = START + timedelta(days=3)
    payload = _payload(_call(server, "market_breadth", business_date=target.isoformat()))
    assert payload["business_date"] == target.isoformat()


def test_top_movers_returns_both_sides_ranked(server):
    payload = _payload(_call(server, "top_movers", top=1))
    assert payload["gainers"] and payload["losers"]
    assert payload["gainers"][0]["change_percent"] >= payload["losers"][0]["change_percent"]


def test_latest_signals_for_named_symbols(server):
    payload = _payload(_call(server, "latest_signals", symbols=["nabil"]))
    assert payload["strategy"] == "sma_cross"
    assert payload["count"] == 1
    signal = payload["signals"][0]
    assert signal["symbol"] == "NABIL"
    assert signal["action"] in {"BUY", "SELL", "HOLD"}


def test_latest_signals_rejects_an_unknown_strategy(server):
    result = _call(server, "latest_signals", symbols=["NABIL"], strategy="astrology")
    assert result["isError"] is True
    assert "astrology" in result["content"][0]["text"]


def test_quant_stats_reports_risk_metrics_per_symbol(server):
    payload = _payload(_call(server, "quant_stats", symbols=["NABIL", "NICA"]))
    assert payload["count"] == 2
    row = payload["stats"][0]
    assert row["symbol"] == "NABIL"
    assert row["n"] == BARS_PER_SYMBOL
    for key in ("total_return_pct", "annualized_vol_pct", "sharpe", "max_drawdown_pct"):
        assert key in row


def test_quant_stats_requires_symbols(server):
    result = _call(server, "quant_stats", symbols=[])
    assert result["isError"] is True


def test_search_documents_finds_an_indexed_document(server, storage):
    DocumentIndex(storage._conn).upsert(
        [
            Document(
                doc_id="news:test:1",
                kind=KIND_NEWS,
                title="NABIL declares dividend",
                body="NABIL Bank announced a 12 percent cash dividend for the fiscal year.",
                symbol="NABIL",
                business_date=START,
                source="unit-test",
            )
        ]
    )
    payload = _payload(_call(server, "search_documents", query="dividend"))
    assert payload["count"] == 1
    hit = payload["results"][0]
    assert hit["doc_id"] == "news:test:1"
    assert hit["kind"] == KIND_NEWS
    assert "dividend" in hit["body"]


def test_search_documents_on_an_empty_corpus_returns_no_results(server):
    payload = _payload(_call(server, "search_documents", query="dividend"))
    assert payload["count"] == 0
    assert payload["results"] == []


def test_search_documents_rejects_a_bad_kind_filter_type(server):
    result = _call(server, "search_documents", query="x", kinds="news")
    assert result["isError"] is True


def test_database_stats_reports_coverage(server):
    payload = _payload(_call(server, "database_stats"))
    assert payload["symbols_with_data"] == len(SYMBOLS)
    assert payload["reconciled_rows"] == len(SYMBOLS) * BARS_PER_SYMBOL
    assert payload["latest_reconciled_date"] == (
        START + timedelta(days=BARS_PER_SYMBOL - 1)
    ).isoformat()


def test_backtest_tool_returns_nepal_costed_local_result(server):
    payload = _payload(
        _call(server, "backtest", symbol="nabil", strategy="sma_cross", cash=500_000)
    )
    assert payload["symbol"] == "NABIL"
    assert payload["bars"] == BARS_PER_SYMBOL
    assert payload["summary"]["strategy_name"] == "sma_cross"
    assert "final_equity" in payload["summary"]
    assert len(payload["trades"]) <= 100


def test_screen_tool_is_bounded_and_ranked(server):
    payload = _payload(
        _call(
            server,
            "screen",
            symbols=["NABIL", "NICA"],
            strategies=["sma_cross"],
            min_bars=20,
            rank_by="sharpe",
            limit=1,
        )
    )
    assert payload["symbols_evaluated"] == 2
    assert payload["total_rows"] == 2
    assert payload["returned"] == 1
    assert len(payload["rows"]) == 1


def test_portfolio_tool_reads_paper_and_local_meroshare_only(server, storage):
    sync_payload(
        storage._conn,
        [
            MeroShareHolding(
                symbol="NABIL",
                current_balance=10,
                wacc=500,
                demat_number="1301230000000001",
                source="test",
            )
        ],
    )
    payload = _payload(_call(server, "portfolio", include_meroshare=True))
    assert payload["paper"]["positions"] == []
    assert payload["meroshare"]["comparison"]["only_real"] == 1


def test_meroshare_holdings_masks_account_identifier_and_never_syncs(server, storage):
    sync_payload(
        storage._conn,
        [
            MeroShareHolding(
                symbol="NABIL",
                current_balance=10,
                wacc=500,
                demat_number="1301230000000001",
                source="test",
            )
        ],
    )
    attempts_before = storage._conn.execute("SELECT COUNT(*) FROM ms_sync_log").fetchone()[0]
    payload = _payload(_call(server, "meroshare_holdings"))
    attempts_after = storage._conn.execute("SELECT COUNT(*) FROM ms_sync_log").fetchone()[0]
    assert payload["count"] == 1
    assert payload["holdings"][0]["demat_last4"] == "0001"
    assert "1301230000000001" not in json.dumps(payload)
    assert attempts_after == attempts_before


# ------------------------------------------------------------ result bounds


@pytest.mark.parametrize(
    ("tool", "arguments", "field"),
    [
        ("price_history", {"symbol": "NABIL", "limit": MAX_PRICE_BARS + 1}, "limit"),
        ("top_movers", {"top": MAX_TOP_MOVERS + 1}, "top"),
        ("search_documents", {"query": "x", "limit": MAX_SEARCH_RESULTS + 1}, "limit"),
        ("screen", {"limit": MAX_SCREEN_ROWS + 1}, "limit"),
        (
            "quant_stats",
            {"symbols": [f"SYM{i}" for i in range(MAX_QUANT_SYMBOLS + 1)]},
            "symbols",
        ),
    ],
)
def test_over_the_cap_requests_are_rejected_not_silently_served(
    server, tool, arguments, field
):
    """An oversized request must fail loudly; a truncated answer would read as complete."""
    result = _call(server, tool, **arguments)
    assert result["isError"] is True
    assert field in result["content"][0]["text"]


@pytest.mark.parametrize(
    ("tool", "arguments", "cap_key"),
    [
        ("list_symbols", {}, "symbols"),
        ("latest_signals", {}, "signals"),
        ("meroshare_holdings", {}, "holdings"),
    ],
)
def test_list_returning_tools_report_how_much_they_returned(
    server, tool, arguments, cap_key
):
    """Every unbounded list carries ``returned``/``truncated`` alongside ``count``."""
    payload = _payload(_call(server, tool, **arguments))
    assert payload["returned"] == len(payload[cap_key])
    assert payload["returned"] <= payload["count"]
    assert payload["truncated"] is (payload["count"] > payload["returned"])


def test_declared_schemas_advertise_the_caps_the_handlers_enforce(server):
    """A client should learn the ceiling from the schema, not from an error."""
    schemas = {spec.name: spec.input_schema for spec in server.tools}
    assert schemas["price_history"]["properties"]["limit"]["maximum"] == MAX_PRICE_BARS
    assert schemas["top_movers"]["properties"]["top"]["maximum"] == MAX_TOP_MOVERS
    assert (
        schemas["search_documents"]["properties"]["limit"]["maximum"] == MAX_SEARCH_RESULTS
    )
    assert (
        schemas["quant_stats"]["properties"]["symbols"]["maxItems"] == MAX_QUANT_SYMBOLS
    )
    assert (
        schemas["latest_signals"]["properties"]["symbols"]["maxItems"]
        == MAX_SIGNAL_SYMBOLS
    )


def test_normal_offline_rashifal_persists_four_doses_and_predictions(
    server, storage, monkeypatch
):
    monkeypatch.setattr(
        server,
        "_advisor_evidence",
        lambda _online: (_ for _ in ()).throw(AssertionError("normal mode requested evidence")),
    )
    payload = _payload(
        _call(
            server,
            "rashifal",
            symbols=["NABIL"],
            mode="normal",
            online=False,
            horizon="year",
            equity=1_000_000,
        )
    )
    assert payload["mode"] == "normal"
    assert payload["online"] is False
    assert payload["horizon"] == "year"
    doses = payload["doses"]["doses"]
    assert [dose["horizon"] for dose in doses] == ["day", "week", "month", "year"]
    assert sum(dose["allocation_pct"] for dose in doses) <= 1.0
    assert all(dose["confidence"]["value"] <= 0.90 for dose in doses)
    # A dose only deploys buys, so a hold-only run assigns no cards to any dose.
    # Those cards are still forecasts, and one that was never journaled can never
    # be scored, so the run's own cards are journaled too — deduplicated against
    # whatever the doses already covered.
    expected_predictions = {
        (card["symbol"], dose["horizon_days"]) for dose in doses for card in dose["cards"]
    } | {(card["symbol"], card["horizon_days"]) for card in payload["cards"]}
    stored_predictions = {
        (str(row[0]), int(row[1]))
        for row in storage._conn.execute("SELECT symbol, horizon_days FROM predictions")
    }
    assert stored_predictions == expected_predictions
    assert storage._conn.execute("SELECT COUNT(*) FROM predictions").fetchone()[0] == len(
        expected_predictions
    )
    unlinked = storage._conn.execute(
        "SELECT COUNT(*) FROM advice_cards WHERE prediction_id IS NULL"
    ).fetchone()[0]
    assert unlinked == 0
    assert payload["run_id"] is not None


def test_doses_tool_returns_the_latest_persisted_run(server):
    _payload(
        _call(
            server,
            "rashifal",
            symbols=["NABIL"],
            mode="normal",
            online=False,
            equity=1_000_000,
        )
    )
    payload = _payload(_call(server, "doses"))
    assert len(payload["doses"]) == 4
    assert {dose["horizon"] for dose in payload["doses"]} == {
        "day",
        "week",
        "month",
        "year",
    }


def test_no_tool_can_mutate_market_data(server):
    """Guard the read-only contract against a future tool being added carelessly."""
    before = server.storage.db_stats()
    for tool in server.tools:
        assert not any(
            word in tool.name for word in ("ingest", "order", "buy", "sell", "apply", "delete")
        ), tool.name
    _call(server, "list_symbols")
    _call(server, "database_stats")
    after = server.storage.db_stats()
    for key in ("price_bar_rows", "reconciled_rows", "paper_trades"):
        assert before[key] == after[key]


def test_the_pipeline_has_no_source_clients(server):
    # The structural read-only guarantee: no client, no network, no ingest.
    assert server.pipeline.clients == []


# ------------------------------------------------------------ stdio loop


def _drive(tmp_path, storage, lines: list[dict]) -> tuple[list[dict], str]:
    """Run serve_stdio over StringIO. Returns (responses, raw stdout text)."""
    stdin = io.StringIO("".join(json.dumps(line) + "\n" for line in lines))
    stdout = io.StringIO()
    serve_stdio(
        settings=Settings(_env_file=None, db_path=tmp_path / "mcp.db"),
        storage=storage,
        stdin=stdin,
        stdout=stdout,
    )
    raw = stdout.getvalue()
    return [json.loads(line) for line in raw.splitlines() if line.strip()], raw


def test_end_to_end_initialize_list_and_call_over_the_stdio_loop(tmp_path, storage):
    responses, raw = _drive(
        tmp_path,
        storage,
        [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "list_symbols", "arguments": {}},
            },
        ],
    )

    # Four messages in, three out: the notification is answered with silence.
    assert [r["id"] for r in responses] == [1, 2, 3]
    assert responses[0]["result"]["serverInfo"]["name"] == SERVER_NAME
    assert responses[1]["result"]["tools"]
    body = json.loads(responses[2]["result"]["content"][0]["text"])
    assert body["symbols"] == sorted(SYMBOLS)

    # One frame per line, nothing else on the stream.
    assert raw.endswith("\n")
    assert len(raw.strip().splitlines()) == 3
    for line in raw.strip().splitlines():
        assert json.loads(line)["jsonrpc"] == "2.0"


def test_stdio_loop_survives_malformed_input_and_a_failing_tool(tmp_path, storage):
    stdin = io.StringIO(
        "{ this is not json\n"
        "\n"
        + json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "price_history", "arguments": {"symbol": "NOPE"}},
            }
        )
        + "\n"
        + json.dumps({"jsonrpc": "2.0", "id": 3, "method": "ping"})
        + "\n"
    )
    stdout = io.StringIO()
    serve_stdio(
        settings=Settings(_env_file=None, db_path=tmp_path / "mcp.db"),
        storage=storage,
        stdin=stdin,
        stdout=stdout,
    )
    responses = [json.loads(x) for x in stdout.getvalue().splitlines() if x.strip()]

    # Blank line produced nothing; the other three lines each produced one frame.
    assert len(responses) == 3
    assert responses[0]["error"]["code"] == -32700
    assert responses[1]["result"]["isError"] is True
    assert responses[2]["result"] == {}


def test_stdio_loop_returns_cleanly_on_eof(tmp_path, storage):
    responses, raw = _drive(tmp_path, storage, [])
    assert responses == []
    assert raw == ""


def test_serve_stdio_does_not_leak_the_real_stdout_rebinding(tmp_path, storage):
    """With explicit streams the loop must leave sys.stdout untouched."""
    original = sys.stdout
    _drive(tmp_path, storage, [{"jsonrpc": "2.0", "id": 1, "method": "ping"}])
    assert sys.stdout is original
