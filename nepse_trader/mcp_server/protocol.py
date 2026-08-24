"""JSON-RPC 2.0 framing and dispatch for the MCP server — transport-agnostic.

This module knows nothing about stdio, sockets or NEPSE. It turns a *line of
text* into a *response dict (or ``None``)*, which is the whole reason it exists:
the MCP protocol surface can then be unit-tested by feeding it dicts, with no
subprocess, no pipes and no timing.

Three rules are encoded here because getting any of them wrong breaks real
clients in ways that are hard to debug from the other side of a pipe:

**A message without ``id`` is a notification and gets no response — ever.**
Not even an error. ``notifications/initialized`` is the one every client sends
immediately after ``initialize``; replying to it makes a strict client hang
waiting for a response it will match to nothing, or drop the connection.

**A tool that raises is not a JSON-RPC error.** Protocol errors (bad JSON,
unknown method, malformed params) use the ``error`` member. A tool that blew up
still *succeeded as a call* — the result carries ``isError: true`` and the
message as a text block, so the model can read the failure and try something
else. Handled at the :mod:`~nepse_trader.mcp_server.server` layer; this module
just guarantees a handler exception never escapes as a crash.

**Dispatch never raises.** :meth:`Dispatcher.handle_line` converts every failure
mode into a well-formed response, because the caller is a ``while True`` loop
reading a pipe and one uncaught exception ends the session.

Only the standard library is used. The MCP spec is a JSON-RPC dialect, not a
package dependency, and hand-rolling ~200 lines here keeps the project's
dependency set unchanged.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

# JSON-RPC 2.0 reserved error codes. Anything application-level belongs in a
# tool result with isError, not here.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

JSONRPC_VERSION = "2.0"

# Handler contract: params dict in, JSON-serialisable result out.
MethodHandler = Callable[[dict[str, Any]], Any]


class RpcError(Exception):
    """A protocol-level failure that must surface as a JSON-RPC ``error``.

    Method handlers raise this for "you asked wrongly" (missing argument,
    unknown tool name). Any *other* exception from a handler becomes an
    ``INTERNAL_ERROR``, since an unexpected traceback is not something a client
    can act on.
    """

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


@dataclass
class Request:
    """A parsed, structurally valid JSON-RPC request or notification."""

    method: str
    params: dict[str, Any]
    id: Any = None
    is_notification: bool = False


def parse_message(raw: str) -> Request:
    """Parse one line of JSON into a :class:`Request`.

    Raises :class:`RpcError` with ``PARSE_ERROR`` for invalid JSON and
    ``INVALID_REQUEST`` for JSON that is not a shaped JSON-RPC request. Both are
    reported with ``id: null``, per the spec — we cannot know the id of a message
    we could not read.
    """
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        raise RpcError(PARSE_ERROR, f"Parse error: {exc}") from exc

    if not isinstance(payload, dict):
        # Batch requests (a JSON array) are legal JSON-RPC but not used by MCP;
        # rejecting them is better than half-supporting them.
        raise RpcError(INVALID_REQUEST, "Invalid Request: expected a JSON object")

    method = payload.get("method")
    if not isinstance(method, str) or not method:
        raise RpcError(INVALID_REQUEST, "Invalid Request: missing 'method'")

    params = payload.get("params")
    if params is None:
        params = {}
    elif not isinstance(params, dict):
        raise RpcError(INVALID_PARAMS, "Invalid params: expected an object")

    # Presence of the key, not truthiness: id 0 and id "" are valid ids, and a
    # `.get()` truthiness check would misread them as notifications.
    has_id = "id" in payload
    return Request(
        method=method,
        params=params,
        id=payload.get("id"),
        is_notification=not has_id,
    )


def success_response(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result}


def error_response(request_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "error": error}


class Dispatcher:
    """Routes JSON-RPC methods to registered handlers.

    Deliberately a plain name → callable mapping rather than an if/elif chain in
    a ``handle`` method: the MCP method set is small but the server also wants to
    enumerate it (for tests, and for a future ``capabilities`` response), which a
    chain cannot do.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, MethodHandler] = {}

    def register(self, method: str, handler: MethodHandler) -> None:
        self._handlers[method] = handler

    def methods(self) -> list[str]:
        return sorted(self._handlers)

    def handle_request(self, request: Request) -> dict[str, Any] | None:
        """Dispatch a parsed request. Returns ``None`` for notifications."""
        handler = self._handlers.get(request.method)

        if handler is None:
            if request.is_notification:
                # An unknown notification is ignored, not errored: the spec lets
                # a client send notifications we have not implemented, and
                # answering one would put an unmatched id on the wire.
                return None
            return error_response(
                request.id, METHOD_NOT_FOUND, f"Method not found: {request.method}"
            )

        try:
            result = handler(request.params)
        except RpcError as exc:
            if request.is_notification:
                return None
            return error_response(request.id, exc.code, exc.message, exc.data)
        except Exception as exc:
            if request.is_notification:
                return None
            return error_response(
                request.id, INTERNAL_ERROR, f"Internal error: {type(exc).__name__}: {exc}"
            )

        if request.is_notification:
            return None
        return success_response(request.id, result)

    def handle_line(self, raw: str) -> dict[str, Any] | None:
        """Parse and dispatch one wire line. Never raises.

        Returns the response dict to write back, or ``None`` when nothing should
        be written (a notification, or a blank line).
        """
        if not raw.strip():
            return None
        try:
            request = parse_message(raw)
        except RpcError as exc:
            # No usable id exists for an unparseable message, so id is null.
            return error_response(None, exc.code, exc.message, exc.data)
        return self.handle_request(request)
