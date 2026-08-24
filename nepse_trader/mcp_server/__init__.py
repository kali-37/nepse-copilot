"""MCP (Model Context Protocol) server exposing the local NEPSE database.

Runs over stdio as a hand-rolled JSON-RPC 2.0 server — standard library only, no
``mcp`` package. This package is named ``mcp_server`` rather than ``mcp``
precisely so it cannot shadow that pip package if anything else in the
environment wants it.

Two modules:

* :mod:`nepse_trader.mcp_server.protocol` — JSON-RPC framing and dispatch, with
  no notion of a transport, so the protocol surface unit-tests as dicts in /
  dicts out.
* :mod:`nepse_trader.mcp_server.server` — the tool registry and the stdio loop.

Every tool is **read-only**. Nothing here places an order, applies for an IPO,
writes a paper trade or mutates market data; an MCP client is an LLM choosing
tools from descriptions, and the blast radius of a hallucinated call must be zero.

Entry point::

    from nepse_trader.mcp_server.server import serve_stdio
    serve_stdio()

Nothing is re-exported at package level on purpose: ``python -m
nepse_trader.mcp_server.server`` would otherwise import ``server`` twice (once
via this ``__init__``, once as ``__main__``) and emit a runpy ``RuntimeWarning``
on stderr at every client launch.
"""
