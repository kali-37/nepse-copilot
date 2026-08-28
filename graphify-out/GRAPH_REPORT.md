# Graph Report - nepse-trader  (2026-08-28)

## Corpus Check
- 221 files · ~290,816 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 4854 nodes · 12359 edges · 192 communities (163 shown, 29 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 1142 edges (avg confidence: 0.51)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `07cbd771`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Settings
- LLMRouter
- meroshare/__init__.py
- indicator_document
- reporting.py
- Storage
- test_ai_analyst.py
- Document
- base.py
- test_nepse_official.py
- advisor/__init__.py
- build_evidence
- ResponseCache
- parse_into
- SourceName
- test_strategies.py
- MeroShareHolding
- test_mcp_server.py
- ._search_fts
- jobs.py
- quant.py
- doses.py
- journal.py
- indicators.py
- outcomes.py
- Backtester
- ChukulClient
- BaseClient
- Confidence
- MeroShareClient
- JobRegistry
- build_plan_card
- Plan: NEPSE Trader — Full Completion
- NepseAlphaClient
- migrations.py
- MeroLaganiClient
- SourceSpec
- server.py
- test_logging_setup.py
- analyzer.py
- Analyst
- add_trading_days
- save_rashifal
- DailyPipeline
- _build_advisor_result
- LLMResponse
- TestAdvisor
- types.ts
- screen
- get
- test_properties.py
- auction.py
- test_mcp_protocol.py
- test_meroshare.py
- MeroShareCredentials
- CorporateAction
- Plan: Web UI Dashboard
- test_web_operations.py
- App.tsx
- FakeAnalyst
- plan.py
- Developers Guide — NEPSE Trader
- .parse_announcements
- _run
- _settings
- main.py
- PriceBar
- fixtures.ts
- ReconciledPrice
- test_pipeline.py
- rashifal_md
- Make It Even Better — Engineering Quality Upgrades
- SmaCrossStrategy
- validate_yaml
- field_validator
- htmlparse.py
- compilerOptions
- system_health
- test_rag_corpus.py
- AccountVault
- TestHtmlToText
- compilerOptions
- Tier 2 — strong analytical upside
- api.py
- Dispatcher
- corpus.py
- _settings
- Operations.tsx
- renderWithProviders.tsx
- How It Works — NEPSE Trader Internals
- devDependencies
- test_backtest_risk.py
- SellCandidate
- Any
- walkforward.py
- test_reporting.py
- MeroLaganiFundamentalsClient
- TestCitations
- _advisor_run_response
- conftest.py
- post
- _ensure_app_settings
- progress_spinner
- NEPSE Trader — Agent Context
- test_ingest_news.py
- check_freshness
- NewsClient
- .parse_news_list
- read_bool
- dependencies
- TestRagSearch
- NEPSE Trader — Operations Runbook
- How To Use — NEPSE Trader
- TestJobRoutes
- demat_fingerprint
- test_sharesansar.py
- test_cli_advisor.py
- Auction.tsx
- Rashifal.tsx
- 22. Recipes
- TestDegradation
- Capabilities — NEPSE Trader
- health.py
- NEPSE Trader
- test_cli.py
- NEPSE Trader — project skill
- _decide
- meroshare_status
- _client
- Alerter
- Per-site capture recipes
- Job
- plugins
- pipeline.py
- TestExtractResultLinks
- scripts
- NEPSE risk & position sizing — project skill
- MeroSharePortfolio
- test_health.py
- test_advisor_rashifal.py
- news.py
- NEPSE backtest protocol — project skill
- check_meroshare
- 23. All the settings
- package.json
- test_golden_fixtures.py
- check_ai
- React + TypeScript + Vite
- Health.tsx
- tsconfig.json
- msw
- analysis/__init__.py
- cli/__init__.py
- har/__init__.py
- nepse_trader/__init__.py
- mcp_server/__init__.py
- trading/__init__.py
- _Base
- @tailwindcss/vite
- @types/react
- @types/react-dom
- typescript
- vite
- @vitejs/plugin-react
- vitest
- nepse-trader
- TestRegime
- 3. Robustness & resilience
- TestBulkAnalytics
- TestPaperTrades
- ._split_csv
- TestAiRoutes
- TestCorporateActions
- check_ingest
- check_schema
- DegradingAnalyst
- plan_cards_md
- card
- serve_stdio
- TestHostileAnalyst
- JobCancelled
- @types/node
- mock
- do_not_touch_md
- sell_queue_md
- TestMeroShareImport
- CostEngine
- TokenBudget

## God Nodes (most connected - your core abstractions)
1. `Settings` - 248 edges
2. `Document` - 138 edges
3. `Storage` - 136 edges
4. `DocumentIndex` - 135 edges
5. `PriceBar` - 133 edges
6. `LLMResponse` - 124 edges
7. `CostEngine` - 120 edges
8. `DailyPipeline` - 94 edges
9. `BaseClient` - 85 edges
10. `TokenBudget` - 75 edges

## Surprising Connections (you probably didn't know these)
- `TestAiRoutes` --uses--> `JobBusy`  [INFERRED]
  tests/test_web_operations.py → nepse_trader/web/jobs.py
- `TestBulkAnalytics` --uses--> `JobBusy`  [INFERRED]
  tests/test_web_operations.py → nepse_trader/web/jobs.py
- `TestCorporateActions` --uses--> `JobBusy`  [INFERRED]
  tests/test_web_operations.py → nepse_trader/web/jobs.py
- `TestInventoryRoutes` --uses--> `JobBusy`  [INFERRED]
  tests/test_web_operations.py → nepse_trader/web/jobs.py
- `TestJobRegistry` --uses--> `JobBusy`  [INFERRED]
  tests/test_web_operations.py → nepse_trader/web/jobs.py

## Import Cycles
- None detected.

## Communities (192 total, 29 thin omitted)

### Community 0 - "Settings"
Cohesion: 0.05
Nodes (45): BaseSettings, Connection, AnthropicProvider, build_provider(), ClaudeCliProvider, estimate_tokens(), NullProvider, _openrouter_text() (+37 more)

### Community 1 - "LLMRouter"
Cohesion: 0.05
Nodes (47): Connection, LLMProvider, True when the provider is configured well enough to try. Checked without any…, Anything that can turn a prompt into text., The model this provider would use right now, for the ledger., LLMRouter, Connection, Best available answer to *prompt*, or a response explaining the gap. ``task``… (+39 more)

### Community 2 - "meroshare/__init__.py"
Cohesion: 0.06
Nodes (46): Dialect, MeroShare credential resolution — and every path a secret could escape by. The…, :func:`redact`, plus every account identifier on this instance., Return ``text`` as a string with every non-empty secret masked. Used on every…, redact(), import_portfolio(), ImportError_, _match_column() (+38 more)

### Community 3 - "indicator_document"
Cohesion: 0.18
Nodes (10): build_symbol_documents(), indicator_document(), Latest reading of every indicator, with its interpretation stated., Every document derivable for one symbol from its bar history. Only the most…, A bare number is useless in a report; the reading must be explained., Daily re-indexing must upsert, not accumulate., A rising series long enough for SMA50/RSI/MACD/Bollinger to have values., _series() (+2 more)

### Community 4 - "reporting.py"
Cohesion: 0.11
Nodes (26): _fmt_num(), leaderboard_md(), market_overview_md(), _md_escape(), movers_md(), portfolio_summary(), price_bars_markdown(), print_signals() (+18 more)

### Community 5 - "Storage"
Cohesion: 0.05
Nodes (42): export_csv(), export_parquet(), Path, _d(), _dt(), Connection, date, datetime (+34 more)

### Community 6 - "test_ai_analyst.py"
Cohesion: 0.09
Nodes (20): Critique, A devil's-advocate pass over the deterministic plan. It cannot change a number…, _analyst(), _FakeRouter, date, Tests for the analyst and the schemas that guard its output. Two contracts are…, Only the surface ``Analyst`` actually touches: ``complete`` and…, One pass per symbol times twenty-five symbols — free models, not synthesis. (+12 more)

### Community 7 - "Document"
Cohesion: 0.05
Nodes (32): FixtureRequest, Document, One retrievable fact or article., Positional tuple matching the ``documents`` table column order., DocumentIndex, Connection, The searchable document index: SQLite FTS5, with a LIKE fallback.…, Remove every document of one kind (used when rebuilding a slice). (+24 more)

### Community 8 - "base.py"
Cohesion: 0.06
Nodes (46): FetchError, FetchResult, _HostThrottle, Any, Client, Exception, RateLimitedError, Polite HTTP base client shared by all ingestion sources. Design goals: *… (+38 more)

### Community 9 - "test_nepse_official.py"
Cohesion: 0.07
Nodes (53): decode_content(), _extract_records(), find_entries(), _first(), HarReplayClient, is_available(), load_har(), _looks_sharesansar() (+45 more)

### Community 10 - "advisor/__init__.py"
Cohesion: 0.10
Nodes (24): Persist one dose run and exactly four child rows atomically., save_doses(), Public advisor API: deterministic plans, confidence, doses and review., build_plan_cards(), date, Build cards for *symbols*, returning the cards and the skips separately.…, A symbol that could not be given an honest card, and why. Surfaced rather than…, Skipped (+16 more)

### Community 11 - "build_evidence"
Cohesion: 0.07
Nodes (35): _as_scored(), build_evidence(), EvidenceItem, EvidencePack, Turning retrieved documents into a bounded, citable evidence block. An…, A compact source list for the human-facing report., Pack hits into an :class:`EvidencePack` under both ceilings. ``max_documents``…, Normalise either input shape to (document, score) pairs. (+27 more)

### Community 12 - "ResponseCache"
Cohesion: 0.07
Nodes (27): cache_key(), Delete entries past the TTL. Returns how many went., Size and age of the cache, for ``ai budget``., Stable key for a request's content. The parts are joined with a separator that…, SQLite-backed cache over the ``ai_cache`` table., A fresh cached response, or None on a miss or an expired entry., Store a successful response. Returns whether it was written. Failures are never…, ResponseCache (+19 more)

### Community 13 - "parse_into"
Cohesion: 0.07
Nodes (22): parse_into(), T, Parse *text* into *model*, or return None and log why. ``defaults`` fill fields…, _critique_json(), _note_json(), parametrize, The contract: a failed pass costs narrative, never an exception., Some models wrap the single answer in a list. (+14 more)

### Community 14 - "SourceName"
Cohesion: 0.17
Nodes (17): _consensus(), ReconciledPrice, Cross-source reconciliation. The whole point of pulling the same NEPSE data…, Return (agreed_value, agreeing_sources, disputed). Greedy clustering: for each…, reconcile_bars(), _within(), CorporateActionType, Enum (+9 more)

### Community 15 - "test_strategies.py"
Cohesion: 0.06
Nodes (54): Backtest screening: rank strategies across symbols. Runs a panel of strategies…, _strategies(), BollingerStrategy, build_strategy(), _clean_indicators(), CompositeStrategy, DonchianStrategy, IchimokuStrategy (+46 more)

### Community 16 - "MeroShareHolding"
Cohesion: 0.06
Nodes (23): MeroShareHolding, field_validator, One scrip balance in the user's demat account, as MeroShare reports it., Total invested in this scrip per the portal's WACC., _bars(), client(), empty_client(), _make_client() (+15 more)

### Community 17 - "test_mcp_server.py"
Cohesion: 0.08
Nodes (45): _call(), _payload(), parametrize, Server-layer tests: tool registry, tool call semantics, and the stdio loop.…, Invoke a tool through the dispatcher and return the raw MCP result., Parse the JSON a tool rendered into its single text content block., An oversized request must fail loudly; a truncated answer would read as…, Every unbounded list carries ``returned``/``truncated`` alongside ``count``. (+37 more)

### Community 18 - "._search_fts"
Cohesion: 0.14
Nodes (14): _matched(), date, Row, Best-matching documents for *query*, most relevant first.…, Term-overlap ranking. Correct, just less clever than bm25., Newest documents matching the filters, ignoring relevance., Extract searchable words (Latin + Devanagari) from a raw query., Turn free text into a safe FTS5 MATCH expression. Terms are OR-ed with a prefix… (+6 more)

### Community 19 - "jobs.py"
Cohesion: 0.15
Nodes (19): Any, DailyPipeline, _job_ingest(), _job_rag_index(), _job_reconcile(), _job_run_daily(), _job_screen(), JobContext (+11 more)

### Community 20 - "quant.py"
Cohesion: 0.08
Nodes (45): annualized_return(), annualized_volatility(), beta(), correlation(), covariance(), kurtosis(), max_drawdown(), mean() (+37 more)

### Community 21 - "doses.py"
Cohesion: 0.05
Nodes (66): penalise(), Scale a confidence down by *factor*, recording *reason*. Used for known…, _add_sell_guidance(), build_dose_run(), build_doses(), _card_horizon(), _card_value(), _confidence_for_card() (+58 more)

### Community 22 - "journal.py"
Cohesion: 0.11
Nodes (49): _as_date(), _confidence(), confidence_for_prediction(), distill_lesson(), _fetch(), get_prediction(), journal_history(), JournalError (+41 more)

### Community 23 - "indicators.py"
Cohesion: 0.07
Nodes (46): atr(), bollinger_bands(), chikou_span(), donchian_channel(), ema(), kijun_sen(), latest(), macd() (+38 more)

### Community 24 - "outcomes.py"
Cohesion: 0.10
Nodes (40): _date(), _is_short(), _number(), Outcome, OutcomeResult, persist_score(), _prediction_symbol(), Any (+32 more)

### Community 25 - "Backtester"
Cohesion: 0.10
Nodes (34): Backtester, BacktestResult, _max_drawdown(), date, Event-driven, long-only backtester over a single symbol's price bars., Replay ``bars`` for ``strategy`` and return a :class:`BacktestResult`. Bars are…, Apply slippage: buys fill higher, sells fill lower., Largest whole-share quantity affordable within the cash budget. Budget is… (+26 more)

### Community 26 - "ChukulClient"
Cohesion: 0.10
Nodes (29): _as_records(), ChukulClient, _int(), _num(), _pick(), Any, date, Chukul JSON source adapter. Chukul (https://chukul.com) is powered by a… (+21 more)

### Community 27 - "BaseClient"
Cohesion: 0.10
Nodes (28): BaseClient, Wraps httpx with throttling, retries, and optional raw-response caching., Retrieval-augmented generation over the local NEPSE database and the live web.…, build_retriever(), HybridRetriever, LocalRetriever, Retrievers: where evidence comes from. Three implementations behind one small…, Lazily built so constructing a WebRetriever opens no connection. (+20 more)

### Community 28 - "Confidence"
Cohesion: 0.10
Nodes (27): band_for(), blend(), certain(), Confidence, confidence_from_history(), ConfidenceError, market(), ValueError (+19 more)

### Community 29 - "MeroShareClient"
Cohesion: 0.07
Nodes (33): _as_date(), _as_float(), _as_int(), connect(), _first(), MeroShareAuthError, MeroShareClient, MeroShareFetchError (+25 more)

### Community 30 - "JobRegistry"
Cohesion: 0.13
Nodes (10): JobRegistry, In-memory job store that runs at most one job at a time., Drop all history. Used between tests so registries never leak state., Register throwaway job kinds, and remove them again afterwards. Editing the…, A worker must never share the request-path Storage., Entering a stage checks for cancellation, so later work never starts., A Saturday must not reach the network. Every stage is skipped., stub_handlers() (+2 more)

### Community 31 - "build_plan_card"
Cohesion: 0.05
Nodes (27): build_plan_card(), PlanCard, Confidence, Build one symbol's card, or explain why it can't be built. *today* defaults to…, One symbol's prescription. Every field here is engine-computed., _bars(), date, fixture (+19 more)

### Community 32 - "Plan: NEPSE Trader — Full Completion"
Cohesion: 0.05
Nodes (43): Overview, Plan: NEPSE Trader — Full Completion, Potential Risks & Gotchas (addressed), Prerequisites, Rollback Plan, Sprint 0: Engineering Foundation, Sprint 1: Tier 1 Features, Sprint 2: Analytical Upside (+35 more)

### Community 33 - "NepseAlphaClient"
Cohesion: 0.12
Nodes (12): NepseAlphaClient, Any, date, NepseAlpha ingestion client — TradingView UDF format. NepseAlpha…, Fetch daily price bars for *symbol* from the UDF history endpoint. The endpoint…, NepseAlpha is supplementary and doesn't support whole-market fetch. Returns an…, Client for NepseAlpha's TradingView UDF datafeed., Parse TradingView UDF history JSON into PriceBar records. Expected payload… (+4 more)

### Community 34 - "migrations.py"
Cohesion: 0.05
Nodes (42): Path, _applied_versions(), _create_version_table(), _m0000_initial(), _m0001_corporate_actions(), _m0002_adjusted_close(), _m0003_rag_documents(), _m0004_ai() (+34 more)

### Community 35 - "MeroLaganiClient"
Cohesion: 0.07
Nodes (45): BaseClient, HTMLParser, IndexValue, mock, _build_column_map(), _cell_at(), _cell_text(), _data_rows() (+37 more)

### Community 36 - "SourceSpec"
Cohesion: 0.13
Nodes (22): CommissionSlab, CostModel, load_cost_model(), load_sources(), BaseModel, Path, Nepal equity transaction cost + tax model. Values are tunable via YAML., _read_yaml() (+14 more)

### Community 37 - "server.py"
Cohesion: 0.10
Nodes (24): _hit_to_dict(), _holding_to_dict(), _json_text(), MCPServer, _normalise_symbols(), _optional_bool(), _optional_choice(), _optional_date() (+16 more)

### Community 38 - "test_logging_setup.py"
Cohesion: 0.09
Nodes (37): BaseException, callback, Context, FileHandler, Logger, _root(), get_logger(), _is_control_flow_exit() (+29 more)

### Community 39 - "analyzer.py"
Cohesion: 0.10
Nodes (39): har_analyze(), har_redact(), har_to_config(), Rank candidate data endpoints found in a HAR capture., Emit a sources.yaml snippet for the top endpoints in a HAR., Strip cookies/auth headers; write <name>.redacted.har next to the input., analyze(), _content_type() (+31 more)

### Community 40 - "Analyst"
Cohesion: 0.04
Nodes (41): Analyst, date, The analyst: evidence in, validated commentary out. One class tying the pieces…, One line naming why AI output is missing, or empty when it isn't. Reasons…, LLM commentary over deterministic output. Never a source of numbers., Narrative for one symbol. Bulk tier — this runs once per symbol., The expensive weekly pass. Synthesis tier, and the only ``deep`` call. Cached…, Devil's advocate against the deterministic plan. Synthesis tier. (+33 more)

### Community 41 - "add_trading_days"
Cohesion: 0.07
Nodes (25): add_trading_days(), _default_holidays(), _get_holidays(), is_trading_day(), load_holidays(), next_trading_day(), periods_per_year(), previous_trading_day() (+17 more)

### Community 42 - "save_rashifal"
Cohesion: 0.20
Nodes (8): latest_run(), Persist a run and its cards; returns the run id. Stored so a call can be scored…, The most recent run with its cards, or None if the advisor never ran., Recent runs, newest first, without their cards., run_history(), _run_row_to_dict(), save_rashifal(), TestPersistence

### Community 43 - "DailyPipeline"
Cohesion: 0.06
Nodes (33): DailyPipeline, Any, date, ReconciledPrice, Signal, Async variant: fetches from all sources concurrently., Call a client fetch method, isolating its failure to that data type., Reconciled history for a symbol as PriceBars (for indicators). (+25 more)

### Community 44 - "_build_advisor_result"
Cohesion: 0.12
Nodes (18): _advisor_evidence(), _advisor_mode(), _advisor_positions(), _build_advisor_result(), _journal_confidence(), _latest_strategy_panel(), meroshare_holdings_cmd(), _normalise_symbols() (+10 more)

### Community 45 - "LLMResponse"
Cohesion: 0.06
Nodes (23): _anthropic_text(), LLMResponse, Read ``--output-format json``, tolerating a plain-text CLI too., One-line, length-capped error text fit for a log or a ledger row., What a provider returned — or why it didn't., True when there is usable text and no error., _short(), _budget() (+15 more)

### Community 47 - "types.ts"
Cohesion: 0.08
Nodes (35): fetchJson(), postJson(), AiCacheStats, AiProviderLeg, BacktestRun, BacktestSummary, BulkSignalRow, Confidence (+27 more)

### Community 48 - "screen"
Cohesion: 0.23
Nodes (15): best_per_symbol(), Any, Collapse a leaderboard to the single best strategy per symbol., Backtest every (symbol, strategy) pair and return a ranked leaderboard.…, screen(), ScreenRow, _bars(), _hump() (+7 more)

### Community 49 - "get"
Cohesion: 0.11
Nodes (32): get, HTTPException, advisor_latest(), advisor_run(), backtest_run(), backtest_screen(), bulk_signals(), bulk_stats() (+24 more)

### Community 50 - "test_properties.py"
Cohesion: 0.08
Nodes (34): given, Property-based tests for core invariants using Hypothesis. Each test explores a…, effective_buy_cost_per_share = net_amount / quantity., SMA values lie within [min(values), max(values)] for the defined portion., EMA values lie within [min(values), max(values)]., SMA has None for the first (period-1) positions., RSI is always in [0, 100]., Bollinger: lower <= middle <= upper. (+26 more)

### Community 51 - "auction.py"
Cohesion: 0.10
Nodes (34): _advice_id(), advise_auction(), advise_from_plan(), _as_date(), auction_advice_history(), AuctionAdvice, _break_even_bid(), _break_even_exit_price() (+26 more)

### Community 52 - "test_mcp_protocol.py"
Cohesion: 0.11
Nodes (30): parse_message(), A parsed, structurally valid JSON-RPC request or notification., Parse one line of JSON into a :class:`Request`. Raises :class:`RpcError` with…, Request, dispatcher(), _line(), fixture, _raise_rpc_invalid_params() (+22 more)

### Community 53 - "test_meroshare.py"
Cohesion: 0.09
Nodes (31): MeroShareDisabledError, MeroShare integration is switched off in settings., MeroShareTransaction, One demat credit or debit. ``quantity`` is signed: debits are negative., Deterministic id — the portal exposes no stable row identifier. Hashing the…, compare_with_paper(), MeroShareHolding, Upsert holdings on (symbol, demat_hash). Returns rows written. (+23 more)

### Community 54 - "MeroShareCredentials"
Cohesion: 0.08
Nodes (18): meroshare_sync_cmd(), Read and mirror holdings only; no MeroShare-side action is available., connection_disclosure(), ensure_enabled(), Client, Return settings, or refuse cleanly when MeroShare is switched off. Refusing…, Exactly what will be sent where, for the CLI to show before connecting.…, MeroShareCredentials (+10 more)

### Community 55 - "CorporateAction"
Cohesion: 0.24
Nodes (19): adjust_prices(), Back-adjust reconciled closes by corporate action factors. For each symbol,…, CorporateAction, A corporate event that adjusts historical prices., _ca(), _price(), date, ReconciledPrice (+11 more)

### Community 56 - "Plan: Web UI Dashboard"
Cohesion: 0.06
Nodes (32): Overview, Plan: Web UI Dashboard, Potential Risks & Gotchas, Prerequisites, Rollback Plan, Sprint 1: Backend API, Sprint 2: Frontend Foundation, Sprint 3: Dashboard + Symbols Page (+24 more)

### Community 57 - "test_web_operations.py"
Cohesion: 0.12
Nodes (11): _bars(), client(), fixture, ReconciledPrice, The background job engine and the operations endpoints it drives. Two halves.…, A temp database with one symbol's history, plus matching Settings., A TestClient over the seeded database, with a clean job registry., _reconciled() (+3 more)

### Community 58 - "App.tsx"
Cohesion: 0.07
Nodes (51): react, AiBudget, AiModelsResponse, AiTestResult, BulkSignalsResponse, BulkStatsResponse, HoldingComparison, JournalEntry (+43 more)

### Community 59 - "FakeAnalyst"
Cohesion: 0.26
Nodes (6): FakeAnalyst, _note(), Returns valid notes and records every call, so we can assert on inputs., The card already has the engine's action; a second opinion beside it is how a…, TestAIMode, _thesis()

### Community 60 - "plan.py"
Cohesion: 0.08
Nodes (22): _expected_outcome(), _latest_atr(), Decimal, Deterministic plan cards: the numbers behind the daily prescription. Every…, Wilder ATR over the reconciled history, or None if it can't be computed., PnL at *exit_price*, net of entry costs, exit costs and CGT. The gross figure…, Long-only, event-driven backtester with the full Nepal cost model. The engine…, exposure_pct() (+14 more)

### Community 61 - "Developers Guide — NEPSE Trader"
Cohesion: 0.08
Nodes (26): 10. Layer: costs and taxes, 11. Layer: paper trading, 12. Layer: RAG, 13. Layer: AI, 14. Layer: advisor, 15. Layer: MeroShare mirror, 16. Layer: health, 17. Surface: CLI (+18 more)

### Community 62 - ".parse_announcements"
Cohesion: 0.13
Nodes (8): Parse the announcements table into documents. Columns are ``S.No | Headline |…, date, parametrize, No known-symbol set needed here — the table states the symbol., Daily re-ingestion must upsert, not accumulate., Sites reflow capitalisation; that must not spawn a duplicate document., TestDeterministicIds, TestParseAnnouncements

### Community 63 - "_run"
Cohesion: 0.14
Nodes (5): mode="normal" ignores the analyst entirely rather than half-using it., A default deterministic run over three symbols., _run(), TestNormalMode, TestSettlementInARun

### Community 64 - "_settings"
Cohesion: 0.11
Nodes (12): MonkeyPatch, parametrize, Tests for the runtime Settings model (modes, LLM, budget, RAG, MeroShare).…, Build Settings without reading the developer's real .env., Bulk per-symbol work must not default to a paid provider., claude_cli runs under the user's subscription — no API billing., Env vars are strings; a CSV watchlist must still parse to a list., _settings() (+4 more)

### Community 65 - "main.py"
Cohesion: 0.05
Nodes (86): command, _advisor_horizon(), _advisor_sections(), ai_budget(), ai_models(), ai_test(), auction_advise_cmd(), auction_list_cmd() (+78 more)

### Community 66 - "PriceBar"
Cohesion: 0.19
Nodes (9): _clamp01(), Signal, Clamp ``x`` into [0, 1] (Signal.strength is validated ``0 <= s <= 1``)., Return signals for ``bars`` (chronological ascending)., Return (closes, has_close). ``closes`` carries the last valid close forward…, Convenience: the signal for the last day, or None if none produced., PriceBar, A single security's end-of-day (or snapshot) OHLCV record. (+1 more)

### Community 67 - "fixtures.ts"
Cohesion: 0.05
Nodes (41): aiBudget, aiModels, aiTestOk, auctionAdvice, backtestRun, bulkSignals, bulkStats, confidence (+33 more)

### Community 68 - "ReconciledPrice"
Cohesion: 0.08
Nodes (10): A price for a symbol/date agreed (or disputed) across multiple sources., ReconciledPrice, TestReconcileDocument, client(), fixture, TestBacktest, TestDashboard, TestHealth (+2 more)

### Community 69 - "test_pipeline.py"
Cohesion: 0.10
Nodes (18): pipe(), asyncio, fixture, Integration tests for the daily pipeline (no network)., A fake source that returns canned bars — exercises ingest without network., Async ingest should produce the same result as sync., _seed_hump(), _StubSource (+10 more)

### Community 70 - "rashifal_md"
Cohesion: 0.28
Nodes (4): rashifal_md(), Render a whole advisor run as Markdown. *result* is ``Rashifal.as_dict()``.…, _rashifal(), TestRashifalMd

### Community 71 - "Make It Even Better — Engineering Quality Upgrades"
Cohesion: 0.08
Nodes (24): 1.1 Use `Decimal` for money — **high impact**, 1.2 Property-based tests (Hypothesis) — **high impact, low effort**, 1.3 Golden-file tests for parsers — **medium**, 1. Correctness & financial precision, 2.1 CI pipeline — **high impact, low effort**, `.github/workflows/ci.yml`, 2.2 Static typing in CI — **medium**, 2.3 Coverage measurement — **low**, 2.4 Pre-commit hooks — **low** (+16 more)

### Community 72 - "SmaCrossStrategy"
Cohesion: 0.15
Nodes (12): PortfolioBacktester, PortfolioResult, date, Aggregate performance of a multi-symbol portfolio., Run a strategy across multiple symbols with equal capital allocation., Run *strategy* on each symbol and aggregate results. *symbol_bars* maps symbol…, Fast/slow simple-moving-average crossover., SmaCrossStrategy (+4 more)

### Community 73 - "validate_yaml"
Cohesion: 0.18
Nodes (14): Any, Path, Config file validation using JSON Schema. Provides validation functions for the…, Validate a single YAML file against its JSON Schema. Returns a (possibly empty)…, Validate all config files. Returns list of error messages (empty = OK)., _validate(), validate_all(), validate_yaml() (+6 more)

### Community 75 - "htmlparse.py"
Cohesion: 0.15
Nodes (22): has_header(), Row, Resilient HTML table extraction with a pluggable backend. Two backends produce…, Return the Scrapling Selector class, or None if unavailable., Resolve the effective parse engine name ('scrapling' or 'selectolax')., Return rows of (tag, text) cell tuples for the first table matching…, The text of the ``<td>`` cells in a row (ignoring header ``<th>`` cells)., resolve_engine() (+14 more)

### Community 76 - "compilerOptions"
Cohesion: 0.08
Nodes (23): DOM, src, vite/client, compilerOptions, allowArbitraryExtensions, allowImportingTsExtensions, erasableSyntaxOnly, jsx (+15 more)

### Community 77 - "system_health"
Cohesion: 0.21
Nodes (11): health(), Check every moving part: schema, data freshness, sources, RAG, AI, MeroShare.…, Every check, in a stable order, plus the worst-wins overall verdict. *storage*…, Persist *report* and return its row id. Called only when a caller explicitly…, Recent snapshots, newest first, without their full JSON payload. The payload is…, record_snapshot(), snapshot_history(), system_health() (+3 more)

### Community 78 - "test_rag_corpus.py"
Cohesion: 0.16
Nodes (11): iter_documents(), price_document(), A single day's OHLCV as prose., Drop the ``None`` results that builders return for thin data., _bar(), Tests for the RAG document corpus builders. Two invariants carry the whole…, test_iter_documents_drops_nones(), TestAsRow (+3 more)

### Community 79 - "AccountVault"
Cohesion: 0.18
Nodes (7): AccountVault, BankAccount, _money(), Decimal, Holds the sensitive, encapsulated account state. All money is stored as Decimal…, Accept Decimal / int / str. Refuse float (binary rounding errors)., The public-facing account that performs operations on a vault.

### Community 80 - "TestHtmlToText"
Cohesion: 0.12
Nodes (10): html_to_text(), date, Search the web and return fetched pages as hits. ``kinds`` and ``since`` are…, Reduce a page to ``(title, body_text)``, truncated to ``max_chars``. Script,…, Short stable id for a URL, so re-fetching the same page upserts., Anything that can turn a query into ranked hits., Retriever, _url_key() (+2 more)

### Community 81 - "compilerOptions"
Cohesion: 0.10
Nodes (19): node, vite.config.ts, compilerOptions, allowImportingTsExtensions, erasableSyntaxOnly, lib, module, moduleDetection (+11 more)

### Community 82 - "Tier 2 — strong analytical upside"
Cohesion: 0.10
Nodes (20): 1.1 Corporate-action adjustment (bonus / rights / splits) — **L**, `ingest/` + `analysis/`, 1.2 Verify & enable Chukul + NepseAlpha sources — **M**, `ingest/chukul.py`, new `ingest/nepsealpha.py`, 1.3 Holiday / trading-calendar awareness — **M**, new `calendar.py`, 1.4 Alerting integrations (Telegram / Discord / email) — **S–M**, `reporting.py`, 2.1 Multi-symbol portfolio backtest — **L**, `analysis/backtest.py`, 2.2 Risk-managed position sizing & stops — **M**, `analysis/strategies.py` + backtest, 2.3 Walk-forward optimization & parameter sweeps — **M**, new `analysis/optimize.py`, 2.4 More strategies — **S each**, `analysis/strategies.py` (+12 more)

### Community 83 - "api.py"
Cohesion: 0.07
Nodes (48): FastAPI, Recent sync attempts, newest first — successes and failures alike., sync_history(), add_corporate_action(), advisor_history(), auction_advice_history_endpoint(), auction_latest_endpoint(), _corporate_action_response() (+40 more)

### Community 84 - "Dispatcher"
Cohesion: 0.09
Nodes (20): MethodHandler, Dispatcher, error_response(), Any, Exception, JSON-RPC 2.0 framing and dispatch for the MCP server — transport-agnostic. This…, Routes JSON-RPC methods to registered handlers. Deliberately a plain name →…, Dispatch a parsed request. Returns ``None`` for notifications. (+12 more)

### Community 85 - "corpus.py"
Cohesion: 0.09
Nodes (31): A strategy's decision for a symbol on a date., Signal, _breadth_documents(), _corporate_action_documents(), _documents_for_symbol(), _flush(), IndexReport, _periods() (+23 more)

### Community 86 - "_settings"
Cohesion: 0.12
Nodes (16): ai_budget(), ai_models(), ai_test(), _evidence_builder(), health_report(), Settings for the current request. Read out of ``_state`` rather than calling…, Queue a job and return it immediately, before any work has happened. 409 when…, Every configured source, whether it is enabled, and how it is accessed. (+8 more)

### Community 87 - "Operations.tsx"
Cohesion: 0.12
Nodes (19): api, Job, JobKind, JobStage, JobStageStatus, JOB_BADGE, JobConsole(), Props (+11 more)

### Community 88 - "renderWithProviders.tsx"
Cohesion: 0.13
Nodes (7): pressRun(), runWithResult(), renderDetail(), handlers, Options, renderWithProviders(), server

### Community 89 - "How It Works — NEPSE Trader Internals"
Cohesion: 0.12
Nodes (17): 10. Paper portfolio (`trading/portfolio.py`), 11. Storage & idempotency (`storage/db.py`), 12. Failure philosophy, 13. Advisor and confidence, 14. Prediction journal and outcomes, 15. MeroShare, auction and modes, 1. End-to-end data flow, 2. The politeness & ethics layer (`ingest/base.py`) (+9 more)

### Community 90 - "devDependencies"
Cohesion: 0.12
Nodes (17): jsdom, oxlint, tailwindcss, @testing-library/jest-dom, @testing-library/react, @testing-library/user-event, @types/react-router-dom, @vitest/coverage-v8 (+9 more)

### Community 91 - "test_backtest_risk.py"
Cohesion: 0.33
Nodes (6): _bar(), _buy_sig(), _DummyStrategy, Signal, Tests for risk-managed stop-loss / take-profit in the event-driven backtester., TestStopLossInBacktest

### Community 92 - "SellCandidate"
Cohesion: 0.22
Nodes (7): build_sell_queue(), Which held positions to exit, from the engine's own view of each symbol.…, A held position the engine wants out of, and why., SellCandidate, date, PlanCard, TestSellQueue

### Community 94 - "walkforward.py"
Cohesion: 0.21
Nodes (12): _param_grid(), Any, Walk-forward optimisation with expanding or rolling windows. Splits price…, walk_forward(), WFOFold, WFResult, _bars(), Tests for walk-forward optimisation. (+4 more)

### Community 95 - "test_reporting.py"
Cohesion: 0.11
Nodes (29): backtest_report(), Path, ReconciledPrice, Markdown table of reconciled prices, flagging low-confidence / disputed rows., Markdown summary of backtest performance metrics., Write a combined daily report with a top title and one ``##`` per section., Send a plain-text message via Telegram Bot API., Build a GitHub markdown table of signals (pure, exact-text testable). (+21 more)

### Community 96 - "MeroLaganiFundamentalsClient"
Cohesion: 0.09
Nodes (30): MeroLaganiFundamentalsClient, Fundamentals data scraping from MeroLagani company detail pages., Fetch fundamental data for a single symbol from MeroLagani., AdvisorRunRequest, AiTestRequest, AuctionAdviceRequest, CorporateActionRequest, JobSubmitRequest (+22 more)

### Community 97 - "TestCitations"
Cohesion: 0.31
Nodes (4): normalise_citations(), Coerce whatever the model wrote into ``["[E1]", "[E3]"]`` form. Models write…, A marker only means something if it can match an evidence item., TestCitations

### Community 98 - "_advisor_run_response"
Cohesion: 0.21
Nodes (17): advisor_doses_latest(), _advisor_run_response(), _attach_dose_cards(), _confidence_response(), _dose_response(), _dose_run_response(), _plan_card_response(), Any (+9 more)

### Community 99 - "conftest.py"
Cohesion: 0.14
Nodes (14): Config, Session, _isolate_run_logs(), fixture, Path, pytest_configure(), pytest_runtest_logreport(), pytest_sessionfinish() (+6 more)

### Community 100 - "post"
Cohesion: 0.11
Nodes (22): auction_advice_endpoint(), cancel_job(), journal_distill_endpoint(), _journal_error(), journal_retire_endpoint(), journal_review_endpoint(), journal_score_endpoint(), journal_score_one_endpoint() (+14 more)

### Community 101 - "_ensure_app_settings"
Cohesion: 0.15
Nodes (15): _advisor_symbols(), _ensure_app_settings(), get_meroshare_setting(), get_watchlist(), put_meroshare_setting(), put_watchlist(), Effective integration toggle with its DB-or-environment provenance., Persist a local toggle, or clear it with ``{"enabled": null}``. (+7 more)

### Community 102 - "progress_spinner"
Cohesion: 0.20
Nodes (13): rag_index(), Build the searchable document corpus from what's already in the database. Runs…, Backtest the strategy panel across all symbols and rank the results. Nepal…, screen(), progress_bars(), progress_spinner(), Console, T (+5 more)

### Community 103 - "NEPSE Trader — Agent Context"
Cohesion: 0.13
Nodes (14): Completed advisor scope, Current State, Key Design Decisions, NEPSE Trader — Agent Context, Open Questions / Planned, Project, Project Structure, Recent Sprint Progress (+6 more)

### Community 104 - "test_ingest_news.py"
Cohesion: 0.24
Nodes (5): extract_symbols(), Symbols mentioned in *text*, in first-seen order. Without a ``known_symbols``…, Tests for news + announcement ingestion. Two things carry this module and are…, No known-symbol set means no tagging — mistagging is worse than nothing., TestExtractSymbols

### Community 105 - "check_freshness"
Cohesion: 0.22
Nodes (10): check_database(), check_freshness(), date, The database exists, is readable, and holds price rows., How far behind the newest reconciled close is, counted in trading days., Trading days strictly after *start* up to and including *end*., _trading_days_between(), date (+2 more)

### Community 106 - "NewsClient"
Cohesion: 0.48
Nodes (3): NewsClient, News plus announcements, deduplicated by ``doc_id``., ShareSansar news + announcement listings as retrievable documents.

### Community 107 - ".parse_news_list"
Cohesion: 0.21
Nodes (3): Parse a ShareSansar news listing page into news documents. The listing is a…, Fuzzy date parsing would turn "11% dividend" into the 11th of this month., TestParseNewsList

### Community 108 - "read_bool"
Cohesion: 0.29
Nodes (9): ensure_table(), Any, Connection, Reads over the ``app_settings`` key/value table. Migration…, Assert the migrated table exists. Deliberately a guard and not ``CREATE…, ``(value, updated_at)`` for *key*, or ``(None, None)`` when unusable., As :func:`read_json`, but only a real JSON boolean counts as an override., read_bool() (+1 more)

### Community 109 - "dependencies"
Cohesion: 0.15
Nodes (13): clsx, lucide-react, react, react-dom, react-router-dom, recharts, dependencies, clsx (+5 more)

### Community 110 - "TestRagSearch"
Cohesion: 0.15
Nodes (3): _index(), TestNews, TestRagSearch

### Community 111 - "NEPSE Trader — Operations Runbook"
Cohesion: 0.12
Nodes (16): 10. MeroShare and auction safety, 11. MCP setup, 1. Daily lifecycle, 2. Scheduling (cron), 3. Sources & enabling/disabling, 4. HAR endpoint refresh (when a source breaks), 5. Paper trading, 6. Troubleshooting (+8 more)

### Community 112 - "How To Use — NEPSE Trader"
Cohesion: 0.06
Nodes (32): 10. Paper trading, 11. The daily run, 12. Advice — rashifal, advise, doses, 13. Prediction journal, 14. Auction bid ceiling, 15. Fundamentals and corporate actions, 16. Searching your own data, 17. AI mode (+24 more)

### Community 113 - "TestJobRoutes"
Cohesion: 0.20
Nodes (3): The route only accepts the five real kinds, so a typo never reaches the…, Cancel is driven over HTTP; the work is a stub so the test stays fast. The kind…, TestJobRoutes

### Community 114 - "demat_fingerprint"
Cohesion: 0.18
Nodes (14): demat_fingerprint(), demat_last4(), _normalise(), Privacy-safe identifiers for persisted MeroShare mirror rows. The CDSC…, Return a deterministic, non-reversible storage key for a demat value., Return only the final four characters for masked display., _holding_rows(), _now() (+6 more)

### Community 115 - "test_sharesansar.py"
Cohesion: 0.05
Nodes (60): EndpointSpec, _int(), _num(), parse_as_of_date(), _parse_date(), _parse_datetime(), _parse_headline(), date (+52 more)

### Community 116 - "test_cli_advisor.py"
Cohesion: 0.21
Nodes (7): fixture, Offline coverage for the advisor, journal, auction and MeroShare CLI surface., _seed_prices(), _storage(), _temp_db(), test_journal_score_review_distill_and_retire_lifecycle(), test_rashifal_and_doses_are_offline_and_include_all_four_horizons()

### Community 117 - "Auction.tsx"
Cohesion: 0.19
Nodes (9): AuctionAdvice, AuctionAdviceRequest, AdviceResult(), AuctionPage(), confidenceVariant(), initialForm, money(), price() (+1 more)

### Community 118 - "Rashifal.tsx"
Cohesion: 0.27
Nodes (12): Dose, PlanCard, confidenceLabel(), confidenceValue(), confidenceVariant(), DoseStrip(), HORIZONS, money() (+4 more)

### Community 119 - "22. Recipes"
Cohesion: 0.29
Nodes (7): 22. Recipes, Add a data source, Add a health check, Add a strategy, Add a table, Add an indicator, Add an MCP tool

### Community 120 - "TestDegradation"
Cohesion: 0.17
Nodes (6): RuntimeError, ExplodingAnalyst, A badly-behaved analyst: raises instead of degrading., Every failure path must yield the full deterministic report plus a banner., It must not raise out of build_rashifal — that is the whole contract., TestDegradation

### Community 121 - "Capabilities — NEPSE Trader"
Cohesion: 0.18
Nodes (11): 10. Performance characteristics, 1. Capability matrix, 2. Data & coverage, 3. Analytical capabilities, 4. Backtesting & screening, 5. Cost & tax fidelity, 6. The once-a-day report, 7. Advisor, mirror and MCP details (+3 more)

### Community 122 - "health.py"
Cohesion: 0.15
Nodes (14): Check, check_journal(), check_paper(), _guarded(), problems(), Any, One read-only health report over everything the toolkit owns. The daily loop…, Prediction lifecycle backlog: what is open, scored-but-unreviewed, retired. (+6 more)

### Community 123 - "NEPSE Trader"
Cohesion: 0.18
Nodes (11): Advisor, journal and MeroShare, Architecture, Daily automation, Data sources & reliability, Disclaimer, Documentation, Install, Nepal cost & tax model (+3 more)

### Community 124 - "test_cli.py"
Cohesion: 0.18
Nodes (3): fixture, CLI smoke tests via Typer's CliRunner (no network)., _temp_db()

### Community 125 - "NEPSE Trader — project skill"
Cohesion: 0.20
Nodes (9): Common tasks → commands, Companion skills, Fetch / parse engines, Hard rules (do not cross), NEPSE Trader — project skill, Setup (once), The once-a-day run (the main thing), When a source breaks (endpoint discovery) (+1 more)

### Community 126 - "_decide"
Cohesion: 0.23
Nodes (6): _decide(), Signal, Turn the strategy panel's votes into an action, conviction and reasons.…, AVOID exists for the AI vocabulary; the engine has no rule that emits it., _signal(), TestDecide

### Community 127 - "meroshare_status"
Cohesion: 0.15
Nodes (14): keyring_available(), _password_from_keyring(), Whether the optional ``keyring`` module imports. ``(ok, reason)``., Fetch a password from the OS keyring. Returns ``(password, reason)``. An empty…, _meroshare_enabled(), _meroshare_settings(), meroshare_status(), meroshare_sync() (+6 more)

### Community 128 - "_client"
Cohesion: 0.46
Nodes (4): _client(), mock, A missing news leg costs commentary, never numbers — it must not raise., TestFetch

### Community 129 - "Alerter"
Cohesion: 0.11
Nodes (15): Alerter, Response, Pluggable alert backends: Telegram, Discord, SMTP, and generic webhook. Every…, Thin POST wrapper kept separate so tests can monkeypatch it., POST the alert if a webhook is set; return success. No webhook -> False, no…, Send a message to a Discord channel via webhook., Send an email via SMTP. Returns True on success., test_alerter_no_webhook_returns_false_no_network() (+7 more)

### Community 131 - "Per-site capture recipes"
Cohesion: 0.22
Nodes (9): 1. ShareSansar — `sharesansar.har` (PRIMARY), 2. Chukul — `chukul.har` (verify inferred /v1/ paths), 3. MeroLagani — `merolagani.har` (secondary HTML), 4. NepseAlpha — `nepsealpha.har` (TradingView UDF, Cloudflare-gated), 5. NEPSE official — `nepse_official.har` (reference / replay only), HAR Capture Plan — NEPSE data sources, How to capture a HAR (Chrome / Firefox / Edge), Per-site capture recipes (+1 more)

### Community 132 - "Job"
Cohesion: 0.13
Nodes (9): Job, JobStage, A unit of background work and everything the UI needs to render it., Start *kind* in a worker thread and return its job immediately. Raises…, Ask a job to stop. Returns the job, or None when the id is unknown. Cancelling…, One named step of a job, with an optional item counter. ``current``/``total``…, RLock, Settings (+1 more)

### Community 133 - "plugins"
Cohesion: 0.22
Nodes (8): oxc, typescript, warn, plugins, rules, react/only-export-components, react/rules-of-hooks, $schema

### Community 134 - "pipeline.py"
Cohesion: 0.16
Nodes (12): date, Interface every source adapter implements. Concrete clients (ShareSansar,…, SourceClient, NepseScraperClient, Adapter over the optional MIT ``nepse_scraper`` package. The third-party…, FloorsheetEntry, A single matched trade from the floorsheet (transaction-level data)., build_clients() (+4 more)

### Community 135 - "TestExtractResultLinks"
Cohesion: 0.22
Nodes (6): extract_result_links(), Result URLs from the configured search endpoint, best first., Pull outbound result URLs from a search results page. DuckDuckGo's HTML…, Turn a search-engine redirect link into the destination URL., _unwrap_redirect(), TestExtractResultLinks

### Community 136 - "scripts"
Cohesion: 0.25
Nodes (8): scripts, build, coverage, dev, lint, preview, test, test:run

### Community 137 - "NEPSE risk & position sizing — project skill"
Cohesion: 0.29
Nodes (6): Ask the engine for exact costs (don't approximate), Fit-check an existing paper portfolio, Hard rules, Nepal mechanics you MUST respect, NEPSE risk & position sizing — project skill, Sizing protocol (fixed-fractional, R-based)

### Community 138 - "MeroSharePortfolio"
Cohesion: 0.14
Nodes (12): ConnectionResult, MeroShareError, Exception, Base for every failure in this package. Messages carry no credential., Outcome of :func:`connect` — a login probe that fetches nothing else., MeroShareCredentialError, Exception, Credentials are missing or unusable. Never contains a credential. (+4 more)

### Community 139 - "test_health.py"
Cohesion: 0.19
Nodes (9): check_config(), check_rag(), YAML config parses against its schema, and at least one source is on., Corpus size, per-kind coverage, and whether ranked search is available., fixture, Health-report tests: every verdict, the guard, and the snapshot history. Fully…, storage(), TestConfig (+1 more)

### Community 140 - "test_advisor_rashifal.py"
Cohesion: 0.18
Nodes (10): The sector with the best mean change today. Takes an already-grouped mapping so…, _sector_of_the_day(), _bars(), _buys(), conn(), fixture, Signal, Tests for the rashifal composer. Two properties matter more than the rest, and… (+2 more)

### Community 141 - "news.py"
Cohesion: 0.27
Nodes (11): _clean(), _headline_key(), _nearby_date(), _news_document(), _parse_date(), date, datetime, News and company announcements — the RAG corpus the database cannot derive.… (+3 more)

### Community 142 - "NEPSE backtest protocol — project skill"
Cohesion: 0.33
Nodes (5): Hard rules, NEPSE backtest protocol — project skill, Red flags that mean "do not deploy", The protocol (run in order), Why discipline matters on NEPSE specifically

### Community 143 - "check_meroshare"
Cohesion: 0.39
Nodes (3): check_meroshare(), The read-only mirror: toggle, credential completeness, last sync. Reports field…, TestMeroShare

### Community 144 - "23. All the settings"
Cohesion: 0.29
Nodes (7): 23. All the settings, AI providers, AI spending caps, Analysis, Fetching politely, Search and MeroShare, Where things live

### Community 145 - "package.json"
Cohesion: 0.40
Nodes (4): name, private, type, version

### Community 146 - "test_golden_fixtures.py"
Cohesion: 0.36
Nodes (9): _load(), Golden-file tests: load fixture files and assert parsers produce expected…, test_chukul_prices_data(), test_chukul_prices_list(), test_chukul_prices_results(), test_ml_indices(), test_ml_stock_quote(), test_ss_floorsheet() (+1 more)

### Community 147 - "check_ai"
Cohesion: 0.43
Nodes (3): check_ai(), Whether AI mode could actually answer, and how much budget is left. Reads the…, TestAi

### Community 148 - "React + TypeScript + Vite"
Cohesion: 0.50
Nodes (3): Expanding the Oxlint configuration, React Compiler, React + TypeScript + Vite

### Community 149 - "Health.tsx"
Cohesion: 0.22
Nodes (9): HealthCheck, HealthReport, HealthSnapshot, HealthStatus, BADGE_VARIANT, CheckRow(), ICONS, metricRows() (+1 more)

### Community 158 - "_Base"
Cohesion: 0.29
Nodes (5): Fetch and parse fundamentals for *symbol*., _Base, FundamentalData, BaseModel, TestFundamentalDocument

### Community 170 - "TestRegime"
Cohesion: 0.38
Nodes (4): Describe the tape in one phrase, from advancers vs decliners., _regime(), parametrize, TestRegime

### Community 171 - "3. Robustness & resilience"
Cohesion: 0.40
Nodes (5): 3.1 Async, concurrent ingestion — **high impact**, `ingest/base.py`, 3.2 Per-source circuit breaker — **medium**, 3.3 Respect `Retry-After` and `robots.txt` programmatically — **medium**, 3.4 Schema-driven HTML parsing — **medium**, `ingest/sharesansar.py`, `merolagani.py`, 3. Robustness & resilience

### Community 174 - "._split_csv"
Cohesion: 0.40
Nodes (3): Any, field_validator, Accept a comma-separated string from env for list-valued settings.

### Community 177 - "check_ingest"
Cohesion: 0.43
Nodes (3): check_ingest(), The error rate over the most recent ingest attempts, per source., TestIngest

### Community 178 - "check_schema"
Cohesion: 0.24
Nodes (6): check_schema(), Connection, Every migration in the registry applied, and nothing unknown applied., One stored report in full, or None when that id was never recorded., snapshot(), TestSchema

### Community 180 - "plan_cards_md"
Cohesion: 0.38
Nodes (4): plan_cards_md(), Render plan cards as one table row per symbol. Cards are…, _card(), TestPlanCardsMd

### Community 181 - "card"
Cohesion: 0.50
Nodes (4): card(), fixture, PlanCard, storage()

### Community 182 - "serve_stdio"
Cohesion: 0.12
Nodes (18): build_server(), Construct a fully wired :class:`MCPServer`. Separate from :func:`serve_stdio`…, Serve MCP over newline-delimited JSON-RPC until stdin closes. Blocks. Returns…, _resolve_streams(), serve_stdio(), _drive(), fixture, Write both raw and reconciled bars: tools read from each side. (+10 more)

### Community 189 - "do_not_touch_md"
Cohesion: 0.50
Nodes (3): do_not_touch_md(), Render the excluded symbols with their reasons. A symbol missing from the…, TestDoNotTouchMd

### Community 190 - "sell_queue_md"
Cohesion: 0.50
Nodes (3): Render the exit queue: what to sell, why, and the earliest legal date., sell_queue_md(), TestSellQueueMd

### Community 208 - "CostEngine"
Cohesion: 0.07
Nodes (43): CostBreakdown, CostEngine, Decimal, Nepal equity transaction cost & tax engine. Computes the full, realistic cost…, Convert a number to paisa-precise Decimal (2 dp, half-up)., _to_money(), Multi-symbol portfolio backtester with equal-weight capital allocation., OrderSide (+35 more)

### Community 210 - "TokenBudget"
Cohesion: 0.06
Nodes (22): BudgetStatus, BudgetSummary, iso_week(), Connection, date, Token budgeting: hard ceilings with a DB-backed ledger. Three caps, all from…, Spend accounting over the ``ai_budget_ledger`` table., ``(billable_calls, billable_tokens)`` for today. Cache hits excluded. (+14 more)

## Knowledge Gaps
- **401 isolated node(s):** `nepse-trader`, `$schema`, `typescript`, `oxc`, `react/rules-of-hooks` (+396 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **29 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Settings` connect `Settings` to `_client`, `LLMRouter`, `meroshare/__init__.py`, `pipeline.py`, `test_ai_analyst.py`, `base.py`, `TestExtractResultLinks`, `MeroSharePortfolio`, `test_health.py`, `ResponseCache`, `parse_into`, `check_meroshare`, `MeroShareHolding`, `test_mcp_server.py`, `check_ai`, `BaseClient`, `MeroShareClient`, `JobRegistry`, `server.py`, `Analyst`, `DailyPipeline`, `TestBulkAnalytics`, `LLMResponse`, `._split_csv`, `TestAdvisor`, `TestAiRoutes`, `check_ingest`, `check_schema`, `TestCorporateActions`, `TestPaperTrades`, `test_meroshare.py`, `serve_stdio`, `MeroShareCredentials`, `test_web_operations.py`, `.parse_announcements`, `_settings`, `main.py`, `TestMeroShareImport`, `system_health`, `TestHtmlToText`, `TokenBudget`, `api.py`, `Dispatcher`, `MeroLaganiFundamentalsClient`, `TestCitations`, `post`, `test_ingest_news.py`, `check_freshness`, `.parse_news_list`, `TestRagSearch`, `TestJobRoutes`, `health.py`?**
  _High betweenness centrality (0.129) - this node is a cross-community bridge._
- **Why does `PriceBar` connect `PriceBar` to `indicator_document`, `reporting.py`, `Storage`, `pipeline.py`, `base.py`, `test_nepse_official.py`, `test_health.py`, `test_advisor_rashifal.py`, `SourceName`, `test_strategies.py`, `MeroShareHolding`, `test_mcp_server.py`, `outcomes.py`, `Backtester`, `ChukulClient`, `_Base`, `build_plan_card`, `NepseAlphaClient`, `DailyPipeline`, `screen`, `test_properties.py`, `serve_stdio`, `test_web_operations.py`, `plan.py`, `ReconciledPrice`, `test_pipeline.py`, `SmaCrossStrategy`, `field_validator`, `test_rag_corpus.py`, `CostEngine`, `corpus.py`, `test_backtest_risk.py`, `walkforward.py`, `test_reporting.py`, `check_freshness`, `test_sharesansar.py`, `test_cli_advisor.py`?**
  _High betweenness centrality (0.072) - this node is a cross-community bridge._
- **Why does `Storage` connect `Storage` to `LLMRouter`, `pipeline.py`, `test_ai_analyst.py`, `test_health.py`, `test_advisor_rashifal.py`, `ResponseCache`, `SourceName`, `MeroShareHolding`, `test_mcp_server.py`, `doses.py`, `journal.py`, `ChukulClient`, `JobRegistry`, `migrations.py`, `server.py`, `save_rashifal`, `TestRegime`, `_build_advisor_result`, `LLMResponse`, `TestBulkAnalytics`, `DegradingAnalyst`, `card`, `MeroShareCredentials`, `serve_stdio`, `TestHostileAnalyst`, `CorporateAction`, `test_meroshare.py`, `FakeAnalyst`, `test_web_operations.py`, `_run`, `main.py`, `ReconciledPrice`, `test_pipeline.py`, `system_health`, `CostEngine`, `api.py`, `Dispatcher`, `SellCandidate`, `test_cli_advisor.py`, `TestDegradation`?**
  _High betweenness centrality (0.065) - this node is a cross-community bridge._
- **Are the 163 inferred relationships involving `Settings` (e.g. with `Analyst` and `BudgetStatus`) actually correct?**
  _`Settings` has 163 INFERRED edges - model-reasoned connections that need verification._
- **Are the 75 inferred relationships involving `Document` (e.g. with `JournalError` and `Prediction`) actually correct?**
  _`Document` has 75 INFERRED edges - model-reasoned connections that need verification._
- **Are the 13 inferred relationships involving `Storage` (e.g. with `_Result` and `DegradingAnalyst`) actually correct?**
  _`Storage` has 13 INFERRED edges - model-reasoned connections that need verification._
- **Are the 54 inferred relationships involving `DocumentIndex` (e.g. with `JournalError` and `Prediction`) actually correct?**
  _`DocumentIndex` has 54 INFERRED edges - model-reasoned connections that need verification._