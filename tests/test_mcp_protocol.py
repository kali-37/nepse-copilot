"""Protocol-layer tests: dicts in, dicts out, no subprocess and no database.

The whole point of keeping :mod:`nepse_trader.mcp_server.protocol` transport-free
is that these tests can assert on exact wire shapes. Two behaviours here are the
ones that break real MCP clients and so get the most coverage: notifications must
produce no response at all, and a malformed line must produce a well-formed error
instead of an exception escaping into the read loop.
"""

from __future__ import annotations

import json

import pytest

from nepse_trader.mcp_server.protocol import (
    INTERNAL_ERROR,
    INVALID_PARAMS,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    PARSE_ERROR,
    Dispatcher,
    Request,
    RpcError,
    error_response,
    parse_message,
    success_response,
)


def _line(**payload) -> str:
    return json.dumps(payload)


@pytest.fixture
def dispatcher() -> Dispatcher:
    d = Dispatcher()
    d.register("echo", lambda params: {"got": params})
    d.register("boom", _raise_runtime)
    d.register("bad_params", _raise_rpc_invalid_params)
    d.register("notifications/initialized", lambda params: None)
    return d


def _raise_runtime(params: dict) -> None:
    raise RuntimeError("handler exploded")


def _raise_rpc_invalid_params(params: dict) -> None:
    raise RpcError(INVALID_PARAMS, "Invalid params: nope")


# --------------------------------------------------------------- parse_message


def test_parse_message_reads_method_params_and_id():
    req = parse_message(_line(jsonrpc="2.0", id=7, method="tools/call", params={"name": "x"}))
    assert req.method == "tools/call"
    assert req.id == 7
    assert req.params == {"name": "x"}
    assert req.is_notification is False


def test_parse_message_missing_id_is_a_notification():
    req = parse_message(_line(jsonrpc="2.0", method="notifications/initialized"))
    assert req.is_notification is True
    assert req.id is None


def test_parse_message_explicit_null_id_is_not_a_notification():
    # Presence of the key decides, not truthiness: JSON-RPC allows a null id and
    # a truthiness check would also misread id 0.
    req = parse_message('{"jsonrpc":"2.0","id":null,"method":"ping"}')
    assert req.is_notification is False


def test_parse_message_zero_id_is_not_a_notification():
    req = parse_message('{"jsonrpc":"2.0","id":0,"method":"ping"}')
    assert req.is_notification is False
    assert req.id == 0


def test_parse_message_defaults_missing_params_to_empty_dict():
    assert parse_message(_line(jsonrpc="2.0", id=1, method="ping")).params == {}


def test_parse_message_rejects_invalid_json():
    with pytest.raises(RpcError) as exc:
        parse_message("{not json")
    assert exc.value.code == PARSE_ERROR


def test_parse_message_rejects_non_object_payload():
    with pytest.raises(RpcError) as exc:
        parse_message('[{"jsonrpc":"2.0","id":1,"method":"ping"}]')
    assert exc.value.code == INVALID_REQUEST


def test_parse_message_rejects_missing_method():
    with pytest.raises(RpcError) as exc:
        parse_message(_line(jsonrpc="2.0", id=1))
    assert exc.value.code == INVALID_REQUEST


def test_parse_message_rejects_non_object_params():
    with pytest.raises(RpcError) as exc:
        parse_message(_line(jsonrpc="2.0", id=1, method="ping", params=[1, 2]))
    assert exc.value.code == INVALID_PARAMS


# ------------------------------------------------------------ response helpers


def test_success_response_shape():
    assert success_response(3, {"a": 1}) == {"jsonrpc": "2.0", "id": 3, "result": {"a": 1}}


def test_error_response_omits_data_when_absent():
    resp = error_response(3, METHOD_NOT_FOUND, "nope")
    assert resp == {"jsonrpc": "2.0", "id": 3, "error": {"code": METHOD_NOT_FOUND, "message": "nope"}}
    assert "data" not in resp["error"]


def test_error_response_includes_data_when_present():
    resp = error_response(3, INTERNAL_ERROR, "bad", data={"why": "x"})
    assert resp["error"]["data"] == {"why": "x"}


# ------------------------------------------------------------------- dispatch


def test_dispatch_returns_handler_result(dispatcher):
    resp = dispatcher.handle_line(_line(jsonrpc="2.0", id=1, method="echo", params={"k": "v"}))
    assert resp == {"jsonrpc": "2.0", "id": 1, "result": {"got": {"k": "v"}}}


def test_notification_produces_no_response(dispatcher):
    assert dispatcher.handle_line(_line(jsonrpc="2.0", method="notifications/initialized")) is None


def test_notification_to_a_raising_handler_still_produces_no_response(dispatcher):
    assert dispatcher.handle_line(_line(jsonrpc="2.0", method="boom")) is None


def test_unknown_notification_is_silently_ignored(dispatcher):
    assert dispatcher.handle_line(_line(jsonrpc="2.0", method="notifications/nope")) is None


def test_unknown_method_returns_method_not_found(dispatcher):
    resp = dispatcher.handle_line(_line(jsonrpc="2.0", id=9, method="no_such_method"))
    assert resp["id"] == 9
    assert resp["error"]["code"] == METHOD_NOT_FOUND
    assert "no_such_method" in resp["error"]["message"]


def test_malformed_json_returns_parse_error_with_null_id(dispatcher):
    resp = dispatcher.handle_line("{broken")
    assert resp["id"] is None
    assert resp["error"]["code"] == PARSE_ERROR


def test_blank_line_produces_no_response(dispatcher):
    assert dispatcher.handle_line("   \n") is None
    assert dispatcher.handle_line("") is None


def test_rpc_error_from_handler_maps_to_its_own_code(dispatcher):
    resp = dispatcher.handle_line(_line(jsonrpc="2.0", id=4, method="bad_params"))
    assert resp["error"]["code"] == INVALID_PARAMS


def test_unexpected_handler_exception_maps_to_internal_error(dispatcher):
    resp = dispatcher.handle_line(_line(jsonrpc="2.0", id=5, method="boom"))
    assert resp["error"]["code"] == INTERNAL_ERROR
    assert "handler exploded" in resp["error"]["message"]


def test_dispatcher_survives_a_failing_call_and_serves_the_next(dispatcher):
    dispatcher.handle_line(_line(jsonrpc="2.0", id=1, method="boom"))
    resp = dispatcher.handle_line(_line(jsonrpc="2.0", id=2, method="echo", params={}))
    assert resp["result"] == {"got": {}}


def test_methods_lists_registered_names(dispatcher):
    assert dispatcher.methods() == sorted(
        ["echo", "boom", "bad_params", "notifications/initialized"]
    )


def test_handle_request_accepts_a_prebuilt_request(dispatcher):
    resp = dispatcher.handle_request(Request(method="echo", params={"a": 1}, id=2))
    assert resp["result"] == {"got": {"a": 1}}


def test_every_response_is_json_serialisable(dispatcher):
    for line in ("{broken", _line(jsonrpc="2.0", id=1, method="boom")):
        resp = dispatcher.handle_line(line)
        json.dumps(resp)  # must not raise
