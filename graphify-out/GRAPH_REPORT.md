# Graph Report - nepse-trader  (2026-08-28)

## Corpus Check
- 221 files · ~285,335 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 4837 nodes · 12384 edges · 193 communities (167 shown, 26 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 1159 edges (avg confidence: 0.51)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `59a16d38`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- _settings
- _router
- meroshare/__init__.py
- indicator_document
- reporting.py
- Storage
- LLMResponse
- DocumentIndex
- Settings
- test_nepse_official.py
- sharesansar.py
- build_evidence
- ResponseCache
- parse_into
- reconcile_bars
- test_strategies.py
- MeroShareHolding
- test_mcp_server.py
- index.py
- jobs.py
- quant.py
- doses.py
- advisor/__init__.py
- test_properties.py
- outcomes.py
- Backtester
- ChukulClient
- WebRetriever
- Confidence
- MeroShareClient
- JobRegistry
- build_plan_card
- Plan: NEPSE Trader — Full Completion
- BaseClient
- migrations.py
- merolagani.py
- test_costs.py
- server.py
- test_logging_setup.py
- analyzer.py
- Analyst
- add_trading_days
- LLMRouter
- DailyPipeline
- serve_stdio
- _budget
- TestAdvisor
- types.ts
- pipeline.py
- get
- CostEngine
- auction.py
- test_mcp_protocol.py
- test_meroshare.py
- MeroShareCredentials
- CorporateAction
- Plan: Web UI Dashboard
- test_web_operations.py
- App.tsx
- .daily_report
- backtest.py
- Developers Guide — NEPSE Trader
- .parse_announcements
- _run
- _settings
- main.py
- PriceBar
- fixtures.ts
- nepse_trader/models.py
- test_pipeline.py
- rashifal_md
- Make It Even Better — Engineering Quality Upgrades
- SmaCrossStrategy
- validate_yaml
- Position
- htmlparse.py
- compilerOptions
- system_health
- Document
- AccountVault
- Retriever
- compilerOptions
- Tier 2 — strong analytical upside
- api.py
- Dispatcher
- corpus.py
- FetchResult
- Operations.tsx
- renderWithProviders.tsx
- How It Works — NEPSE Trader Internals
- devDependencies
- test_backtest_risk.py
- build_rashifal
- Any
- walkforward.py
- signals_markdown
- MeroLaganiFundamentalsClient
- TestCitations
- _advisor_run_response
- conftest.py
- post
- _settings
- progress_spinner
- NEPSE Trader — Agent Context
- test_ingest_news.py
- TestDatabaseAndFreshness
- NewsClient
- .parse_news_list
- read_bool
- dependencies
- TestRagSearch
- NEPSE Trader — Operations Runbook
- How To Use — NEPSE Trader
- TestJobRoutes
- check_rag
- test_sharesansar.py
- test_cli_advisor.py
- Auction.tsx
- Rashifal.tsx
- 22. Recipes
- TestTableBrowser
- Capabilities — NEPSE Trader
- health.py
- NEPSE Trader
- test_cli.py
- NEPSE Trader — project skill
- _decide
- ReconciledPrice
- _client
- test_reporting.py
- Per-site capture recipes
- Job
- plugins
- SourceClient
- TestExtractResultLinks
- scripts
- NEPSE risk & position sizing — project skill
- client.py
- test_health.py
- TestSectorOfTheDay
- news.py
- NEPSE backtest protocol — project skill
- check_meroshare
- 23. All the settings
- package.json
- TestSymbols
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
- HoldingDiff
- @tailwindcss/vite
- @types/react
- @types/react-dom
- typescript
- vite
- @vitejs/plugin-react
- vitest
- nepse-trader
- TestDeterministicIds
- 3. Robustness & resilience
- TestBulkAnalytics
- TestPaperTrades
- ._split_csv
- TestAiRoutes
- TestCorporateActions
- ._post
- check_schema
- TestJournalLifecycleAPI
- plan_cards_md
- TestHtmlToText
- _drive
- _seed
- save_auction_advice
- _StdioStreams
- oxlint
- do_not_touch_md
- sell_queue_md
- TestMeroShareImport
- _to_money
- TokenBudget
- conn

## God Nodes (most connected - your core abstractions)
1. `Settings` - 258 edges
2. `Storage` - 139 edges
3. `Document` - 138 edges
4. `PriceBar` - 136 edges
5. `DocumentIndex` - 135 edges
6. `LLMResponse` - 124 edges
7. `CostEngine` - 120 edges
8. `DailyPipeline` - 102 edges
9. `BaseClient` - 91 edges
10. `TokenBudget` - 75 edges

## Surprising Connections (you probably didn't know these)
- `TestDecide` --uses--> `Skipped`  [INFERRED]
  tests/test_advisor_plan.py → nepse_trader/advisor/plan.py
- `_Result` --uses--> `PlanCard`  [INFERRED]
  tests/test_advisor_journal.py → nepse_trader/advisor/plan.py
- `TestDecide` --uses--> `PlanCard`  [INFERRED]
  tests/test_advisor_plan.py → nepse_trader/advisor/plan.py
- `DegradingAnalyst` --uses--> `PlanCard`  [INFERRED]
  tests/test_advisor_rashifal.py → nepse_trader/advisor/plan.py
- `ExplodingAnalyst` --uses--> `PlanCard`  [INFERRED]
  tests/test_advisor_rashifal.py → nepse_trader/advisor/plan.py

## Import Cycles
- None detected.

## Communities (193 total, 26 thin omitted)

### Community 0 - "_settings"
Cohesion: 0.05
Nodes (38): _anthropic_text(), AnthropicProvider, ClaudeCliProvider, estimate_tokens(), NullProvider, _openrouter_text(), OpenRouterProvider, The local Claude Code CLI, driven as a subprocess. The prompt goes in on… (+30 more)

### Community 1 - "_router"
Cohesion: 0.06
Nodes (33): ExplodingProvider, FakeProvider, _ok(), _prime_cache(), Tests for the LLM router. The contract this file pins down is the order of the…, A badly-behaved leg: it raises instead of returning a failed response., A router whose ledger day is pinned, so a midnight run can't straddle two., Tiers are code, not config — a typo here is a bug, not a bad .env. (+25 more)

### Community 2 - "meroshare/__init__.py"
Cohesion: 0.10
Nodes (28): Dialect, import_portfolio(), ImportError_, _match_column(), _norm(), parse_holdings_csv(), parse_holdings_file(), Exception (+20 more)

### Community 3 - "indicator_document"
Cohesion: 0.18
Nodes (10): build_symbol_documents(), indicator_document(), Latest reading of every indicator, with its interpretation stated., Every document derivable for one symbol from its bar history. Only the most…, A bare number is useless in a report; the reading must be explained., Daily re-indexing must upsert, not accumulate., A rising series long enough for SMA50/RSI/MACD/Bollinger to have values., _series() (+2 more)

### Community 4 - "reporting.py"
Cohesion: 0.13
Nodes (22): _fmt_num(), leaderboard_md(), market_overview_md(), _md_escape(), movers_md(), price_bars_markdown(), print_signals(), Console (+14 more)

### Community 5 - "Storage"
Cohesion: 0.06
Nodes (34): export_csv(), export_parquet(), Path, _d(), _dt(), Connection, date, datetime (+26 more)

### Community 6 - "LLMResponse"
Cohesion: 0.08
Nodes (22): LLMResponse, What a provider returned — or why it didn't., True when there is usable text and no error., _analyst(), conn(), date, fixture, Path (+14 more)

### Community 7 - "DocumentIndex"
Cohesion: 0.06
Nodes (25): FixtureRequest, DocumentIndex, Connection, Remove every document of one kind (used when rebuilding a slice)., Document count per kind — what the corpus actually holds., Read/write access to the document corpus and its search index., True when bm25 ranking is available; False means the LIKE fallback., _conn() (+17 more)

### Community 8 - "Settings"
Cohesion: 0.08
Nodes (44): BaseSettings, Connection, Runtime settings. Override via env vars (NEPSE_*) or .env., Settings, FetchError, Client, Exception, RateLimitedError (+36 more)

### Community 9 - "test_nepse_official.py"
Cohesion: 0.07
Nodes (53): decode_content(), _extract_records(), find_entries(), _first(), HarReplayClient, is_available(), load_har(), _looks_sharesansar() (+45 more)

### Community 10 - "sharesansar.py"
Cohesion: 0.17
Nodes (14): EndpointSpec, load_cost_model(), load_sources(), Path, _read_yaml(), SourceSpec, _parse_headline(), ShareSansar ingestion client — the project's PRIMARY public-data source.… (+6 more)

### Community 11 - "build_evidence"
Cohesion: 0.07
Nodes (33): _as_scored(), build_evidence(), EvidencePack, Turning retrieved documents into a bounded, citable evidence block. An…, A compact source list for the human-facing report., Pack hits into an :class:`EvidencePack` under both ceilings. ``max_documents``…, Normalise either input shape to (document, score) pairs., Interleave across kinds, preserving each kind's internal ranking. (+25 more)

### Community 12 - "ResponseCache"
Cohesion: 0.07
Nodes (28): cache_key(), Connection, Delete entries past the TTL. Returns how many went., Size and age of the cache, for ``ai budget``., Stable key for a request's content. The parts are joined with a separator that…, SQLite-backed cache over the ``ai_cache`` table., A fresh cached response, or None on a miss or an expired entry., Store a successful response. Returns whether it was written. Failures are never… (+20 more)

### Community 13 - "parse_into"
Cohesion: 0.07
Nodes (22): parse_into(), T, Parse *text* into *model*, or return None and log why. ``defaults`` fill fields…, _critique_json(), _note_json(), parametrize, The contract: a failed pass costs narrative, never an exception., Some models wrap the single answer in a list. (+14 more)

### Community 14 - "reconcile_bars"
Cohesion: 0.42
Nodes (8): ReconciledPrice, reconcile_bars(), _bar(), Tests for cross-source reconciliation., test_full_agreement_high_confidence(), test_groups_by_symbol_and_date(), test_outlier_flags_dispute_and_lowers_confidence(), test_single_source_no_dispute_but_low_confidence_share()

### Community 15 - "test_strategies.py"
Cohesion: 0.07
Nodes (43): BollingerStrategy, CompositeStrategy, DonchianStrategy, IchimokuStrategy, MacdStrategy, MeanReversionStrategy, ABC, Long-only technical trading strategies producing dated :class:`Signal`s. Each… (+35 more)

### Community 16 - "MeroShareHolding"
Cohesion: 0.05
Nodes (26): MeroShareHolding, field_validator, One scrip balance in the user's demat account, as MeroShare reports it., Total invested in this scrip per the portal's WACC., _bars(), client(), empty_client(), _make_client() (+18 more)

### Community 17 - "test_mcp_server.py"
Cohesion: 0.07
Nodes (46): _call(), _payload(), parametrize, Server-layer tests: tool registry, tool call semantics, and the stdio loop.…, Invoke a tool through the dispatcher and return the raw MCP result., Parse the JSON a tool rendered into its single text content block., An oversized request must fail loudly; a truncated answer would read as…, Every unbounded list carries ``returned``/``truncated`` alongside ``count``. (+38 more)

### Community 18 - "index.py"
Cohesion: 0.13
Nodes (15): _matched(), date, Row, The searchable document index: SQLite FTS5, with a LIKE fallback.…, Best-matching documents for *query*, most relevant first.…, Term-overlap ranking. Correct, just less clever than bm25., Newest documents matching the filters, ignoring relevance., Extract searchable words (Latin + Devanagari) from a raw query. (+7 more)

### Community 19 - "jobs.py"
Cohesion: 0.18
Nodes (16): _job_ingest(), _job_rag_index(), _job_reconcile(), _job_run_daily(), _job_screen(), JobContext, _now(), date (+8 more)

### Community 20 - "quant.py"
Cohesion: 0.08
Nodes (45): annualized_return(), annualized_volatility(), beta(), correlation(), covariance(), kurtosis(), max_drawdown(), mean() (+37 more)

### Community 21 - "doses.py"
Cohesion: 0.05
Nodes (68): market(), A market-dependent confidence, clamped to :data:`MARKET_CEILING`. Every…, _add_sell_guidance(), build_dose_run(), build_doses(), _card_horizon(), _card_value(), _confidence_for_card() (+60 more)

### Community 22 - "advisor/__init__.py"
Cohesion: 0.10
Nodes (54): Public advisor API: deterministic plans, confidence, doses and review., _as_date(), _confidence(), confidence_for_prediction(), distill_lesson(), _fetch(), get_prediction(), journal_history() (+46 more)

### Community 23 - "test_properties.py"
Cohesion: 0.04
Nodes (76): given, atr(), bollinger_bands(), chikou_span(), donchian_channel(), ema(), kijun_sen(), latest() (+68 more)

### Community 24 - "outcomes.py"
Cohesion: 0.10
Nodes (40): _date(), _is_short(), _number(), Outcome, OutcomeResult, persist_score(), _prediction_symbol(), Any (+32 more)

### Community 25 - "Backtester"
Cohesion: 0.09
Nodes (35): Backtester, BacktestResult, _max_drawdown(), date, Event-driven, long-only backtester over a single symbol's price bars., Replay ``bars`` for ``strategy`` and return a :class:`BacktestResult`. Bars are…, Apply slippage: buys fill higher, sells fill lower., Largest whole-share quantity affordable within the cash budget. Budget is… (+27 more)

### Community 26 - "ChukulClient"
Cohesion: 0.08
Nodes (37): _as_records(), ChukulClient, _int(), _num(), _pick(), Any, date, Chukul JSON source adapter. Chukul (https://chukul.com) is powered by a… (+29 more)

### Community 27 - "WebRetriever"
Cohesion: 0.12
Nodes (24): build_retriever(), HybridRetriever, LocalRetriever, Retrievers: where evidence comes from. Three implementations behind one small…, Local first, web only when the local result set is thin. ``min_local_hits`` is…, The right retriever for the current mode. Offline (or web disabled) gives a…, Retrieval from the local document index. Offline, always available., Live search + page fetch. Requires online mode and a fetch client. The search… (+16 more)

### Community 28 - "Confidence"
Cohesion: 0.10
Nodes (25): band_for(), blend(), certain(), Confidence, confidence_from_history(), ConfidenceError, penalise(), ValueError (+17 more)

### Community 29 - "MeroShareClient"
Cohesion: 0.09
Nodes (24): connect(), MeroShareAuthError, MeroShareClient, MeroShareFetchError, MeroShareHolding, Response, Login was refused, or the session expired., A read failed: transport, bad status, or an unparseable body. (+16 more)

### Community 30 - "JobRegistry"
Cohesion: 0.13
Nodes (10): JobRegistry, In-memory job store that runs at most one job at a time., Drop all history. Used between tests so registries never leak state., Register throwaway job kinds, and remove them again afterwards. Editing the…, A worker must never share the request-path Storage., Entering a stage checks for cancellation, so later work never starts., A Saturday must not reach the network. Every stage is skipped., stub_handlers() (+2 more)

### Community 31 - "build_plan_card"
Cohesion: 0.04
Nodes (40): build_plan_card(), build_plan_cards(), _expected_outcome(), _latest_atr(), PlanCard, Confidence, date, Decimal (+32 more)

### Community 32 - "Plan: NEPSE Trader — Full Completion"
Cohesion: 0.05
Nodes (43): Overview, Plan: NEPSE Trader — Full Completion, Potential Risks & Gotchas (addressed), Prerequisites, Rollback Plan, Sprint 0: Engineering Foundation, Sprint 1: Tier 1 Features, Sprint 2: Analytical Upside (+35 more)

### Community 33 - "BaseClient"
Cohesion: 0.10
Nodes (15): BaseClient, Wraps httpx with throttling, retries, and optional raw-response caching., NepseAlphaClient, Any, date, NepseAlpha ingestion client — TradingView UDF format. NepseAlpha…, Fetch daily price bars for *symbol* from the UDF history endpoint. The endpoint…, NepseAlpha is supplementary and doesn't support whole-market fetch. Returns an… (+7 more)

### Community 34 - "migrations.py"
Cohesion: 0.05
Nodes (42): Path, _applied_versions(), _create_version_table(), _m0000_initial(), _m0001_corporate_actions(), _m0002_adjusted_close(), _m0003_rag_documents(), _m0004_ai() (+34 more)

### Community 35 - "merolagani.py"
Cohesion: 0.09
Nodes (33): HTMLParser, _build_column_map(), _cell_at(), _cell_text(), _data_rows(), _first_match(), _int(), MeroLaganiClient (+25 more)

### Community 36 - "test_costs.py"
Cohesion: 0.21
Nodes (16): CommissionSlab, CostModel, BaseModel, Nepal equity transaction cost + tax model. Values are tunable via YAML., _engine(), Tests for the Nepal cost & tax engine. The headline test reproduces the…, test_buy_breakdown_matches_worked_example(), test_cgt_boundary_exactly_365_days_is_short_term() (+8 more)

### Community 37 - "server.py"
Cohesion: 0.11
Nodes (22): _hit_to_dict(), _holding_to_dict(), _json_text(), MCPServer, _normalise_symbols(), _optional_bool(), _optional_choice(), _optional_date() (+14 more)

### Community 38 - "test_logging_setup.py"
Cohesion: 0.09
Nodes (37): BaseException, callback, Context, FileHandler, Logger, _root(), get_logger(), _is_control_flow_exit() (+29 more)

### Community 39 - "analyzer.py"
Cohesion: 0.13
Nodes (31): analyze(), _content_type(), decode_content(), _endpoint_key(), EndpointCandidate, _entries(), find_entries(), _is_sensitive_param() (+23 more)

### Community 40 - "Analyst"
Cohesion: 0.04
Nodes (44): Analyst, date, One line naming why AI output is missing, or empty when it isn't. Reasons…, LLM commentary over deterministic output. Never a source of numbers., Narrative for one symbol. Bulk tier — this runs once per symbol., The expensive weekly pass. Synthesis tier, and the only ``deep`` call. Cached…, Devil's advocate against the deterministic plan. Synthesis tier., _render() (+36 more)

### Community 41 - "add_trading_days"
Cohesion: 0.07
Nodes (26): add_trading_days(), _default_holidays(), _get_holidays(), is_trading_day(), load_holidays(), next_trading_day(), periods_per_year(), previous_trading_day() (+18 more)

### Community 42 - "LLMRouter"
Cohesion: 0.11
Nodes (16): build_provider(), LLMProvider, ABC, True when the provider is configured well enough to try. Checked without any…, Construct a provider by configuration name., Anything that can turn a prompt into text., The model this provider would use right now, for the ledger., LLMRouter (+8 more)

### Community 43 - "DailyPipeline"
Cohesion: 0.10
Nodes (24): rag_index(), Build the searchable document corpus from what's already in the database. Runs…, DailyPipeline, build_corpus(), index_documents(), Write pre-built documents (news, web pages) into the index., Index everything derivable for *symbols* into the document store. ``pipeline``…, pipe() (+16 more)

### Community 44 - "serve_stdio"
Cohesion: 0.33
Nodes (6): mcp_serve_cmd(), Serve the local, read-only MCP toolkit over stdio., build_server(), Construct a fully wired :class:`MCPServer`. Separate from :func:`serve_stdio`…, Serve MCP over newline-delimited JSON-RPC until stdin closes. Blocks. Returns…, serve_stdio()

### Community 45 - "_budget"
Cohesion: 0.10
Nodes (12): _budget(), _ok(), The estimate exists so an overrun is prevented, not just detected., The weekly cap rations successful theses, not failed attempts., A provider stuck in a failure loop must still burn its call allowance., _settings(), TestCallCap, TestDeepPassCap (+4 more)

### Community 47 - "types.ts"
Cohesion: 0.08
Nodes (35): fetchJson(), postJson(), AiCacheStats, AiProviderLeg, BacktestRun, BacktestSummary, BulkSignalRow, Confidence (+27 more)

### Community 48 - "pipeline.py"
Cohesion: 0.11
Nodes (32): best_per_symbol(), Any, Backtest screening: rank strategies across symbols. Runs a panel of strategies…, Collapse a leaderboard to the single best strategy per symbol., Backtest every (symbol, strategy) pair and return a ranked leaderboard.…, screen(), ScreenRow, _strategies() (+24 more)

### Community 49 - "get"
Cohesion: 0.10
Nodes (34): get, HTTPException, advisor_latest(), advisor_run(), backtest_run(), backtest_screen(), bulk_signals(), bulk_stats() (+26 more)

### Community 50 - "CostEngine"
Cohesion: 0.14
Nodes (27): CostEngine, PaperPortfolio, An in-memory paper-trading account with realistic Nepal costs., engine(), fixture, parametrize, Tests for the paper-trading portfolio ledger (no network). These exercise the…, Duck-typed storage stub capturing persisted trades. (+19 more)

### Community 51 - "auction.py"
Cohesion: 0.10
Nodes (32): _advice_id(), advise_auction(), advise_from_plan(), _as_date(), auction_advice_history(), AuctionAdvice, _break_even_bid(), _break_even_exit_price() (+24 more)

### Community 52 - "test_mcp_protocol.py"
Cohesion: 0.09
Nodes (36): parse_message(), Exception, JSON-RPC 2.0 framing and dispatch for the MCP server — transport-agnostic. This…, A protocol-level failure that must surface as a JSON-RPC ``error``. Method…, A parsed, structurally valid JSON-RPC request or notification., Parse one line of JSON into a :class:`Request`. Raises :class:`RpcError` with…, Request, RpcError (+28 more)

### Community 53 - "test_meroshare.py"
Cohesion: 0.06
Nodes (50): :func:`redact`, plus every account identifier on this instance., demat_fingerprint(), demat_last4(), _normalise(), Privacy-safe identifiers for persisted MeroShare mirror rows. The CDSC…, Return a deterministic, non-reversible storage key for a demat value., Return only the final four characters for masked display., _client_failure_message() (+42 more)

### Community 54 - "MeroShareCredentials"
Cohesion: 0.07
Nodes (21): connection_disclosure(), Client, Exactly what will be sent where, for the CLI to show before connecting.…, keyring_available(), MeroShareCredentials, _password_from_keyring(), MeroShare credential resolution — and every path a secret could escape by. The…, Which fields are empty, by name — safe to show the user. (+13 more)

### Community 55 - "CorporateAction"
Cohesion: 0.18
Nodes (23): adjust_prices(), _consensus(), Cross-source reconciliation. The whole point of pulling the same NEPSE data…, Back-adjust reconciled closes by corporate action factors. For each symbol,…, Return (agreed_value, agreeing_sources, disputed). Greedy clustering: for each…, _within(), CorporateAction, A corporate event that adjusts historical prices. (+15 more)

### Community 56 - "Plan: Web UI Dashboard"
Cohesion: 0.06
Nodes (32): Overview, Plan: Web UI Dashboard, Potential Risks & Gotchas, Prerequisites, Rollback Plan, Sprint 1: Backend API, Sprint 2: Frontend Foundation, Sprint 3: Dashboard + Symbols Page (+24 more)

### Community 57 - "test_web_operations.py"
Cohesion: 0.21
Nodes (10): _bars(), client(), fixture, ReconciledPrice, The background job engine and the operations endpoints it drives. Two halves.…, A temp database with one symbol's history, plus matching Settings., A TestClient over the seeded database, with a clean job registry., _reconciled() (+2 more)

### Community 58 - "App.tsx"
Cohesion: 0.07
Nodes (51): react, AiBudget, AiModelsResponse, AiTestResult, BulkSignalsResponse, BulkStatsResponse, HoldingComparison, JournalEntry (+43 more)

### Community 59 - ".daily_report"
Cohesion: 0.10
Nodes (12): Any, date, ReconciledPrice, Async variant: fetches from all sources concurrently., Call a client fetch method, isolating its failure to that data type., Reconciled history for a symbol as PriceBars (for indicators)., Rebuild the paper portfolio by replaying stored trades (no re-persist)., Advancers/decliners/turnover/reconcile-quality for a date. (+4 more)

### Community 60 - "backtest.py"
Cohesion: 0.10
Nodes (15): Long-only, event-driven backtester with the full Nepal cost model. The engine…, exposure_pct(), Risk-managed position sizing, stop-loss, and exposure controls. All functions…, Compute the quantity to buy using fixed-fractional position sizing. Two sizing…, Compute the stop-loss price for a long position. Uses ATR-based or percentage-…, Compute the take-profit price for a long position., Return the fraction of equity deployed in a position (0–100)., size_position() (+7 more)

### Community 61 - "Developers Guide — NEPSE Trader"
Cohesion: 0.08
Nodes (26): 10. Layer: costs and taxes, 11. Layer: paper trading, 12. Layer: RAG, 13. Layer: AI, 14. Layer: advisor, 15. Layer: MeroShare mirror, 16. Layer: health, 17. Surface: CLI (+18 more)

### Community 62 - ".parse_announcements"
Cohesion: 0.21
Nodes (5): Parse the announcements table into documents. Columns are ``S.No | Headline |…, date, parametrize, No known-symbol set needed here — the table states the symbol., TestParseAnnouncements

### Community 63 - "_run"
Cohesion: 0.04
Nodes (49): latest_run(), Rashifal, Describe the tape in one phrase, from advancers vs decliners., Persist a run and its cards; returns the run id. Stored so a call can be scored…, A held position the engine wants out of, and why., The most recent run with its cards, or None if the advisor never ran., Recent runs, newest first, without their cards., One advisor run: the whole daily prescription. (+41 more)

### Community 64 - "_settings"
Cohesion: 0.11
Nodes (12): MonkeyPatch, parametrize, Tests for the runtime Settings model (modes, LLM, budget, RAG, MeroShare).…, Build Settings without reading the developer's real .env., Bulk per-symbol work must not default to a paid provider., claude_cli runs under the user's subscription — no API billing., Env vars are strings; a CSV watchlist must still parse to a list., _settings() (+4 more)

### Community 65 - "main.py"
Cohesion: 0.04
Nodes (106): command, Render all four horizons as safe beginner-facing prose., render_doses(), _advisor_evidence(), _advisor_horizon(), _advisor_mode(), _advisor_positions(), _advisor_sections() (+98 more)

### Community 66 - "PriceBar"
Cohesion: 0.21
Nodes (10): _clamp01(), _clean_indicators(), Signal, Clamp ``x`` into [0, 1] (Signal.strength is validated ``0 <= s <= 1``)., Drop None entries; Signal.indicators is ``dict[str, float]``., Return signals for ``bars`` (chronological ascending)., Return (closes, has_close). ``closes`` carries the last valid close forward…, Convenience: the signal for the last day, or None if none produced. (+2 more)

### Community 67 - "fixtures.ts"
Cohesion: 0.05
Nodes (41): aiBudget, aiModels, aiTestOk, auctionAdvice, backtestRun, bulkSignals, bulkStats, confidence (+33 more)

### Community 68 - "nepse_trader/models.py"
Cohesion: 0.10
Nodes (15): _Base, CorporateActionType, FloorsheetEntry, MarketStatus, BaseModel, Enum, str, Core data contracts shared across ingestion, analysis, and trading. All… (+7 more)

### Community 69 - "test_pipeline.py"
Cohesion: 0.11
Nodes (16): asyncio, Integration tests for the daily pipeline (no network)., A fake source that returns canned bars — exercises ingest without network., Async ingest should produce the same result as sync., _seed_hump(), _StubSource, test_async_ingest_matches_sync(), test_build_clients_include_all_scrapes_every_source() (+8 more)

### Community 70 - "rashifal_md"
Cohesion: 0.28
Nodes (4): rashifal_md(), Render a whole advisor run as Markdown. *result* is ``Rashifal.as_dict()``.…, _rashifal(), TestRashifalMd

### Community 71 - "Make It Even Better — Engineering Quality Upgrades"
Cohesion: 0.08
Nodes (24): 1.1 Use `Decimal` for money — **high impact**, 1.2 Property-based tests (Hypothesis) — **high impact, low effort**, 1.3 Golden-file tests for parsers — **medium**, 1. Correctness & financial precision, 2.1 CI pipeline — **high impact, low effort**, `.github/workflows/ci.yml`, 2.2 Static typing in CI — **medium**, 2.3 Coverage measurement — **low**, 2.4 Pre-commit hooks — **low** (+16 more)

### Community 72 - "SmaCrossStrategy"
Cohesion: 0.14
Nodes (13): PortfolioBacktester, PortfolioResult, date, Multi-symbol portfolio backtester with equal-weight capital allocation., Aggregate performance of a multi-symbol portfolio., Run a strategy across multiple symbols with equal capital allocation., Run *strategy* on each symbol and aggregate results. *symbol_bars* maps symbol…, Fast/slow simple-moving-average crossover. (+5 more)

### Community 73 - "validate_yaml"
Cohesion: 0.18
Nodes (14): Any, Path, Config file validation using JSON Schema. Provides validation functions for the…, Validate a single YAML file against its JSON Schema. Returns a (possibly empty)…, Validate all config files. Returns list of error messages (empty = OK)., _validate(), validate_all(), validate_yaml() (+6 more)

### Community 74 - "Position"
Cohesion: 0.20
Nodes (3): Position, Decimal, field_validator

### Community 75 - "htmlparse.py"
Cohesion: 0.15
Nodes (22): has_header(), Row, Resilient HTML table extraction with a pluggable backend. Two backends produce…, Return the Scrapling Selector class, or None if unavailable., Resolve the effective parse engine name ('scrapling' or 'selectolax')., Return rows of (tag, text) cell tuples for the first table matching…, The text of the ``<td>`` cells in a row (ignoring header ``<th>`` cells)., resolve_engine() (+14 more)

### Community 76 - "compilerOptions"
Cohesion: 0.08
Nodes (23): DOM, src, vite/client, compilerOptions, allowArbitraryExtensions, allowImportingTsExtensions, erasableSyntaxOnly, jsx (+15 more)

### Community 77 - "system_health"
Cohesion: 0.18
Nodes (12): Connection, Every check, in a stable order, plus the worst-wins overall verdict. *storage*…, Persist *report* and return its row id. Called only when a caller explicitly…, Recent snapshots, newest first, without their full JSON payload. The payload is…, One stored report in full, or None when that id was never recorded., record_snapshot(), snapshot(), snapshot_history() (+4 more)

### Community 78 - "Document"
Cohesion: 0.13
Nodes (18): _breadth_documents(), _corporate_action_documents(), _documents_for_symbol(), _flush(), IndexReport, _periods(), Corpus construction: walk the database, emit documents, write the index.…, What an indexing run produced. (+10 more)

### Community 79 - "AccountVault"
Cohesion: 0.18
Nodes (7): AccountVault, BankAccount, _money(), Decimal, Holds the sensitive, encapsulated account state. All money is stored as Decimal…, Accept Decimal / int / str. Refuse float (binary rounding errors)., The public-facing account that performs operations on a vault.

### Community 80 - "Retriever"
Cohesion: 0.15
Nodes (8): date, Search the web and return fetched pages as hits. ``kinds`` and ``since`` are…, Result URLs from the configured search endpoint, best first., Short stable id for a URL, so re-fetching the same page upserts., Anything that can turn a query into ranked hits., Retriever, _url_key(), Protocol

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
Cohesion: 0.12
Nodes (12): MethodHandler, Dispatcher, error_response(), Any, Routes JSON-RPC methods to registered handlers. Deliberately a plain name →…, Dispatch a parsed request. Returns ``None`` for notifications., Parse and dispatch one wire line. Never raises. Returns the response dict to…, One MCP tool: what the model sees, and what runs when it is called.… (+4 more)

### Community 85 - "corpus.py"
Cohesion: 0.07
Nodes (33): Fetch and parse fundamentals for *symbol*., FundamentalData, breadth_document(), _doc_id(), _fmt(), fundamental_document(), iter_documents(), price_document() (+25 more)

### Community 86 - "FetchResult"
Cohesion: 0.25
Nodes (5): FetchResult, _HostThrottle, Any, Enforces a minimum wall-clock gap between requests to each host., retry

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
Nodes (17): jsdom, tailwindcss, @testing-library/jest-dom, @testing-library/react, @testing-library/user-event, @types/node, @types/react-router-dom, @vitest/coverage-v8 (+9 more)

### Community 91 - "test_backtest_risk.py"
Cohesion: 0.33
Nodes (6): _bar(), _buy_sig(), _DummyStrategy, Signal, Tests for risk-managed stop-loss / take-profit in the event-driven backtester., TestStopLossInBacktest

### Community 92 - "build_rashifal"
Cohesion: 0.11
Nodes (17): _attach_narrative(), build_rashifal(), build_sell_queue(), _note_text(), date, PlanCard, Which held positions to exit, from the engine's own view of each symbol.…, Compose a full run. Deterministic unless *analyst* is supplied. ``mode="ai"``… (+9 more)

### Community 93 - "Any"
Cohesion: 0.21
Nodes (5): JobStage, Any, Newest first, without log bodies — this is the index, not the detail., Start *kind* in a worker thread and return its job immediately. Raises…, One named step of a job, with an optional item counter. ``current``/``total``…

### Community 94 - "walkforward.py"
Cohesion: 0.21
Nodes (12): _param_grid(), Any, Walk-forward optimisation with expanding or rolling windows. Splits price…, walk_forward(), WFOFold, WFResult, _bars(), Tests for walk-forward optimisation. (+4 more)

### Community 95 - "signals_markdown"
Cohesion: 0.18
Nodes (14): Path, Write a combined daily report with a top title and one ``##`` per section., Build a GitHub markdown table of signals (pure, exact-text testable)., signals_markdown(), write_markdown_report(), parametrize, _signal(), test_signals_markdown_empty() (+6 more)

### Community 96 - "MeroLaganiFundamentalsClient"
Cohesion: 0.08
Nodes (32): MeroLaganiFundamentalsClient, Fundamentals data scraping from MeroLagani company detail pages., Fetch fundamental data for a single symbol from MeroLagani., AdvisorRunRequest, AiTestRequest, AuctionAdviceRequest, CorporateActionRequest, JobSubmitRequest (+24 more)

### Community 97 - "TestCitations"
Cohesion: 0.27
Nodes (4): normalise_citations(), Coerce whatever the model wrote into ``["[E1]", "[E3]"]`` form. Models write…, A marker only means something if it can match an evidence item., TestCitations

### Community 98 - "_advisor_run_response"
Cohesion: 0.21
Nodes (17): advisor_doses_latest(), _advisor_run_response(), _attach_dose_cards(), _confidence_response(), _dose_response(), _dose_run_response(), _plan_card_response(), Any (+9 more)

### Community 99 - "conftest.py"
Cohesion: 0.14
Nodes (14): Config, Session, _isolate_run_logs(), fixture, Path, pytest_configure(), pytest_runtest_logreport(), pytest_sessionfinish() (+6 more)

### Community 100 - "post"
Cohesion: 0.11
Nodes (20): ai_test(), cancel_job(), journal_distill_endpoint(), _journal_error(), journal_retire_endpoint(), journal_review_endpoint(), meroshare_import(), ValueError (+12 more)

### Community 101 - "_settings"
Cohesion: 0.07
Nodes (37): _advisor_symbols(), ai_budget(), ai_models(), _ensure_app_settings(), _evidence_builder(), get_meroshare_setting(), get_watchlist(), health_report() (+29 more)

### Community 102 - "progress_spinner"
Cohesion: 0.11
Nodes (21): ai_budget(), ai_models(), ai_test(), A router over the real database. Opens the DB; caller keeps the Storage., Show each provider chain and which legs are actually usable., Today's LLM spend against the caps, plus cache size., Send one tiny prompt through a chain and report what answered. This spends real…, Quantitative statistics per symbol over reconciled history. Annualised return &… (+13 more)

### Community 103 - "NEPSE Trader — Agent Context"
Cohesion: 0.13
Nodes (14): Completed advisor scope, Current State, Key Design Decisions, NEPSE Trader — Agent Context, Open Questions / Planned, Project, Project Structure, Recent Sprint Progress (+6 more)

### Community 104 - "test_ingest_news.py"
Cohesion: 0.24
Nodes (5): extract_symbols(), Symbols mentioned in *text*, in first-seen order. Without a ``known_symbols``…, Tests for news + announcement ingestion. Two things carry this module and are…, No known-symbol set means no tagging — mistagging is worse than nothing., TestExtractSymbols

### Community 105 - "TestDatabaseAndFreshness"
Cohesion: 0.19
Nodes (8): check_database(), check_ingest(), The database exists, is readable, and holds price rows., The error rate over the most recent ingest attempts, per source., date, _seed_prices(), TestDatabaseAndFreshness, TestIngest

### Community 106 - "NewsClient"
Cohesion: 0.39
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

### Community 114 - "check_rag"
Cohesion: 0.33
Nodes (5): check_rag(), Corpus size, per-kind coverage, and whether ranked search is available., has_fts5(), Probe whether this SQLite build has the FTS5 extension compiled in. FTS5 ships…, TestRag

### Community 115 - "test_sharesansar.py"
Cohesion: 0.06
Nodes (50): _int(), _num(), parse_as_of_date(), _parse_date(), _parse_datetime(), date, Extract plain text from a value that may be an HTML anchor. ShareSansar's JSON…, Parse a possibly comma-grouped numeric cell to ``float`` (or ``None``). Handles… (+42 more)

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

### Community 121 - "Capabilities — NEPSE Trader"
Cohesion: 0.18
Nodes (11): 10. Performance characteristics, 1. Capability matrix, 2. Data & coverage, 3. Analytical capabilities, 4. Backtesting & screening, 5. Cost & tax fidelity, 6. The once-a-day report, 7. Advisor, mirror and MCP details (+3 more)

### Community 122 - "health.py"
Cohesion: 0.13
Nodes (19): Check, check_freshness(), check_journal(), check_paper(), _guarded(), problems(), Any, date (+11 more)

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

### Community 127 - "ReconciledPrice"
Cohesion: 0.20
Nodes (10): A price for a symbol/date agreed (or disputed) across multiple sources., ReconciledPrice, ReconciledPrice, Markdown table of reconciled prices, flagging low-confidence / disputed rows., reconciliation_report(), test_reconciliation_report_empty(), test_reconciliation_report_flags_disputed_even_if_confident(), test_reconciliation_report_flags_low_confidence() (+2 more)

### Community 128 - "_client"
Cohesion: 0.46
Nodes (4): _client(), mock, A missing news leg costs commentary, never numbers — it must not raise., TestFetch

### Community 129 - "test_reporting.py"
Cohesion: 0.10
Nodes (25): Alerter, backtest_report(), portfolio_summary(), Markdown summary of cash, equity, PnL and current positions., Markdown summary of backtest performance metrics., Pluggable alert backends: Telegram, Discord, SMTP, and generic webhook. Every…, Send a plain-text message via Telegram Bot API., Send a message to a Discord channel via webhook. (+17 more)

### Community 131 - "Per-site capture recipes"
Cohesion: 0.22
Nodes (9): 1. ShareSansar — `sharesansar.har` (PRIMARY), 2. Chukul — `chukul.har` (verify inferred /v1/ paths), 3. MeroLagani — `merolagani.har` (secondary HTML), 4. NepseAlpha — `nepsealpha.har` (TradingView UDF, Cloudflare-gated), 5. NEPSE official — `nepse_official.har` (reference / replay only), HAR Capture Plan — NEPSE data sources, How to capture a HAR (Chrome / Firefox / Edge), Per-site capture recipes (+1 more)

### Community 132 - "Job"
Cohesion: 0.22
Nodes (4): Job, A unit of background work and everything the UI needs to render it., Ask a job to stop. Returns the job, or None when the id is unknown. Cancelling…, RLock

### Community 133 - "plugins"
Cohesion: 0.22
Nodes (8): oxc, typescript, warn, plugins, rules, react/only-export-components, react/rules-of-hooks, $schema

### Community 134 - "SourceClient"
Cohesion: 0.33
Nodes (4): date, Interface every source adapter implements. Concrete clients (ShareSansar,…, SourceClient, Ingestion subpackage: per-source clients that fetch PUBLIC market data.

### Community 135 - "TestExtractResultLinks"
Cohesion: 0.27
Nodes (5): extract_result_links(), Pull outbound result URLs from a search results page. DuckDuckGo's HTML…, Turn a search-engine redirect link into the destination URL., _unwrap_redirect(), TestExtractResultLinks

### Community 136 - "scripts"
Cohesion: 0.25
Nodes (8): scripts, build, coverage, dev, lint, preview, test, test:run

### Community 137 - "NEPSE risk & position sizing — project skill"
Cohesion: 0.29
Nodes (6): Ask the engine for exact costs (don't approximate), Fit-check an existing paper portfolio, Hard rules, Nepal mechanics you MUST respect, NEPSE risk & position sizing — project skill, Sizing protocol (fixed-fractional, R-based)

### Community 138 - "client.py"
Cohesion: 0.09
Nodes (31): _as_date(), _as_float(), _as_int(), ConnectionResult, ensure_enabled(), _first(), MeroShareDisabledError, MeroShareError (+23 more)

### Community 139 - "test_health.py"
Cohesion: 0.28
Nodes (6): check_config(), YAML config parses against its schema, and at least one source is on., fixture, Health-report tests: every verdict, the guard, and the snapshot history. Fully…, storage(), TestConfig

### Community 140 - "TestSectorOfTheDay"
Cohesion: 0.39
Nodes (3): The sector with the best mean change today. Takes an already-grouped mapping so…, _sector_of_the_day(), TestSectorOfTheDay

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

### Community 147 - "check_ai"
Cohesion: 0.43
Nodes (3): check_ai(), Whether AI mode could actually answer, and how much budget is left. Reads the…, TestAi

### Community 148 - "React + TypeScript + Vite"
Cohesion: 0.50
Nodes (3): Expanding the Oxlint configuration, React Compiler, React + TypeScript + Vite

### Community 149 - "Health.tsx"
Cohesion: 0.22
Nodes (9): HealthCheck, HealthReport, HealthSnapshot, HealthStatus, BADGE_VARIANT, CheckRow(), ICONS, metricRows() (+1 more)

### Community 158 - "HoldingDiff"
Cohesion: 0.29
Nodes (4): HoldingDiff, One symbol's disagreement (or agreement) between real and paper books., Real minus paper. Positive means the real account holds more., ``"real"``, ``"paper"``, or ``None`` when both hold the symbol.

### Community 170 - "TestDeterministicIds"
Cohesion: 0.29
Nodes (3): Daily re-ingestion must upsert, not accumulate., Sites reflow capitalisation; that must not spawn a duplicate document., TestDeterministicIds

### Community 171 - "3. Robustness & resilience"
Cohesion: 0.40
Nodes (5): 3.1 Async, concurrent ingestion — **high impact**, `ingest/base.py`, 3.2 Per-source circuit breaker — **medium**, 3.3 Respect `Retry-After` and `robots.txt` programmatically — **medium**, 3.4 Schema-driven HTML parsing — **medium**, `ingest/sharesansar.py`, `merolagani.py`, 3. Robustness & resilience

### Community 174 - "._split_csv"
Cohesion: 0.40
Nodes (3): Any, field_validator, Accept a comma-separated string from env for list-valued settings.

### Community 177 - "._post"
Cohesion: 0.40
Nodes (3): Response, Thin POST wrapper kept separate so tests can monkeypatch it., POST the alert if a webhook is set; return success. No webhook -> False, no…

### Community 178 - "check_schema"
Cohesion: 0.43
Nodes (3): check_schema(), Every migration in the registry applied, and nothing unknown applied., TestSchema

### Community 180 - "plan_cards_md"
Cohesion: 0.38
Nodes (4): plan_cards_md(), Render plan cards as one table row per symbol. Cards are…, _card(), TestPlanCardsMd

### Community 181 - "TestHtmlToText"
Cohesion: 0.36
Nodes (3): html_to_text(), Reduce a page to ``(title, body_text)``, truncated to ``max_chars``. Script,…, TestHtmlToText

### Community 182 - "_drive"
Cohesion: 0.33
Nodes (6): _drive(), Run serve_stdio over StringIO. Returns (responses, raw stdout text)., With explicit streams the loop must leave sys.stdout untouched., test_end_to_end_initialize_list_and_call_over_the_stdio_loop(), test_serve_stdio_does_not_leak_the_real_stdout_rebinding(), test_stdio_loop_returns_cleanly_on_eof()

### Community 183 - "_seed"
Cohesion: 0.40
Nodes (5): fixture, Write both raw and reconciled bars: tools read from each side., _seed(), server(), storage()

### Community 184 - "save_auction_advice"
Cohesion: 0.50
Nodes (4): Persist one manual auction recommendation using parameterized SQL. The caller…, save_auction_advice(), auction_advice_endpoint(), Calculate and persist a manual auction bid ceiling.

### Community 185 - "_StdioStreams"
Cohesion: 0.50
Nodes (4): Resolved I/O plus whether we own (and may therefore guard) real stdout., _resolve_streams(), _StdioStreams, TextIO

### Community 189 - "do_not_touch_md"
Cohesion: 0.50
Nodes (3): do_not_touch_md(), Render the excluded symbols with their reasons. A symbol missing from the…, TestDoNotTouchMd

### Community 190 - "sell_queue_md"
Cohesion: 0.50
Nodes (3): Render the exit queue: what to sell, why, and the earliest legal date., sell_queue_md(), TestSellQueueMd

### Community 208 - "_to_money"
Cohesion: 0.11
Nodes (16): CostBreakdown, Decimal, Nepal equity transaction cost & tax engine. Computes the full, realistic cost…, Convert a number to paisa-precise Decimal (2 dp, half-up)., _to_money(), OrderSide, PaperTrade, An executed paper trade with full Nepal cost breakdown. (+8 more)

### Community 210 - "TokenBudget"
Cohesion: 0.06
Nodes (30): The analyst: evidence in, validated commentary out. One class tying the pieces…, BudgetStatus, BudgetSummary, iso_week(), Connection, date, Token budgeting: hard ceilings with a DB-backed ledger. Three caps, all from…, Spend accounting over the ``ai_budget_ledger`` table. (+22 more)

### Community 211 - "conn"
Cohesion: 0.67
Nodes (3): conn(), fixture, Path

## Knowledge Gaps
- **401 isolated node(s):** `nepse-trader`, `$schema`, `typescript`, `oxc`, `react/rules-of-hooks` (+396 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **26 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Settings` connect `Settings` to `_settings`, `_router`, `_client`, `meroshare/__init__.py`, `Job`, `LLMResponse`, `SourceClient`, `TestExtractResultLinks`, `client.py`, `test_health.py`, `ResponseCache`, `parse_into`, `check_meroshare`, `MeroShareHolding`, `test_mcp_server.py`, `check_ai`, `jobs.py`, `WebRetriever`, `MeroShareClient`, `JobRegistry`, `BaseClient`, `server.py`, `Analyst`, `LLMRouter`, `DailyPipeline`, `serve_stdio`, `_budget`, `._split_csv`, `TestAdvisor`, `pipeline.py`, `TestDeterministicIds`, `check_schema`, `TestJournalLifecycleAPI`, `TestAiRoutes`, `test_meroshare.py`, `MeroShareCredentials`, `_drive`, `_seed`, `_StdioStreams`, `TestHtmlToText`, `test_web_operations.py`, `.parse_announcements`, `_run`, `_settings`, `main.py`, `TestMeroShareImport`, `system_health`, `Retriever`, `TokenBudget`, `api.py`, `Dispatcher`, `FetchResult`, `Any`, `MeroLaganiFundamentalsClient`, `TestCitations`, `TestBulkAnalytics`, `TestPaperTrades`, `test_ingest_news.py`, `TestDatabaseAndFreshness`, `.parse_news_list`, `TestRagSearch`, `TestJobRoutes`, `check_rag`, `TestCorporateActions`, `TestTableBrowser`, `health.py`?**
  _High betweenness centrality (0.159) - this node is a cross-community bridge._
- **Why does `Storage` connect `Storage` to `_router`, `Job`, `LLMResponse`, `test_health.py`, `TestSectorOfTheDay`, `ResponseCache`, `MeroShareHolding`, `test_mcp_server.py`, `jobs.py`, `doses.py`, `advisor/__init__.py`, `ChukulClient`, `JobRegistry`, `migrations.py`, `server.py`, `DailyPipeline`, `serve_stdio`, `TestBulkAnalytics`, `pipeline.py`, `test_meroshare.py`, `CorporateAction`, `_seed`, `test_web_operations.py`, `_run`, `main.py`, `nepse_trader/models.py`, `test_pipeline.py`, `_to_money`, `TokenBudget`, `api.py`, `Dispatcher`, `conn`, `build_rashifal`, `progress_spinner`, `test_cli_advisor.py`, `ReconciledPrice`?**
  _High betweenness centrality (0.063) - this node is a cross-community bridge._
- **Why does `PriceBar` connect `PriceBar` to `test_reporting.py`, `indicator_document`, `reporting.py`, `Storage`, `SourceClient`, `Settings`, `test_nepse_official.py`, `sharesansar.py`, `test_health.py`, `reconcile_bars`, `test_strategies.py`, `MeroShareHolding`, `test_mcp_server.py`, `test_properties.py`, `outcomes.py`, `Backtester`, `ChukulClient`, `build_plan_card`, `BaseClient`, `merolagani.py`, `DailyPipeline`, `pipeline.py`, `CorporateAction`, `_seed`, `test_web_operations.py`, `.daily_report`, `backtest.py`, `_run`, `nepse_trader/models.py`, `test_pipeline.py`, `SmaCrossStrategy`, `Position`, `corpus.py`, `test_backtest_risk.py`, `walkforward.py`, `TestDatabaseAndFreshness`, `test_sharesansar.py`, `test_cli_advisor.py`, `ReconciledPrice`?**
  _High betweenness centrality (0.057) - this node is a cross-community bridge._
- **Are the 169 inferred relationships involving `Settings` (e.g. with `Analyst` and `BudgetStatus`) actually correct?**
  _`Settings` has 169 INFERRED edges - model-reasoned connections that need verification._
- **Are the 13 inferred relationships involving `Storage` (e.g. with `_Result` and `DegradingAnalyst`) actually correct?**
  _`Storage` has 13 INFERRED edges - model-reasoned connections that need verification._
- **Are the 75 inferred relationships involving `Document` (e.g. with `JournalError` and `Prediction`) actually correct?**
  _`Document` has 75 INFERRED edges - model-reasoned connections that need verification._
- **Are the 54 inferred relationships involving `DocumentIndex` (e.g. with `JournalError` and `Prediction`) actually correct?**
  _`DocumentIndex` has 54 INFERRED edges - model-reasoned connections that need verification._