"""Tests for HAR analysis, config emission, and redaction."""

from __future__ import annotations

import base64
import json

from nepse_trader.har import analyzer


def _entry(
    url, method="GET", mime="application/json", text="", status=200, headers=None, encoding=None
):
    content = {"mimeType": mime, "text": text}
    if encoding:
        content["encoding"] = encoding
    return {
        "request": {
            "url": url,
            "method": method,
            "queryString": [],
            "headers": headers or [],
            "cookies": [],
        },
        "response": {"status": status, "content": content, "headers": [], "cookies": []},
    }


def _har(entries):
    return {"log": {"version": "1.2", "entries": entries}}


def test_json_api_outranks_assets():
    rows = json.dumps({"data": [{"symbol": "NABIL", "ltp": "500", "turnover": "1000"}]})
    har = _har(
        [
            _entry("https://www.sharesansar.com/top-gainers", text=rows),
            _entry(
                "https://www.sharesansar.com/app.js", mime="application/javascript", text="var x=1"
            ),
            _entry("https://www.sharesansar.com/logo.png", mime="image/png", text=""),
        ]
    )
    cands = analyzer.analyze(har)
    assert cands
    top = cands[0]
    assert top.kind == "json_api"
    assert "symbol" in top.sample_keys
    # Asset endpoints should be filtered out entirely.
    assert all(not c.url.endswith((".js", ".png")) for c in cands)


def test_datatables_nested_content_keys():
    payload = json.dumps(
        {
            "floorsheets": {
                "content": [{"contractId": 1, "stockSymbol": "ADBL", "contractRate": 250}]
            }
        }
    )
    har = _har([_entry("https://x/floorsheet", text=payload)])
    cands = analyzer.analyze(har)
    assert cands[0].sample_keys == ["contractId", "stockSymbol", "contractRate"]


def test_html_table_detected():
    html = "<html><body><table id='headFixed'><tr><th>Symbol</th></tr></table></body></html>"
    har = _har(
        [_entry("https://www.sharesansar.com/today-share-price", mime="text/html", text=html)]
    )
    cands = analyzer.analyze(har)
    assert cands[0].kind == "html_table"
    assert "table#headFixed" in cands[0].sample_keys


def test_base64_content_decoded():
    rows = json.dumps({"data": [{"symbol": "NABIL", "close": 1}]})
    b64 = base64.b64encode(rows.encode()).decode()
    e = _entry("https://x/today-price", text=b64, encoding="base64")
    assert "NABIL" in analyzer.decode_content(e)


def test_to_config_snippet_emits_yaml_keys():
    rows = json.dumps({"data": [{"symbol": "NABIL", "ltp": "500"}]})
    har = _har([_entry("https://www.sharesansar.com/top-gainers?draw=1", text=rows)])
    snippet = analyzer.to_config_snippet(har, "sharesansar")
    assert "sharesansar:" in snippet
    assert "endpoints:" in snippet
    assert "method: GET" in snippet
    assert "confidence: medium" in snippet


def test_redact_strips_cookies_and_auth():
    har = _har(
        [
            _entry(
                "https://x/api",
                headers=[
                    {"name": "Authorization", "value": "Salter secret"},
                    {"name": "Accept", "value": "application/json"},
                ],
            )
        ]
    )
    har["log"]["entries"][0]["request"]["cookies"] = [{"name": "sid", "value": "abc"}]
    red = analyzer.redact(har)
    req = red["log"]["entries"][0]["request"]
    assert req["cookies"] == []
    names = [h["name"].lower() for h in req["headers"]]
    assert "authorization" not in names
    assert "accept" in names
    # Original must be untouched (deep copy).
    assert har["log"]["entries"][0]["request"]["cookies"] != []


def test_redact_strips_post_bodies_query_params_and_auth_responses():
    secret = "SALTER-TOP-SECRET-TOKEN-12345"
    har = _har(
        [
            # POST whose body carries a token.
            {
                "request": {
                    "url": f"https://www.nepalstock.com/api/nots/today-price?accessToken={secret}&size=500",
                    "method": "POST",
                    "queryString": [
                        {"name": "accessToken", "value": secret},
                        {"name": "size", "value": "500"},
                    ],
                    "headers": [],
                    "cookies": [],
                    "postData": {
                        "mimeType": "application/json",
                        "text": '{"id": 42, "token": "' + secret + '"}',
                    },
                },
                "response": {
                    "status": 200,
                    "content": {"mimeType": "application/json", "text": '{"content": []}'},
                    "headers": [],
                    "cookies": [],
                },
            },
            # Auth endpoint whose RESPONSE body carries tokens.
            _entry(
                "https://www.nepalstock.com/api/authenticate/prove",
                text=json.dumps({"accessToken": secret, "salt1": 1}),
            ),
        ]
    )
    red = analyzer.redact(har)
    dumped = json.dumps(red)
    assert secret not in dumped
    # Non-sensitive query params survive; market-data response bodies survive.
    req0 = red["log"]["entries"][0]["request"]
    assert "size=500" in req0["url"]
    assert red["log"]["entries"][0]["response"]["content"]["text"] == '{"content": []}'
    # Auth response body blanked.
    assert red["log"]["entries"][1]["response"]["content"]["text"] == "REDACTED"
    # Original untouched.
    assert secret in json.dumps(har)
