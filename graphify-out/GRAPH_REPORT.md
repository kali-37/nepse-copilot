# Graph Report - nepse-trader  (2026-08-24)

## Corpus Check
- 206 files · ~222,510 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 4561 nodes · 11170 edges · 202 communities (175 shown, 27 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 999 edges (avg confidence: 0.52)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `18f56e4f`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- _settings
- LLMProvider
- command
- corpus.py
- reporting.py
- Storage
- test_ai_analyst.py
- Document
- BaseClient
- test_nepse_official.py
- test_sharesansar.py
- build_evidence
- ResponseCache
- parse_into
- SymbolNote
- test_strategies.py
- test_api_phase6.py
- test_mcp_server.py
- ._search_fts
- nepse_trader/models.py
- quant.py
- doses.py
- advisor/__init__.py
- test_properties.py
- outcomes.py
- Backtester
- ChukulClient
- WebRetriever
- plan.py
- client.py
- system_health
- build_plan_card
- Plan: NEPSE Trader — Full Completion
- NepseAlphaClient
- migrations.py
- merolagani.py
- test_costs.py
- Any
- test_logging_setup.py
- analyzer.py
- Analyst
- is_trading_day
- CorporateAction
- DailyPipeline
- main.py
- LLMResponse
- TestAdvisor
- types.ts
- pipeline.py
- sync_payload
- CostEngine
- auction.py
- test_mcp_protocol.py
- sync.py
- test_meroshare.py
- test_advisor_doses.py
- Plan: Web UI Dashboard
- _Base
- App.tsx
- MeroShareHolding
- size_position
- Developers Guide — NEPSE Trader
- MeroShareClient
- _run
- _settings
- _safe_run
- PriceBar
- fixtures.ts
- _settings
- test_pipeline.py
- rashifal_md
- Make It Even Better — Engineering Quality Upgrades
- SmaCrossStrategy
- validate_yaml
- test_backtest_risk.py
- sharesansar.py
- compilerOptions
- health.py
- TestRagSearch
- AccountVault
- serve_stdio
- compilerOptions
- Tier 2 — strong analytical upside
- HTTPException
- protocol.py
- indicator_document
- .daily_report
- Dashboard.tsx
- renderWithProviders.tsx
- How It Works — NEPSE Trader Internals
- devDependencies
- TestPersistence
- SellCandidate
- Settings
- walkforward.py
- test_reporting.py
- SourceClient
- news.py
- get
- conftest.py
- check_freshness
- _storage
- _d
- NEPSE Trader — Agent Context
- test_advisor_rashifal.py
- check_schema
- TokenBudget
- test_web_api.py
- read_bool
- dependencies
- api.py
- NEPSE Trader — Operations Runbook
- How To Use — NEPSE Trader
- check_meroshare
- TestExtractResultLinks
- _ensure_app_settings
- test_cli_advisor.py
- Auction.tsx
- Rashifal.tsx
- 22. Recipes
- check_ingest
- Capabilities — NEPSE Trader
- rashifal.py
- NEPSE Trader
- test_cli.py
- NEPSE Trader — project skill
- credentials.py
- build.py
- _to_money
- Alerter
- Per-site capture recipes
- SearchHit
- plugins
- TestCardNumbers
- FakeAnalyst
- scripts
- NEPSE risk & position sizing — project skill
- add_trading_days
- test_rag_corpus.py
- test_health.py
- TestSectorOfTheDay
- NEPSE backtest protocol — project skill
- PlanCard
- 23. All the settings
- package.json
- check_ai
- test_advisor_plan.py
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
- LLMRouter
- @tailwindcss/vite
- @types/react
- @types/react-dom
- typescript
- vite
- @vitejs/plugin-react
- vitest
- nepse-trader
- reconcile_bars
- 3. Robustness & resilience
- @types/node
- Any
- Path
- TestDegradation
- Rashifal
- BaseModel
- ai_budget
- progress_bars
- plan_cards_md
- HoldingDiff
- ReconciledPrice
- TestExpectedOutcome
- test_storage.py
- _drive
- TestMeroShareImport
- FundamentalData
- TestNoNetworkAndNoLLM
- do_not_touch_md
- sell_queue_md
- _m0006_meroshare
- test_list_returning_tools_report_how_much_they_returned
- card
- _seed
- ._upper_symbol
- conn
- conn
- Path
- BaseModel
- ValueError
- fixture

## God Nodes (most connected - your core abstractions)
1. `Settings` - 196 edges
2. `PriceBar` - 130 edges
3. `Document` - 125 edges
4. `LLMResponse` - 110 edges
5. `CostEngine` - 104 edges
6. `DocumentIndex` - 104 edges
7. `Storage` - 95 edges
8. `BaseClient` - 89 edges
9. `TokenBudget` - 71 edges
10. `SourceName` - 62 edges

## Surprising Connections (you probably didn't know these)
- `test_constants_and_card_partition_are_exact()` --calls--> `partition_cards()`  [EXTRACTED]
  tests/test_advisor_doses.py → nepse_trader/advisor/doses.py
- `test_invalid_allocations_are_rejected()` --calls--> `build_dose_run()`  [EXTRACTED]
  tests/test_advisor_doses.py → nepse_trader/advisor/doses.py
- `TestAsDict` --uses--> `Skipped`  [INFERRED]
  tests/test_advisor_plan.py → nepse_trader/advisor/plan.py
- `TestCardNumbers` --uses--> `Skipped`  [INFERRED]
  tests/test_advisor_plan.py → nepse_trader/advisor/plan.py
- `TestDecide` --uses--> `Skipped`  [INFERRED]
  tests/test_advisor_plan.py → nepse_trader/advisor/plan.py

## Import Cycles
- None detected.

## Communities (202 total, 27 thin omitted)

### Community 0 - "_settings"
Cohesion: 0.05
Nodes (38): _anthropic_text(), AnthropicProvider, ClaudeCliProvider, estimate_tokens(), NullProvider, _openrouter_text(), OpenRouterProvider, The local Claude Code CLI, driven as a subprocess. The prompt goes in on… (+30 more)

### Community 1 - "LLMProvider"
Cohesion: 0.05
Nodes (37): LLMProvider, True when the provider is configured well enough to try. Checked without any…, Anything that can turn a prompt into text., The model this provider would use right now, for the ledger., ExplodingProvider, FakeProvider, _ok(), _prime_cache() (+29 more)

### Community 2 - "command"
Cohesion: 0.07
Nodes (43): command, auction_list_cmd(), ca_add(), ca_list(), dashboard(), export_csv_cmd(), export_parquet_cmd(), fund_show() (+35 more)

### Community 3 - "corpus.py"
Cohesion: 0.11
Nodes (19): A strategy's decision for a symbol on a date., Signal, breadth_document(), _doc_id(), _fmt(), fundamental_document(), date, Signal (+11 more)

### Community 4 - "reporting.py"
Cohesion: 0.11
Nodes (26): _fmt_num(), leaderboard_md(), market_overview_md(), _md_escape(), movers_md(), portfolio_summary(), price_bars_markdown(), print_signals() (+18 more)

### Community 5 - "Storage"
Cohesion: 0.14
Nodes (15): export_csv(), export_parquet(), Path, Row, Storage, conn(), fixture, Path (+7 more)

### Community 6 - "test_ai_analyst.py"
Cohesion: 0.09
Nodes (18): _analyst(), _FakeRouter, date, Tests for the analyst and the schemas that guard its output. Two contracts are…, Only the surface ``Analyst`` actually touches: ``complete`` and…, One pass per symbol times twenty-five symbols — free models, not synthesis., One failure, one degradation — not "no response" plus "failed validation"., ``deep`` is what the weekly cap counts; it must reach the router. (+10 more)

### Community 7 - "Document"
Cohesion: 0.07
Nodes (17): Document, One retrievable fact or article., Positional tuple matching the ``documents`` table column order., DocumentIndex, Connection, Remove every document of one kind (used when rebuilding a slice)., Document count per kind — what the corpus actually holds., Read/write access to the document corpus and its search index. (+9 more)

### Community 8 - "BaseClient"
Cohesion: 0.06
Nodes (50): BaseClient, FetchError, FetchResult, _HostThrottle, Any, Client, Exception, RateLimitedError (+42 more)

### Community 9 - "test_nepse_official.py"
Cohesion: 0.07
Nodes (53): decode_content(), _extract_records(), find_entries(), _first(), HarReplayClient, is_available(), load_har(), _looks_sharesansar() (+45 more)

### Community 10 - "test_sharesansar.py"
Cohesion: 0.05
Nodes (57): EndpointSpec, load_cost_model(), load_sources(), Path, _read_yaml(), SourcesConfig, SourceSpec, _int() (+49 more)

### Community 11 - "build_evidence"
Cohesion: 0.08
Nodes (26): build_evidence(), EvidencePack, A compact source list for the human-facing report., Pack hits into an :class:`EvidencePack` under both ceilings. ``max_documents``…, A size-bounded, ordered, citable set of documents., Distinct symbols appearing in the evidence, in first-seen order., ``{"[E1]": "price:NABIL:2026-08-20", ...}`` — for auditing an answer., The block to embed in a prompt. (+18 more)

### Community 12 - "ResponseCache"
Cohesion: 0.07
Nodes (27): cache_key(), Delete entries past the TTL. Returns how many went., Size and age of the cache, for ``ai budget``., Stable key for a request's content. The parts are joined with a separator that…, SQLite-backed cache over the ``ai_cache`` table., A fresh cached response, or None on a miss or an expired entry., Store a successful response. Returns whether it was written. Failures are never…, ResponseCache (+19 more)

### Community 13 - "parse_into"
Cohesion: 0.07
Nodes (22): parse_into(), T, Parse *text* into *model*, or return None and log why. ``defaults`` fill fields…, _critique_json(), _note_json(), parametrize, The contract: a failed pass costs narrative, never an exception., Some models wrap the single answer in a list. (+14 more)

### Community 14 - "SymbolNote"
Cohesion: 0.06
Nodes (29): critique_prompt(), Prompt templates as plain strings. Kept out of the modules that use them for…, symbol_note_prompt(), weekly_thesis_prompt(), _Base, _clean(), _clean_list(), Critique (+21 more)

### Community 15 - "test_strategies.py"
Cohesion: 0.07
Nodes (50): BollingerStrategy, build_strategy(), CompositeStrategy, DonchianStrategy, IchimokuStrategy, MacdStrategy, MeanReversionStrategy, ABC (+42 more)

### Community 16 - "test_api_phase6.py"
Cohesion: 0.05
Nodes (23): _bars(), client(), empty_client(), _make_client(), _meroshare_client(), fixture, ReconciledPrice, Phase 6 endpoints: RAG search, AI budget, news, watchlist, advisor, MeroShare.… (+15 more)

### Community 17 - "test_mcp_server.py"
Cohesion: 0.09
Nodes (39): _call(), _payload(), Server-layer tests: tool registry, tool call semantics, and the stdio loop.…, Invoke a tool through the dispatcher and return the raw MCP result., Parse the JSON a tool rendered into its single text content block., Guard the read-only contract against a future tool being added carelessly., _request(), test_a_raising_tool_returns_is_error_not_a_jsonrpc_error() (+31 more)

### Community 18 - "._search_fts"
Cohesion: 0.14
Nodes (14): _matched(), date, Row, Best-matching documents for *query*, most relevant first.…, Term-overlap ranking. Correct, just less clever than bm25., Newest documents matching the filters, ignoring relevance., Extract searchable words (Latin + Devanagari) from a raw query., Turn free text into a safe FTS5 MATCH expression. Terms are OR-ed with a prefix… (+6 more)

### Community 19 - "nepse_trader/models.py"
Cohesion: 0.21
Nodes (9): CorporateActionType, OrderSide, Enum, str, Core data contracts shared across ingestion, analysis, and trading. All…, SignalAction, SourceName, SQLite persistence for price bars, indices, floorsheet, signals and trades.… (+1 more)

### Community 20 - "quant.py"
Cohesion: 0.08
Nodes (45): annualized_return(), annualized_volatility(), beta(), correlation(), covariance(), kurtosis(), max_drawdown(), mean() (+37 more)

### Community 21 - "doses.py"
Cohesion: 0.10
Nodes (40): _add_sell_guidance(), build_dose_run(), build_doses(), _card_horizon(), _card_value(), _confidence_for_card(), _date(), _decimal() (+32 more)

### Community 22 - "advisor/__init__.py"
Cohesion: 0.11
Nodes (50): Public advisor API: deterministic plans, confidence, doses and review., _as_date(), _confidence(), confidence_for_prediction(), distill_lesson(), _fetch(), get_prediction(), journal_history() (+42 more)

### Community 23 - "test_properties.py"
Cohesion: 0.04
Nodes (80): given, _latest_atr(), Wilder ATR over the reconciled history, or None if it can't be computed., atr(), bollinger_bands(), chikou_span(), donchian_channel(), ema() (+72 more)

### Community 24 - "outcomes.py"
Cohesion: 0.10
Nodes (40): _date(), _is_short(), _number(), Outcome, OutcomeResult, persist_score(), _prediction_symbol(), Any (+32 more)

### Community 25 - "Backtester"
Cohesion: 0.10
Nodes (35): Backtester, BacktestResult, _max_drawdown(), date, Long-only, event-driven backtester with the full Nepal cost model. The engine…, Event-driven, long-only backtester over a single symbol's price bars., Replay ``bars`` for ``strategy`` and return a :class:`BacktestResult`. Bars are…, Apply slippage: buys fill higher, sells fill lower. (+27 more)

### Community 26 - "ChukulClient"
Cohesion: 0.08
Nodes (35): _as_records(), ChukulClient, _int(), _num(), _pick(), Any, date, Chukul JSON source adapter. Chukul (https://chukul.com) is powered by a… (+27 more)

### Community 27 - "WebRetriever"
Cohesion: 0.12
Nodes (24): build_retriever(), HybridRetriever, LocalRetriever, Lazily built so constructing a WebRetriever opens no connection., Local first, web only when the local result set is thin. ``min_local_hits`` is…, The right retriever for the current mode. Offline (or web disabled) gives a…, Retrieval from the local document index. Offline, always available., Live search + page fetch. Requires online mode and a fetch client. The search… (+16 more)

### Community 28 - "plan.py"
Cohesion: 0.09
Nodes (30): band_for(), blend(), certain(), Confidence, confidence_from_history(), ConfidenceError, market(), penalise() (+22 more)

### Community 29 - "client.py"
Cohesion: 0.09
Nodes (28): _as_date(), _as_float(), _as_int(), connect(), ensure_enabled(), _first(), MeroShareFetchError, OwnDetail (+20 more)

### Community 30 - "system_health"
Cohesion: 0.27
Nodes (7): Every check, in a stable order, plus the worst-wins overall verdict. *storage*…, Recent snapshots, newest first, without their full JSON payload. The payload is…, snapshot_history(), system_health(), _settings(), TestReport, TestSnapshots

### Community 31 - "build_plan_card"
Cohesion: 0.13
Nodes (15): build_plan_card(), Confidence, Build one symbol's card, or explain why it can't be built. *today* defaults to…, _bars(), date, Silently returning quantity 0 would print an unactionable card., Only ACCUMULATE needs a tradeable size — a hold is information either way., T+2 is *trading* days. Every case here is one a naive +2 gets wrong. (+7 more)

### Community 32 - "Plan: NEPSE Trader — Full Completion"
Cohesion: 0.05
Nodes (43): Overview, Plan: NEPSE Trader — Full Completion, Potential Risks & Gotchas (addressed), Prerequisites, Rollback Plan, Sprint 0: Engineering Foundation, Sprint 1: Tier 1 Features, Sprint 2: Analytical Upside (+35 more)

### Community 33 - "NepseAlphaClient"
Cohesion: 0.13
Nodes (10): NepseAlphaClient, Any, date, Fetch daily price bars for *symbol* from the UDF history endpoint. The endpoint…, NepseAlpha is supplementary and doesn't support whole-market fetch. Returns an…, Client for NepseAlpha's TradingView UDF datafeed., Parse TradingView UDF history JSON into PriceBar records. Expected payload…, mock (+2 more)

### Community 34 - "migrations.py"
Cohesion: 0.04
Nodes (57): FixtureRequest, The searchable document index: SQLite FTS5, with a LIKE fallback.…, Path, _applied_versions(), _create_version_table(), has_fts5(), _m0000_initial(), _m0001_corporate_actions() (+49 more)

### Community 35 - "merolagani.py"
Cohesion: 0.09
Nodes (32): HTMLParser, _build_column_map(), _cell_at(), _cell_text(), _data_rows(), _first_match(), _int(), MeroLaganiClient (+24 more)

### Community 36 - "test_costs.py"
Cohesion: 0.21
Nodes (16): CommissionSlab, CostModel, BaseModel, Nepal equity transaction cost + tax model. Values are tunable via YAML., _engine(), Tests for the Nepal cost & tax engine. The headline test reproduces the…, test_buy_breakdown_matches_worked_example(), test_cgt_boundary_exactly_365_days_is_short_term() (+8 more)

### Community 37 - "Any"
Cohesion: 0.11
Nodes (23): _hit_to_dict(), _holding_to_dict(), _json_text(), MCPServer, _normalise_symbols(), _optional_bool(), _optional_choice(), _optional_date() (+15 more)

### Community 38 - "test_logging_setup.py"
Cohesion: 0.10
Nodes (34): BaseException, FileHandler, Logger, get_logger(), _is_control_flow_exit(), log_path(), _make_handler(), datetime (+26 more)

### Community 39 - "analyzer.py"
Cohesion: 0.12
Nodes (33): analyze(), _content_type(), decode_content(), _endpoint_key(), EndpointCandidate, _entries(), find_entries(), _is_sensitive_param() (+25 more)

### Community 40 - "Analyst"
Cohesion: 0.10
Nodes (17): Analyst, date, One line naming why AI output is missing, or empty when it isn't. Reasons…, LLM commentary over deterministic output. Never a source of numbers., Narrative for one symbol. Bulk tier — this runs once per symbol., The expensive weekly pass. Synthesis tier, and the only ``deep`` call. Cached…, Devil's advocate against the deterministic plan. Synthesis tier., _render() (+9 more)

### Community 41 - "is_trading_day"
Cohesion: 0.10
Nodes (21): _default_holidays(), _get_holidays(), is_trading_day(), load_holidays(), next_trading_day(), periods_per_year(), previous_trading_day(), Any (+13 more)

### Community 42 - "CorporateAction"
Cohesion: 0.24
Nodes (19): adjust_prices(), Back-adjust reconciled closes by corporate action factors. For each symbol,…, CorporateAction, A corporate event that adjusts historical prices., _ca(), _price(), date, ReconciledPrice (+11 more)

### Community 43 - "DailyPipeline"
Cohesion: 0.11
Nodes (20): DailyPipeline, build_corpus(), index_documents(), Write pre-built documents (news, web pages) into the index., Index everything derivable for *symbols* into the document store. ``pipeline``…, _bars(), pipeline(), fixture (+12 more)

### Community 44 - "main.py"
Cohesion: 0.07
Nodes (36): callback, Context, _advisor_evidence(), _advisor_horizon(), _advisor_mode(), _advisor_sections(), backtest(), _build_advisor_result() (+28 more)

### Community 45 - "LLMResponse"
Cohesion: 0.09
Nodes (16): LLMResponse, What a provider returned — or why it didn't., True when there is usable text and no error., _budget(), _ok(), Tests for the token budget. The behaviour that matters is the **hard stop**:…, The estimate exists so an overrun is prevented, not just detected., The weekly cap rations successful theses, not failed attempts. (+8 more)

### Community 47 - "types.ts"
Cohesion: 0.13
Nodes (22): AiBudget, BacktestRun, BacktestSummary, Confidence, DoseRun, Fundamentals, IngestReport, JournalEntry (+14 more)

### Community 48 - "pipeline.py"
Cohesion: 0.16
Nodes (21): best_per_symbol(), Any, Backtest screening: rank strategies across symbols. Runs a panel of strategies…, Collapse a leaderboard to the single best strategy per symbol., Backtest every (symbol, strategy) pair and return a ranked leaderboard.…, screen(), ScreenRow, _strategies() (+13 more)

### Community 49 - "sync_payload"
Cohesion: 0.13
Nodes (16): Persist an already-fetched payload, logging the attempt either way. Split from…, Log in, read, persist. Any failure is logged to ``ms_sync_log`` and returned as…, Import a CSV/pasted export and persist it, logging the attempt., Holdings as last synced, ordered by symbol., What one sync attempt did. ``error`` is always redacted., stored_holdings(), sync_from_client(), sync_from_csv() (+8 more)

### Community 50 - "CostEngine"
Cohesion: 0.10
Nodes (34): CostEngine, PaperTrade, An executed paper trade with full Nepal cost breakdown., _Lot, PaperPortfolio, date, Decimal, Paper-trading portfolio ledger. A self-contained, in-memory account that… (+26 more)

### Community 51 - "auction.py"
Cohesion: 0.10
Nodes (34): _advice_id(), advise_auction(), advise_from_plan(), _as_date(), auction_advice_history(), AuctionAdvice, _break_even_bid(), _break_even_exit_price() (+26 more)

### Community 52 - "test_mcp_protocol.py"
Cohesion: 0.11
Nodes (29): parse_message(), Exception, A protocol-level failure that must surface as a JSON-RPC ``error``. Method…, Parse one line of JSON into a :class:`Request`. Raises :class:`RpcError` with…, RpcError, dispatcher(), _line(), fixture (+21 more)

### Community 53 - "sync.py"
Cohesion: 0.08
Nodes (33): :func:`redact`, plus every account identifier on this instance., demat_fingerprint(), demat_last4(), _normalise(), Privacy-safe identifiers for persisted MeroShare mirror rows. The CDSC…, Return a deterministic, non-reversible storage key for a demat value., Return only the final four characters for masked display., _client_failure_message() (+25 more)

### Community 54 - "test_meroshare.py"
Cohesion: 0.10
Nodes (23): connection_disclosure(), MeroShareAuthError, MeroShareDisabledError, MeroShareError, Exception, Base for every failure in this package. Messages carry no credential., MeroShare integration is switched off in settings., Login was refused, or the session expired. (+15 more)

### Community 55 - "test_advisor_doses.py"
Cohesion: 0.09
Nodes (24): dose_history(), DoseRun, latest_dose_run(), Any, Connection, All four nested doses over one capital pool., Adapt a budgeted report to the persisted ``dose_runs`` contract., Render all four horizons as safe beginner-facing prose. (+16 more)

### Community 56 - "Plan: Web UI Dashboard"
Cohesion: 0.06
Nodes (32): Overview, Plan: Web UI Dashboard, Potential Risks & Gotchas, Prerequisites, Rollback Plan, Sprint 1: Backend API, Sprint 2: Frontend Foundation, Sprint 3: Dashboard + Symbols Page (+24 more)

### Community 57 - "_Base"
Cohesion: 0.14
Nodes (5): _Base, Position, BaseModel, Decimal, field_validator

### Community 58 - "App.tsx"
Cohesion: 0.10
Nodes (31): react, HoldingComparison, MeroShareHolding, NewsItem, PortfolioSummary, RagSearchResponse, ScreenRow, App() (+23 more)

### Community 59 - "MeroShareHolding"
Cohesion: 0.08
Nodes (31): Dialect, ConnectionResult, Outcome of :func:`connect` — a login probe that fetches nothing else., import_portfolio(), ImportError_, _match_column(), _norm(), parse_holdings_csv() (+23 more)

### Community 60 - "size_position"
Cohesion: 0.11
Nodes (14): exposure_pct(), Risk-managed position sizing, stop-loss, and exposure controls. All functions…, Compute the quantity to buy using fixed-fractional position sizing. Two sizing…, Compute the stop-loss price for a long position. Uses ATR-based or percentage-…, Compute the take-profit price for a long position., Return the fraction of equity deployed in a position (0–100)., size_position(), stop_loss_price() (+6 more)

### Community 61 - "Developers Guide — NEPSE Trader"
Cohesion: 0.08
Nodes (26): 10. Layer: costs and taxes, 11. Layer: paper trading, 12. Layer: RAG, 13. Layer: AI, 14. Layer: advisor, 15. Layer: MeroShare mirror, 16. Layer: health, 17. Surface: CLI (+18 more)

### Community 62 - "MeroShareClient"
Cohesion: 0.20
Nodes (6): MeroShareClient, Logs in once, then reads. Every boundary is injectable for testing. ``http``…, Log out, then drop the connection. Safe to call twice., parametrize, _settings(), TestClient

### Community 63 - "_run"
Cohesion: 0.14
Nodes (6): Signal, mode="normal" ignores the analyst entirely rather than half-using it., A default deterministic run over three symbols., _run(), TestNormalMode, TestSettlementInARun

### Community 64 - "_settings"
Cohesion: 0.11
Nodes (12): MonkeyPatch, parametrize, Tests for the runtime Settings model (modes, LLM, budget, RAG, MeroShare).…, Build Settings without reading the developer's real .env., Bulk per-symbol work must not default to a paid provider., claude_cli runs under the user's subscription — no API billing., Env vars are strings; a CSV watchlist must still parse to a list., _settings() (+4 more)

### Community 65 - "_safe_run"
Cohesion: 0.11
Nodes (31): _advisor_positions(), auction_advise_cmd(), doses(), ingest(), journal_score_cmd(), paper_buy(), paper_sell(), paper_status() (+23 more)

### Community 66 - "PriceBar"
Cohesion: 0.17
Nodes (11): _clamp01(), _clean_indicators(), Signal, Clamp ``x`` into [0, 1] (Signal.strength is validated ``0 <= s <= 1``)., Drop None entries; Signal.indicators is ``dict[str, float]``., Return signals for ``bars`` (chronological ascending)., Return (closes, has_close). ``closes`` carries the last valid close forward…, Convenience: the signal for the last day, or None if none produced. (+3 more)

### Community 67 - "fixtures.ts"
Cohesion: 0.07
Nodes (28): aiBudget, auctionAdvice, backtestRun, confidence, dashboardStats, doseRun, emptyMarketBreadth, emptyMovers (+20 more)

### Community 68 - "_settings"
Cohesion: 0.18
Nodes (14): ai_budget(), get_meroshare_setting(), health_report(), _meroshare_enabled(), _meroshare_settings(), meroshare_status(), Settings for the current request. Read out of ``_state`` rather than calling…, Effective integration toggle with its DB-or-environment provenance. (+6 more)

### Community 69 - "test_pipeline.py"
Cohesion: 0.09
Nodes (21): build_clients(), _construct(), Instantiate the source clients to run. By default this honours…, pipe(), asyncio, fixture, Integration tests for the daily pipeline (no network)., A fake source that returns canned bars — exercises ingest without network. (+13 more)

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
Nodes (13): Any, Config file validation using JSON Schema. Provides validation functions for the…, Validate a single YAML file against its JSON Schema. Returns a (possibly empty)…, Validate all config files. Returns list of error messages (empty = OK)., _validate(), validate_all(), validate_yaml(), Path (+5 more)

### Community 74 - "test_backtest_risk.py"
Cohesion: 0.33
Nodes (6): _bar(), _buy_sig(), _DummyStrategy, Signal, Tests for risk-managed stop-loss / take-profit in the event-driven backtester., TestStopLossInBacktest

### Community 75 - "sharesansar.py"
Cohesion: 0.14
Nodes (23): has_header(), Row, Resilient HTML table extraction with a pluggable backend. Two backends produce…, Return the Scrapling Selector class, or None if unavailable., Resolve the effective parse engine name ('scrapling' or 'selectolax')., Return rows of (tag, text) cell tuples for the first table matching…, The text of the ``<td>`` cells in a row (ignoring header ``<th>`` cells)., resolve_engine() (+15 more)

### Community 76 - "compilerOptions"
Cohesion: 0.08
Nodes (23): DOM, src, vite/client, compilerOptions, allowArbitraryExtensions, allowImportingTsExtensions, erasableSyntaxOnly, jsx (+15 more)

### Community 77 - "health.py"
Cohesion: 0.15
Nodes (14): Check, check_journal(), check_paper(), _guarded(), problems(), Any, One read-only health report over everything the toolkit owns. The daily loop…, Prediction lifecycle backlog: what is open, scored-but-unreviewed, retired. (+6 more)

### Community 78 - "TestRagSearch"
Cohesion: 0.15
Nodes (3): _index(), TestNews, TestRagSearch

### Community 79 - "AccountVault"
Cohesion: 0.18
Nodes (7): AccountVault, BankAccount, _money(), Decimal, Holds the sensitive, encapsulated account state. All money is stored as Decimal…, Accept Decimal / int / str. Refuse float (binary rounding errors)., The public-facing account that performs operations on a vault.

### Community 80 - "serve_stdio"
Cohesion: 0.11
Nodes (16): Dispatcher, mcp_serve_cmd(), Serve the local, read-only MCP toolkit over stdio., build_server(), Settings, Construct a fully wired :class:`MCPServer`. Separate from :func:`serve_stdio`…, Resolved I/O plus whether we own (and may therefore guard) real stdout., Serve MCP over newline-delimited JSON-RPC until stdin closes. Blocks. Returns… (+8 more)

### Community 81 - "compilerOptions"
Cohesion: 0.10
Nodes (19): node, vite.config.ts, compilerOptions, allowImportingTsExtensions, erasableSyntaxOnly, lib, module, moduleDetection (+11 more)

### Community 82 - "Tier 2 — strong analytical upside"
Cohesion: 0.10
Nodes (20): 1.1 Corporate-action adjustment (bonus / rights / splits) — **L**, `ingest/` + `analysis/`, 1.2 Verify & enable Chukul + NepseAlpha sources — **M**, `ingest/chukul.py`, new `ingest/nepsealpha.py`, 1.3 Holiday / trading-calendar awareness — **M**, new `calendar.py`, 1.4 Alerting integrations (Telegram / Discord / email) — **S–M**, `reporting.py`, 2.1 Multi-symbol portfolio backtest — **L**, `analysis/backtest.py`, 2.2 Risk-managed position sizing & stops — **M**, `analysis/strategies.py` + backtest, 2.3 Walk-forward optimization & parameter sweeps — **M**, new `analysis/optimize.py`, 2.4 More strategies — **S each**, `analysis/strategies.py` (+12 more)

### Community 83 - "HTTPException"
Cohesion: 0.12
Nodes (24): HTTPException, auction_advice_endpoint(), journal_distill_endpoint(), _journal_error(), journal_retire_endpoint(), journal_review_endpoint(), journal_score_endpoint(), journal_score_one_endpoint() (+16 more)

### Community 84 - "protocol.py"
Cohesion: 0.12
Nodes (16): MethodHandler, Dispatcher, error_response(), Any, JSON-RPC 2.0 framing and dispatch for the MCP server — transport-agnostic. This…, Routes JSON-RPC methods to registered handlers. Deliberately a plain name →…, Dispatch a parsed request. Returns ``None`` for notifications., Parse and dispatch one wire line. Never raises. Returns the response dict to… (+8 more)

### Community 85 - "indicator_document"
Cohesion: 0.18
Nodes (10): build_symbol_documents(), indicator_document(), Latest reading of every indicator, with its interpretation stated., Every document derivable for one symbol from its bar history. Only the most…, A bare number is useless in a report; the reading must be explained., Daily re-indexing must upsert, not accumulate., A rising series long enough for SMA50/RSI/MACD/Bollinger to have values., _series() (+2 more)

### Community 86 - ".daily_report"
Cohesion: 0.10
Nodes (12): Any, date, ReconciledPrice, Async variant: fetches from all sources concurrently., Call a client fetch method, isolating its failure to that data type., Reconciled history for a symbol as PriceBars (for indicators)., Rebuild the paper portfolio by replaying stored trades (no re-persist)., Advancers/decliners/turnover/reconcile-quality for a date. (+4 more)

### Community 87 - "Dashboard.tsx"
Cohesion: 0.22
Nodes (7): DashboardStats, MarketBreadth, MoversResponse, Badge(), Props, styles, DashboardPage()

### Community 88 - "renderWithProviders.tsx"
Cohesion: 0.28
Nodes (5): renderDetail(), handlers, Options, renderWithProviders(), server

### Community 89 - "How It Works — NEPSE Trader Internals"
Cohesion: 0.12
Nodes (17): 10. Paper portfolio (`trading/portfolio.py`), 11. Storage & idempotency (`storage/db.py`), 12. Failure philosophy, 13. Advisor and confidence, 14. Prediction journal and outcomes, 15. MeroShare, auction and modes, 1. End-to-end data flow, 2. The politeness & ethics layer (`ingest/base.py`) (+9 more)

### Community 90 - "devDependencies"
Cohesion: 0.12
Nodes (17): jsdom, oxlint, tailwindcss, @testing-library/jest-dom, @testing-library/react, @testing-library/user-event, @types/react-router-dom, @vitest/coverage-v8 (+9 more)

### Community 91 - "TestPersistence"
Cohesion: 0.20
Nodes (8): latest_run(), Persist a run and its cards; returns the run id. Stored so a call can be scored…, The most recent run with its cards, or None if the advisor never ran., Recent runs, newest first, without their cards., run_history(), _run_row_to_dict(), save_rashifal(), TestPersistence

### Community 92 - "SellCandidate"
Cohesion: 0.22
Nodes (7): build_sell_queue(), Which held positions to exit, from the engine's own view of each symbol.…, A held position the engine wants out of, and why., SellCandidate, date, PlanCard, TestSellQueue

### Community 93 - "Settings"
Cohesion: 0.07
Nodes (27): BaseSettings, Connection, The analyst: evidence in, validated commentary out. One class tying the pieces…, BudgetStatus, BudgetSummary, Connection, Token budgeting: hard ceilings with a DB-backed ledger. Three caps, all from…, Whether a call may proceed, and if not, why not in plain words. (+19 more)

### Community 94 - "walkforward.py"
Cohesion: 0.21
Nodes (12): _param_grid(), Any, Walk-forward optimisation with expanding or rolling windows. Splits price…, walk_forward(), WFOFold, WFResult, _bars(), Tests for walk-forward optimisation. (+4 more)

### Community 95 - "test_reporting.py"
Cohesion: 0.14
Nodes (23): backtest_report(), Path, Markdown summary of backtest performance metrics., Write a combined daily report with a top title and one ``##`` per section., Send a plain-text message via Telegram Bot API., Build a GitHub markdown table of signals (pure, exact-text testable)., signals_markdown(), write_markdown_report() (+15 more)

### Community 96 - "SourceClient"
Cohesion: 0.12
Nodes (12): date, Interface every source adapter implements. Concrete clients (ShareSansar,…, SourceClient, MeroLaganiFundamentalsClient, Fundamentals data scraping from MeroLagani company detail pages., Fetch fundamental data for a single symbol from MeroLagani., FloorsheetEntry, IndexValue (+4 more)

### Community 97 - "news.py"
Cohesion: 0.05
Nodes (34): _clean(), extract_symbols(), _headline_key(), _nearby_date(), _news_document(), NewsClient, _parse_date(), date (+26 more)

### Community 98 - "get"
Cohesion: 0.20
Nodes (20): get, advisor_doses_latest(), advisor_latest(), _advisor_run_response(), _attach_dose_cards(), _confidence_response(), _dose_response(), _dose_run_response() (+12 more)

### Community 99 - "conftest.py"
Cohesion: 0.14
Nodes (14): Config, Session, _isolate_run_logs(), fixture, Path, pytest_configure(), pytest_runtest_logreport(), pytest_sessionfinish() (+6 more)

### Community 100 - "check_freshness"
Cohesion: 0.22
Nodes (10): check_database(), check_freshness(), date, The database exists, is readable, and holds price rows., How far behind the newest reconciled close is, counted in trading days., Trading days strictly after *start* up to and including *end*., _trading_days_between(), date (+2 more)

### Community 101 - "_storage"
Cohesion: 0.08
Nodes (30): advisor_history(), auction_advice_history_endpoint(), auction_latest_endpoint(), dashboard(), health_history(), journal_calibration_endpoint(), journal_history_endpoint(), journal_review_queue_endpoint() (+22 more)

### Community 102 - "_d"
Cohesion: 0.14
Nodes (8): _d(), _dt(), date, datetime, ReconciledPrice, Signal, All reconciled consensus rows for a single business date., Aggregate statistics about the database contents.

### Community 103 - "NEPSE Trader — Agent Context"
Cohesion: 0.13
Nodes (14): Completed advisor scope, Current State, Key Design Decisions, NEPSE Trader — Agent Context, Open Questions / Planned, Project, Project Structure, Recent Sprint Progress (+6 more)

### Community 104 - "test_advisor_rashifal.py"
Cohesion: 0.12
Nodes (16): build_rashifal(), date, Describe the tape in one phrase, from advancers vs decliners., Compose a full run. Deterministic unless *analyst* is supplied. ``mode="ai"``…, _regime(), _bars(), _buys(), conn() (+8 more)

### Community 105 - "check_schema"
Cohesion: 0.43
Nodes (3): check_schema(), Every migration in the registry applied, and nothing unknown applied., TestSchema

### Community 106 - "TokenBudget"
Cohesion: 0.15
Nodes (12): iso_week(), date, Spend accounting over the ``ai_budget_ledger`` table., ``(billable_calls, billable_tokens)`` for today. Cache hits excluded., Whether one more call fits inside the caps. ``estimated_tokens`` lets a large…, Append one call to the ledger, successful or not. Failures are recorded with…, Most recent ledger rows, newest first — the audit trail., ``"2026-W35"`` — the key the weekly deep-pass cap counts against. (+4 more)

### Community 107 - "test_web_api.py"
Cohesion: 0.09
Nodes (7): client(), fixture, TestBacktest, TestDashboard, TestHealth, TestPortfolio, TestSymbols

### Community 108 - "read_bool"
Cohesion: 0.29
Nodes (9): ensure_table(), Any, Connection, Reads over the ``app_settings`` key/value table. Migration…, Assert the migrated table exists. Deliberately a guard and not ``CREATE…, ``(value, updated_at)`` for *key*, or ``(None, None)`` when unusable., As :func:`read_json`, but only a real JSON boolean counts as an override., read_bool() (+1 more)

### Community 109 - "dependencies"
Cohesion: 0.15
Nodes (13): clsx, lucide-react, react, react-dom, react-router-dom, recharts, dependencies, clsx (+5 more)

### Community 110 - "api.py"
Cohesion: 0.17
Nodes (20): FastAPI, advisor_run(), AdvisorRunRequest, backtest_run(), backtest_screen(), _evidence_builder(), health(), lifespan() (+12 more)

### Community 111 - "NEPSE Trader — Operations Runbook"
Cohesion: 0.12
Nodes (16): 10. MeroShare and auction safety, 11. MCP setup, 1. Daily lifecycle, 2. Scheduling (cron), 3. Sources & enabling/disabling, 4. HAR endpoint refresh (when a source breaks), 5. Paper trading, 6. Troubleshooting (+8 more)

### Community 112 - "How To Use — NEPSE Trader"
Cohesion: 0.06
Nodes (32): 10. Paper trading, 11. The daily run, 12. Advice — rashifal, advise, doses, 13. Prediction journal, 14. Auction bid ceiling, 15. Fundamentals and corporate actions, 16. Searching your own data, 17. AI mode (+24 more)

### Community 113 - "check_meroshare"
Cohesion: 0.39
Nodes (3): check_meroshare(), The read-only mirror: toggle, credential completeness, last sync. Reports field…, TestMeroShare

### Community 114 - "TestExtractResultLinks"
Cohesion: 0.22
Nodes (6): extract_result_links(), Result URLs from the configured search endpoint, best first., Pull outbound result URLs from a search results page. DuckDuckGo's HTML…, Turn a search-engine redirect link into the destination URL., _unwrap_redirect(), TestExtractResultLinks

### Community 115 - "_ensure_app_settings"
Cohesion: 0.12
Nodes (19): _advisor_symbols(), _ensure_app_settings(), get_watchlist(), MeroShareToggleRequest, put_meroshare_setting(), put_watchlist(), Persist a local toggle, or clear it with ``{"enabled": null}``., Assert the migrated settings table exists. ``app_settings`` is created by… (+11 more)

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

### Community 120 - "check_ingest"
Cohesion: 0.43
Nodes (3): check_ingest(), The error rate over the most recent ingest attempts, per source., TestIngest

### Community 121 - "Capabilities — NEPSE Trader"
Cohesion: 0.18
Nodes (11): 10. Performance characteristics, 1. Capability matrix, 2. Data & coverage, 3. Analytical capabilities, 4. Backtesting & screening, 5. Cost & tax fidelity, 6. The once-a-day report, 7. Advisor, mirror and MCP details (+3 more)

### Community 122 - "rashifal.py"
Cohesion: 0.11
Nodes (11): DoseReport, Compatibility/reporting view of the four nested doses., _attach_narrative(), _note_text(), The daily prescription: plan cards composed into a report. The name is a joke…, Ask the analyst for prose. Never let it affect a number, never let it raise.…, The card as text for the prompt. Read-only: the analyst sees, never sets., Flatten a :class:`WeeklyThesis` into prose for the report header. (+3 more)

### Community 123 - "NEPSE Trader"
Cohesion: 0.18
Nodes (11): Advisor, journal and MeroShare, Architecture, Daily automation, Data sources & reliability, Disclaimer, Documentation, Install, Nepal cost & tax model (+3 more)

### Community 124 - "test_cli.py"
Cohesion: 0.18
Nodes (3): fixture, CLI smoke tests via Typer's CliRunner (no network)., _temp_db()

### Community 125 - "NEPSE Trader — project skill"
Cohesion: 0.20
Nodes (9): Common tasks → commands, Companion skills, Fetch / parse engines, Hard rules (do not cross), NEPSE Trader — project skill, Setup (once), The once-a-day run (the main thing), When a source breaks (endpoint discovery) (+1 more)

### Community 126 - "credentials.py"
Cohesion: 0.12
Nodes (14): keyring_available(), MeroShareCredentialError, _password_from_keyring(), Exception, MeroShare credential resolution — and every path a secret could escape by. The…, Which fields are empty, by name — safe to show the user., Self, or raise naming only the *missing field names*., Whether the optional ``keyring`` module imports. ``(ok, reason)``. (+6 more)

### Community 127 - "build.py"
Cohesion: 0.14
Nodes (15): _breadth_documents(), _corporate_action_documents(), _documents_for_symbol(), _flush(), IndexReport, _periods(), Corpus construction: walk the database, emit documents, write the index.…, What an indexing run produced. (+7 more)

### Community 128 - "_to_money"
Cohesion: 0.22
Nodes (8): _expected_outcome(), Decimal, PnL at *exit_price*, net of entry costs, exit costs and CGT. The gross figure…, CostBreakdown, Decimal, Nepal equity transaction cost & tax engine. Computes the full, realistic cost…, Convert a number to paisa-precise Decimal (2 dp, half-up)., _to_money()

### Community 129 - "Alerter"
Cohesion: 0.11
Nodes (15): Alerter, Response, Pluggable alert backends: Telegram, Discord, SMTP, and generic webhook. Every…, Thin POST wrapper kept separate so tests can monkeypatch it., POST the alert if a webhook is set; return success. No webhook -> False, no…, Send a message to a Discord channel via webhook., Send an email via SMTP. Returns True on success., test_alerter_no_webhook_returns_false_no_network() (+7 more)

### Community 131 - "Per-site capture recipes"
Cohesion: 0.22
Nodes (9): 1. ShareSansar — `sharesansar.har` (PRIMARY), 2. Chukul — `chukul.har` (verify inferred /v1/ paths), 3. MeroLagani — `merolagani.har` (secondary HTML), 4. NepseAlpha — `nepsealpha.har` (TradingView UDF, Cloudflare-gated), 5. NEPSE official — `nepse_official.har` (reference / replay only), HAR Capture Plan — NEPSE data sources, How to capture a HAR (Chrome / Firefox / Edge), Per-site capture recipes (+1 more)

### Community 132 - "SearchHit"
Cohesion: 0.08
Nodes (21): _as_scored(), EvidenceItem, Turning retrieved documents into a bounded, citable evidence block. An…, Normalise either input shape to (document, score) pairs., Interleave across kinds, preserving each kind's internal ranking., One document admitted into the pack, with its citation marker., _round_robin_by_kind(), One retrieved document plus why it matched. (+13 more)

### Community 133 - "plugins"
Cohesion: 0.22
Nodes (8): oxc, typescript, warn, plugins, rules, react/only-export-components, react/rules-of-hooks, $schema

### Community 134 - "TestCardNumbers"
Cohesion: 0.11
Nodes (4): fixture, PlanCard, A stop the market cannot reach in one session would understate the risk., TestCardNumbers

### Community 135 - "FakeAnalyst"
Cohesion: 0.26
Nodes (6): FakeAnalyst, _note(), Returns valid notes and records every call, so we can assert on inputs., The card already has the engine's action; a second opinion beside it is how a…, TestAIMode, _thesis()

### Community 136 - "scripts"
Cohesion: 0.25
Nodes (8): scripts, build, coverage, dev, lint, preview, test, test:run

### Community 137 - "NEPSE risk & position sizing — project skill"
Cohesion: 0.29
Nodes (6): Ask the engine for exact costs (don't approximate), Fit-check an existing paper portfolio, Hard rules, Nepal mechanics you MUST respect, NEPSE risk & position sizing — project skill, Sizing protocol (fixed-fractional, R-based)

### Community 138 - "add_trading_days"
Cohesion: 0.20
Nodes (5): add_trading_days(), Return the date *n* trading days from *d*, skipping weekends and holidays.…, A trade dated Saturday is really the Sunday session., T+2 settlement lives on this function, so the weekend cases matter most., TestAddTradingDays

### Community 139 - "test_rag_corpus.py"
Cohesion: 0.24
Nodes (9): iter_documents(), price_document(), A single day's OHLCV as prose., Drop the ``None`` results that builders return for thin data., _bar(), Tests for the RAG document corpus builders. Two invariants carry the whole…, test_iter_documents_drops_nones(), TestAsRow (+1 more)

### Community 140 - "test_health.py"
Cohesion: 0.17
Nodes (11): fixture, check_rag(), Connection, Corpus size, per-kind coverage, and whether ranked search is available., Persist *report* and return its row id. Called only when a caller explicitly…, One stored report in full, or None when that id was never recorded., record_snapshot(), snapshot() (+3 more)

### Community 141 - "TestSectorOfTheDay"
Cohesion: 0.39
Nodes (3): The sector with the best mean change today. Takes an already-grouped mapping so…, _sector_of_the_day(), TestSectorOfTheDay

### Community 142 - "NEPSE backtest protocol — project skill"
Cohesion: 0.33
Nodes (5): Hard rules, NEPSE backtest protocol — project skill, Red flags that mean "do not deploy", The protocol (run in order), Why discipline matters on NEPSE specifically

### Community 143 - "PlanCard"
Cohesion: 0.17
Nodes (8): build_plan_cards(), PlanCard, date, Build cards for *symbols*, returning the cards and the skips separately.…, A symbol that could not be given an honest card, and why. Surfaced rather than…, One symbol's prescription. Every field here is engine-computed., Skipped, TestBuildPlanCards

### Community 144 - "23. All the settings"
Cohesion: 0.29
Nodes (7): 23. All the settings, AI providers, AI spending caps, Analysis, Fetching politely, Search and MeroShare, Where things live

### Community 145 - "package.json"
Cohesion: 0.40
Nodes (4): name, private, type, version

### Community 146 - "check_ai"
Cohesion: 0.21
Nodes (7): check_ai(), check_config(), Settings, YAML config parses against its schema, and at least one source is on., Whether AI mode could actually answer, and how much budget is left. Reads the…, TestAi, TestConfig

### Community 147 - "test_advisor_plan.py"
Cohesion: 0.21
Nodes (7): _decide(), Signal, Turn the strategy panel's votes into an action, conviction and reasons.…, Tests for the deterministic plan engine. The point of these tests is that…, AVOID exists for the AI vocabulary; the engine has no rule that emits it., _signal(), TestDecide

### Community 148 - "React + TypeScript + Vite"
Cohesion: 0.50
Nodes (3): Expanding the Oxlint configuration, React Compiler, React + TypeScript + Vite

### Community 149 - "Health.tsx"
Cohesion: 0.15
Nodes (10): api, HealthCheck, HealthReport, HealthSnapshot, HealthStatus, BADGE_VARIANT, CheckRow(), ICONS (+2 more)

### Community 158 - "LLMRouter"
Cohesion: 0.21
Nodes (8): LLMRouter, Best available answer to *prompt*, or a response explaining the gap. ``task``…, Everything ``ai models`` prints: chains, availability, caps, cache., A refusal, logged in the ledger so the reason survives the run., Cache → budget → provider chain, with graceful failure at every step., Provider names to try, in order, for *tier*., A cached provider instance, or None if the name is unknown., The legs of *tier*'s chain that are configured well enough to try.

### Community 170 - "reconcile_bars"
Cohesion: 0.25
Nodes (12): _consensus(), ReconciledPrice, Cross-source reconciliation. The whole point of pulling the same NEPSE data…, Return (agreed_value, agreeing_sources, disputed). Greedy clustering: for each…, reconcile_bars(), _within(), _bar(), Tests for cross-source reconciliation. (+4 more)

### Community 171 - "3. Robustness & resilience"
Cohesion: 0.40
Nodes (5): 3.1 Async, concurrent ingestion — **high impact**, `ingest/base.py`, 3.2 Per-source circuit breaker — **medium**, 3.3 Respect `Retry-After` and `robots.txt` programmatically — **medium**, 3.4 Schema-driven HTML parsing — **medium**, `ingest/sharesansar.py`, `merolagani.py`, 3. Robustness & resilience

### Community 175 - "TestDegradation"
Cohesion: 0.18
Nodes (5): ExplodingAnalyst, A badly-behaved analyst: raises instead of degrading., Every failure path must yield the full deterministic report plus a banner., It must not raise out of build_rashifal — that is the whole contract., TestDegradation

### Community 176 - "Rashifal"
Cohesion: 0.17
Nodes (5): PlanCard, Rashifal, One advisor run: the whole daily prescription., DegradingAnalyst, The documented failure mode: returns None and reports why.

### Community 177 - "BaseModel"
Cohesion: 0.18
Nodes (11): BaseModel, AuctionAdviceRequest, JournalDistillRequest, JournalReviewRequest, meroshare_import(), MeroShareImportRequest, A pasted CSV/holdings export. No credential is involved in this path., Persist a pasted CSV export — the no-credentials path into the mirror. (+3 more)

### Community 178 - "ai_budget"
Cohesion: 0.20
Nodes (10): ai_budget(), ai_models(), ai_test(), A router over the real database. Opens the DB; caller keeps the Storage., Show each provider chain and which legs are actually usable., Today's LLM spend against the caps, plus cache size., Send one tiny prompt through a chain and report what answered. This spends real…, Quantitative statistics per symbol over reconciled history. Annualised return &… (+2 more)

### Community 179 - "progress_bars"
Cohesion: 0.29
Nodes (9): progress_bars(), progress_spinner(), Console, T, A simple spinner context for indeterminate tasks., Reusable Progress instance with standard columns., Iterate over *seq* with a live progress bar., track() (+1 more)

### Community 180 - "plan_cards_md"
Cohesion: 0.38
Nodes (4): plan_cards_md(), Render plan cards as one table row per symbol. Cards are…, _card(), TestPlanCardsMd

### Community 181 - "HoldingDiff"
Cohesion: 0.22
Nodes (6): HoldingDiff, One symbol's disagreement (or agreement) between real and paper books., Real minus paper. Positive means the real account holds more., ``"real"``, ``"paper"``, or ``None`` when both hold the symbol., comparison_summary(), Counts over :func:`compare_with_paper`'s output, for a one-line report.

### Community 182 - "ReconciledPrice"
Cohesion: 0.25
Nodes (8): A price for a symbol/date agreed (or disputed) across multiple sources., ReconciledPrice, ReconciledPrice, Markdown table of reconciled prices, flagging low-confidence / disputed rows., reconciliation_report(), test_reconciliation_report_empty(), test_reconciliation_report_flags_disputed_even_if_confident(), test_reconciliation_report_flags_low_confidence()

### Community 184 - "test_storage.py"
Cohesion: 0.36
Nodes (8): _bar(), Tests for the SQLite storage layer., test_bars_for_date(), test_db_stats(), test_different_sources_kept_separately(), test_index_values_roundtrip(), test_upsert_and_read_back(), test_upsert_is_idempotent_per_source()

### Community 185 - "_drive"
Cohesion: 0.21
Nodes (8): _drive(), A client should learn the ceiling from the schema, not from an error., Run serve_stdio over StringIO. Returns (responses, raw stdout text)., With explicit streams the loop must leave sys.stdout untouched., test_declared_schemas_advertise_the_caps_the_handlers_enforce(), test_end_to_end_initialize_list_and_call_over_the_stdio_loop(), test_serve_stdio_does_not_leak_the_real_stdout_rebinding(), test_stdio_loop_returns_cleanly_on_eof()

### Community 187 - "FundamentalData"
Cohesion: 0.40
Nodes (3): Fetch and parse fundamentals for *symbol*., FundamentalData, TestFundamentalDocument

### Community 188 - "TestNoNetworkAndNoLLM"
Cohesion: 0.33
Nodes (3): The load-bearing guarantee: Normal mode is fully offline., The Claude leg is a subprocess; the engine must never reach it., TestNoNetworkAndNoLLM

### Community 189 - "do_not_touch_md"
Cohesion: 0.50
Nodes (3): do_not_touch_md(), Render the excluded symbols with their reasons. A symbol missing from the…, TestDoNotTouchMd

### Community 190 - "sell_queue_md"
Cohesion: 0.50
Nodes (3): Render the exit queue: what to sell, why, and the earliest legal date., sell_queue_md(), TestSellQueueMd

### Community 191 - "_m0006_meroshare"
Cohesion: 0.40
Nodes (4): _m0006_meroshare(), _m0012_meroshare_demat_privacy(), Read-only mirror of the user's own MeroShare/CDSC account. **No credential has…, Replace raw demat identifiers with a stable hash and masked suffix. ``0006``…

### Community 192 - "test_list_returning_tools_report_how_much_they_returned"
Cohesion: 0.40
Nodes (5): parametrize, An oversized request must fail loudly; a truncated answer would read as…, Every unbounded list carries ``returned``/``truncated`` alongside ``count``., test_list_returning_tools_report_how_much_they_returned(), test_over_the_cap_requests_are_rejected_not_silently_served()

### Community 193 - "card"
Cohesion: 0.50
Nodes (4): card(), fixture, PlanCard, storage()

### Community 194 - "_seed"
Cohesion: 0.50
Nodes (4): fixture, Write both raw and reconciled bars: tools read from each side., _seed(), storage()

### Community 196 - "conn"
Cohesion: 0.67
Nodes (3): conn(), fixture, Path

### Community 197 - "conn"
Cohesion: 0.67
Nodes (3): conn(), fixture, Path

## Knowledge Gaps
- **375 isolated node(s):** `Mover`, `BacktestSummary`, `Confidence`, `RagHit`, `NAV_ITEMS` (+370 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **27 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Settings` connect `Settings` to `_settings`, `LLMProvider`, `SearchHit`, `test_ai_analyst.py`, `BaseClient`, `ResponseCache`, `parse_into`, `SymbolNote`, `test_api_phase6.py`, `test_mcp_server.py`, `WebRetriever`, `client.py`, `LLMRouter`, `Analyst`, `DailyPipeline`, `LLMResponse`, `TestAdvisor`, `pipeline.py`, `sync_payload`, `test_meroshare.py`, `_drive`, `TestMeroShareImport`, `MeroShareHolding`, `MeroShareClient`, `_settings`, `test_pipeline.py`, `TestRagSearch`, `serve_stdio`, `SourceClient`, `news.py`, `TokenBudget`, `TestExtractResultLinks`, `credentials.py`?**
  _High betweenness centrality (0.139) - this node is a cross-community bridge._
- **Why does `PriceBar` connect `PriceBar` to `corpus.py`, `reporting.py`, `Storage`, `BaseClient`, `test_nepse_official.py`, `test_sharesansar.py`, `test_rag_corpus.py`, `test_strategies.py`, `test_api_phase6.py`, `test_mcp_server.py`, `nepse_trader/models.py`, `test_advisor_plan.py`, `test_properties.py`, `outcomes.py`, `Backtester`, `ChukulClient`, `plan.py`, `build_plan_card`, `NepseAlphaClient`, `merolagani.py`, `reconcile_bars`, `DailyPipeline`, `pipeline.py`, `test_storage.py`, `_Base`, `_seed`, `test_pipeline.py`, `SmaCrossStrategy`, `test_backtest_risk.py`, `sharesansar.py`, `indicator_document`, `.daily_report`, `walkforward.py`, `test_reporting.py`, `SourceClient`, `_d`, `test_advisor_rashifal.py`, `test_web_api.py`, `test_cli_advisor.py`?**
  _High betweenness centrality (0.065) - this node is a cross-community bridge._
- **Why does `Storage` connect `Storage` to `LLMProvider`, `test_ai_analyst.py`, `FakeAnalyst`, `ResponseCache`, `TestSectorOfTheDay`, `test_api_phase6.py`, `test_mcp_server.py`, `nepse_trader/models.py`, `advisor/__init__.py`, `migrations.py`, `CorporateAction`, `LLMResponse`, `TestDegradation`, `pipeline.py`, `Rashifal`, `test_meroshare.py`, `test_advisor_doses.py`, `test_storage.py`, `_run`, `card`, `_seed`, `conn`, `conn`, `test_pipeline.py`, `TestPersistence`, `SellCandidate`, `Settings`, `_d`, `test_advisor_rashifal.py`, `test_web_api.py`, `test_cli_advisor.py`?**
  _High betweenness centrality (0.059) - this node is a cross-community bridge._
- **Are the 127 inferred relationships involving `Settings` (e.g. with `Analyst` and `BudgetStatus`) actually correct?**
  _`Settings` has 127 INFERRED edges - model-reasoned connections that need verification._
- **Are the 65 inferred relationships involving `Document` (e.g. with `JournalError` and `Prediction`) actually correct?**
  _`Document` has 65 INFERRED edges - model-reasoned connections that need verification._
- **Are the 58 inferred relationships involving `LLMResponse` (e.g. with `BudgetStatus` and `BudgetSummary`) actually correct?**
  _`LLMResponse` has 58 INFERRED edges - model-reasoned connections that need verification._
- **Are the 30 inferred relationships involving `CostEngine` (e.g. with `AuctionAdvice` and `Dose`) actually correct?**
  _`CostEngine` has 30 INFERRED edges - model-reasoned connections that need verification._