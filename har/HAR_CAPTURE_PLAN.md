# HAR Capture Plan — NEPSE data sources

A **HAR** (HTTP Archive) file is a JSON log of every request your browser made on
a page, including URLs, methods, headers, query params, request bodies, and
response bodies. We use HAR files to **discover and verify** the real data
endpoints each Nepali market site uses, then turn those into entries in
`config/sources.yaml` via the analyzer:

```bash
nepse-trader har analyze har/captures/sharesansar.har
nepse-trader har to-config har/captures/sharesansar.har --source sharesansar
```

> Scope & ethics: we capture **your own browser's traffic** on **publicly
> available** pages, to read public market data politely. We do **not** capture
> or replay anyone else's session, and we do **not** use HAR to defeat auth,
> CAPTCHAs, WAFs, or rate limits. For NEPSE's official obfuscated token, prefer
> the `nepse-scraper` library; only replay a HAR you captured from your own
> session, and never share a HAR (they can contain cookies/tokens).

---

## How to capture a HAR (Chrome / Firefox / Edge)

1. Open the site in a normal browser tab (logged out — we only want public data).
2. Open DevTools → **Network** tab. Tick **Preserve log** and **Disable cache**.
3. Set the request-type filter to **Fetch/XHR** first (to spot JSON APIs), then
   also review **Doc** (for server-rendered HTML pages).
4. Perform the exact actions whose data you want (see per-site recipes below).
5. Right-click anywhere in the request list → **Save all as HAR with content**
   (Firefox: the gear/⚙ → "Save All As HAR"). Save into `har/captures/`.
6. Name it `<source>.har` (e.g. `sharesansar.har`, `chukul.har`).

**Redaction:** before committing or sharing, strip cookies/auth:
```bash
nepse-trader har redact har/captures/chukul.har    # writes *.redacted.har
```
`har/captures/*.har` is git-ignored by default; keep it that way.

---

## Per-site capture recipes

### 1. ShareSansar — `sharesansar.har` (PRIMARY)
Goal: confirm the EOD price page + the DataTables JSON feeds.
- Visit `https://www.sharesansar.com/today-share-price` → change the date picker
  to a recent **trading day** (Sunday–Thursday) → let the table load. (This is a
  server-rendered HTML doc, not XHR — capture it from the **Doc** filter.)
- Visit `https://www.sharesansar.com/floorsheet`, page through it once → you'll
  see an **XHR** to `/floorsheet` returning JSON (`draw`, `data`, `recordsTotal`).
- Visit `https://www.sharesansar.com/top-gainers` and `/top-losers` → XHR JSON.
- Visit `https://www.sharesansar.com/indices-sub-indices`, pick a sector + date
  range → XHR to `/indices-sub-indices` with `index_id`, `from`, `to`.
- Visit a company page, e.g. `https://www.sharesansar.com/company/nabil`, open
  the **Price History** tab → XHR **POST** `/company-price-history` carrying an
  `X-CSRF-Token` header and `company=<numeric id>` form field. Note both.

What to extract: the JSON `data` row shape for each feed, and the CSRF token flow
(the `<meta name="_token">` on the company page → `X-CSRF-Token` header).

### 2. Chukul — `chukul.har` (verify inferred /v1/ paths)
Goal: confirm the real `api.chukul.com/v1/...` paths (currently low-confidence).
- Visit `https://chukul.com/nepse-live-market`. Watch **Fetch/XHR** for calls to
  `api.chukul.com/v1/...`. Record the exact path, query params, and JSON shape
  for: live market, stock list, indices, fundamentals.
- Visit a stock profile page (e.g. a chart) to capture the OHLC/history endpoint.

What to extract: exact `/v1/...` paths + response keys → update `chukul` in
`config/sources.yaml` and flip `enabled: true` once verified.

### 3. MeroLagani — `merolagani.har` (secondary HTML)
Goal: confirm the StockQuote / LatestMarket / Indices HTML tables and the
`AutoSuggestHandler.ashx` autocomplete handler.
- Visit `StockQuote.aspx`, `LatestMarket.aspx`, `Indices.aspx` (Doc filter).
- Type in the search box on any page to trigger
  `handlers/AutoSuggestHandler.ashx?type=Company&q=...` (XHR).

What to extract: table structure for the HTML parser; the `__VIEWSTATE` /
`__EVENTVALIDATION` hidden fields if you need paginated postbacks.

### 4. NepseAlpha — `nepsealpha.har` (TradingView UDF, Cloudflare-gated)
Goal: capture the UDF datafeed *from your own browser session* (it requires a
`laravel_session` cookie and sits behind Cloudflare).
- Visit `https://www.nepsealpha.com/trading/chart` (or any chart), let a symbol
  load → XHR to `/trading/{0|1}/symbols?symbol=...` then `/trading/{0|1}/history?
  symbol=...&resolution=1D&from=<epoch>&to=<epoch>`.

What to extract: the `history` response (`t`,`o`,`h`,`l`,`c`,`v` arrays) and the
cookie flow. Use the HAR-replay client only with your **own** captured session,
sparingly (it rate-limits hard).

### 5. NEPSE official — `nepse_official.har` (reference / replay only)
Goal: understand the `/api/nots/...` calls and the `Authorization: Salter` flow.
- Visit `https://www.nepalstock.com`, open "Today's Price" / "Floorsheet".
- Observe `GET /api/authenticate/prove`, then data calls carrying
  `Authorization: Salter <token>` and (for POSTs) a numeric `id` body.

We do **not** reconstruct the token. Use this HAR for documentation, and prefer
the `nepse-scraper` library for actual NEPSE-official ingestion.

---

## What the analyzer produces

`nepse-trader har analyze <file>` prints a ranked table of candidate data
endpoints found in the HAR:

| column | meaning |
|--------|---------|
| method/url | the request |
| kind | `json_api`, `html_table`, or `other` |
| score | heuristic: JSON array/`data` payloads + market keywords rank higher |
| sample_keys | top-level keys (JSON) or `table#id` hints (HTML) |

`nepse-trader har to-config <file> --source <name>` emits a `sources.yaml`
snippet you can paste in, with `confidence: medium` (promote to `high` once you
re-verify against a live pull). `nepse-trader har redact <file>` strips cookies,
`Authorization`, and `set-cookie` so a HAR is safe to keep in the repo.
