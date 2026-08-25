# Graph Report - nepse-trader  (2026-08-25)

## Corpus Check
- 221 files · ~243,374 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 4832 nodes · 12069 edges · 198 communities (170 shown, 28 thin omitted)
- Extraction: 91% EXTRACTED · 9% INFERRED · 0% AMBIGUOUS · INFERRED: 1051 edges (avg confidence: 0.51)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `adddd615`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- _settings
- LLMProvider
- Path
- test_rag_corpus.py
- reporting.py
- Storage
- LLMResponse
- DocumentIndex
- base.py
- test_nepse_official.py
- SourceName
- build_evidence
- ResponseCache
- parse_into
- TestExtractJson
- test_strategies.py
- MeroShareHolding
- test_mcp_server.py
- ._search_fts
- jobs.py
- quant.py
- doses.py
- journal.py
- test_properties.py
- outcomes.py
- Backtester
- ChukulClient
- BaseClient
- advisor/__init__.py
- MeroShareClient
- JobRegistry
- build_plan_card
- Plan: NEPSE Trader — Full Completion
- NepseAlphaClient
- migrations.py
- merolagani.py
- test_costs.py
- MCPServer
- test_logging_setup.py
- analyzer.py
- Settings
- add_trading_days
- ReconciledPrice
- DailyPipeline
- _build_advisor_result
- _budget
- TestAdvisor
- types.ts
- screen.py
- api.py
- CostEngine
- _to_money
- test_mcp_protocol.py
- test_meroshare.py
- MeroShareCredentials
- test_advisor_doses.py
- Plan: Web UI Dashboard
- test_web_operations.py
- App.tsx
- meroshare/__init__.py
- size_position
- Developers Guide — NEPSE Trader
- .parse_announcements
- _run
- _settings
- main.py
- PriceBar
- fixtures.ts
- test_ingest_news.py
- test_pipeline.py
- rashifal_md
- Make It Even Better — Engineering Quality Upgrades
- SmaCrossStrategy
- validate_yaml
- nepse_trader/models.py
- htmlparse.py
- compilerOptions
- test_health.py
- SourceClient
- AccountVault
- TestHtmlToText
- compilerOptions
- Tier 2 — strong analytical upside
- get
- Dispatcher
- Document
- .daily_report
- Operations.tsx
- renderWithProviders.tsx
- How It Works — NEPSE Trader Internals
- devDependencies
- rashifal.py
- SellCandidate
- .complete
- walkforward.py
- test_reporting.py
- JobBusy
- .parse_news_list
- _advisor_run_response
- conftest.py
- post
- _settings
- check_schema
- NEPSE Trader — Agent Context
- test_advisor_rashifal.py
- check_freshness
- SourceSpec
- TokenBudget
- read_bool
- dependencies
- TestRagSearch
- NEPSE Trader — Operations Runbook
- How To Use — NEPSE Trader
- TestJobRoutes
- NewsClient
- _ensure_app_settings
- test_cli_advisor.py
- Auction.tsx
- Rashifal.tsx
- 22. Recipes
- TestTableBrowser
- Capabilities — NEPSE Trader
- Check
- NEPSE Trader
- test_cli.py
- NEPSE Trader — project skill
- test_rag_index.py
- FakeAnalyst
- config.py
- Alerter
- Per-site capture recipes
- Job
- plugins
- DoseReport
- TestExtractResultLinks
- scripts
- NEPSE risk & position sizing — project skill
- news.py
- _DummyStrategy
- FetchResult
- TestCitations
- NEPSE backtest protocol — project skill
- TestClient
- 23. All the settings
- package.json
- _client
- _decide
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
- ExplodingAnalyst
- @tailwindcss/vite
- @types/react
- @types/react-dom
- typescript
- vite
- @vitejs/plugin-react
- vitest
- nepse-trader
- ToolSpec
- 3. Robustness & resilience
- TestSectorOfTheDay
- _drive
- ._split_csv
- PlanCard
- TestPaperTrades
- add_corporate_action
- progress_spinner
- TestAiRoutes
- plan_cards_md
- card
- _seed
- conn
- conn
- server.py
- TestMeroShareImport
- conn
- conn
- do_not_touch_md
- sell_queue_md
- redact
- JobCancelled
- @types/node
- Signal
- BaseModel
- ValueError
- fixture

## God Nodes (most connected - your core abstractions)
1. `Settings` - 217 edges
2. `Document` - 138 edges
3. `PriceBar` - 131 edges
4. `DocumentIndex` - 130 edges
5. `Storage` - 122 edges
6. `LLMResponse` - 112 edges
7. `CostEngine` - 102 edges
8. `DailyPipeline` - 91 edges
9. `BaseClient` - 89 edges
10. `TokenBudget` - 73 edges

## Surprising Connections (you probably didn't know these)
- `_StubSource` --uses--> `DailyPipeline`  [INFERRED]
  tests/test_pipeline.py → nepse_trader/pipeline.py
- `TestAiRoutes` --uses--> `JobBusy`  [INFERRED]
  tests/test_web_operations.py → nepse_trader/web/jobs.py
- `TestBulkAnalytics` --uses--> `JobBusy`  [INFERRED]
  tests/test_web_operations.py → nepse_trader/web/jobs.py
- `TestCorporateActions` --uses--> `JobBusy`  [INFERRED]
  tests/test_web_operations.py → nepse_trader/web/jobs.py
- `TestInventoryRoutes` --uses--> `JobBusy`  [INFERRED]
  tests/test_web_operations.py → nepse_trader/web/jobs.py

## Import Cycles
- None detected.

## Communities (198 total, 28 thin omitted)

### Community 0 - "_settings"
Cohesion: 0.05
Nodes (38): _anthropic_text(), AnthropicProvider, ClaudeCliProvider, estimate_tokens(), NullProvider, _openrouter_text(), OpenRouterProvider, The local Claude Code CLI, driven as a subprocess. The prompt goes in on… (+30 more)

### Community 1 - "LLMProvider"
Cohesion: 0.05
Nodes (38): LLMProvider, ABC, True when the provider is configured well enough to try. Checked without any…, Anything that can turn a prompt into text., The model this provider would use right now, for the ledger., ExplodingProvider, FakeProvider, _ok() (+30 more)

### Community 2 - "Path"
Cohesion: 0.15
Nodes (15): har_analyze(), har_redact(), har_to_config(), meroshare_import_cmd(), meroshare_toggle_cmd(), Path, Import a MeroShare CSV export without using any portal credential., Turn the optional MeroShare integration on or off in one local setting. (+7 more)

### Community 3 - "test_rag_corpus.py"
Cohesion: 0.08
Nodes (25): build_symbol_documents(), indicator_document(), iter_documents(), price_document(), ReconciledPrice, quant_document(), A single day's OHLCV as prose., Latest reading of every indicator, with its interpretation stated. (+17 more)

### Community 4 - "reporting.py"
Cohesion: 0.11
Nodes (26): _fmt_num(), leaderboard_md(), market_overview_md(), _md_escape(), movers_md(), portfolio_summary(), price_bars_markdown(), print_signals() (+18 more)

### Community 5 - "Storage"
Cohesion: 0.07
Nodes (28): export_csv(), export_parquet(), Path, _d(), _dt(), date, datetime, ReconciledPrice (+20 more)

### Community 6 - "LLMResponse"
Cohesion: 0.09
Nodes (16): LLMResponse, What a provider returned — or why it didn't., True when there is usable text and no error., _analyst(), date, One pass per symbol times twenty-five symbols — free models, not synthesis., One failure, one degradation — not "no response" plus "failed validation"., ``deep`` is what the weekly cap counts; it must reach the router. (+8 more)

### Community 7 - "DocumentIndex"
Cohesion: 0.07
Nodes (14): DocumentIndex, Connection, Remove every document of one kind (used when rebuilding a slice)., Document count per kind — what the corpus actually holds., Read/write access to the document corpus and its search index., True when bm25 ranking is available; False means the LIKE fallback., Insert or replace documents by ``doc_id``. Returns the count written. Uses…, Same id twice must not double-count — this is what daily re-indexing does. (+6 more)

### Community 8 - "base.py"
Cohesion: 0.07
Nodes (43): FetchError, _HostThrottle, Client, Exception, RateLimitedError, Polite HTTP base client shared by all ingestion sources. Design goals: *…, Raised when a source signals 429/403 — we back off, never bypass., Non-retryable fetch failure (bad status, parse impossible). (+35 more)

### Community 9 - "test_nepse_official.py"
Cohesion: 0.07
Nodes (55): decode_content(), _extract_records(), find_entries(), _first(), HarReplayClient, is_available(), load_har(), _looks_sharesansar() (+47 more)

### Community 10 - "SourceName"
Cohesion: 0.06
Nodes (48): _int(), _num(), _parse_date(), _parse_datetime(), _parse_headline(), date, ShareSansar ingestion client — the project's PRIMARY public-data source.…, Extract plain text from a value that may be an HTML anchor. ShareSansar's JSON… (+40 more)

### Community 11 - "build_evidence"
Cohesion: 0.08
Nodes (28): build_evidence(), EvidencePack, A compact source list for the human-facing report., Pack hits into an :class:`EvidencePack` under both ceilings. ``max_documents``…, A size-bounded, ordered, citable set of documents., Distinct symbols appearing in the evidence, in first-seen order., ``{"[E1]": "price:NABIL:2026-08-20", ...}`` — for auditing an answer., The block to embed in a prompt. (+20 more)

### Community 12 - "ResponseCache"
Cohesion: 0.08
Nodes (25): cache_key(), Connection, Delete entries past the TTL. Returns how many went., Size and age of the cache, for ``ai budget``., Stable key for a request's content. The parts are joined with a separator that…, SQLite-backed cache over the ``ai_cache`` table., A fresh cached response, or None on a miss or an expired entry., Store a successful response. Returns whether it was written. Failures are never… (+17 more)

### Community 13 - "parse_into"
Cohesion: 0.06
Nodes (19): parse_into(), T, Parse *text* into *model*, or return None and log why. ``defaults`` fill fields…, _critique_json(), _note_json(), parametrize, The contract: a failed pass costs narrative, never an exception., Some models wrap the single answer in a list. (+11 more)

### Community 14 - "TestExtractJson"
Cohesion: 0.22
Nodes (6): extract_json(), _json_candidates(), Find the JSON payload in a model's reply, or None. Three shapes, tried in…, Free models ignore "no prose before or after it" constantly., ``42`` is valid JSON but no model's worth of fields., TestExtractJson

### Community 15 - "test_strategies.py"
Cohesion: 0.07
Nodes (50): BollingerStrategy, build_strategy(), CompositeStrategy, DonchianStrategy, IchimokuStrategy, MacdStrategy, MeanReversionStrategy, ABC (+42 more)

### Community 16 - "MeroShareHolding"
Cohesion: 0.05
Nodes (25): MeroShareHolding, field_validator, One scrip balance in the user's demat account, as MeroShare reports it., Total invested in this scrip per the portal's WACC., _bars(), client(), empty_client(), _make_client() (+17 more)

### Community 17 - "test_mcp_server.py"
Cohesion: 0.08
Nodes (45): _call(), _payload(), parametrize, Server-layer tests: tool registry, tool call semantics, and the stdio loop.…, Invoke a tool through the dispatcher and return the raw MCP result., Parse the JSON a tool rendered into its single text content block., An oversized request must fail loudly; a truncated answer would read as…, Every unbounded list carries ``returned``/``truncated`` alongside ``count``. (+37 more)

### Community 18 - "._search_fts"
Cohesion: 0.14
Nodes (14): _matched(), date, Row, Best-matching documents for *query*, most relevant first.…, Term-overlap ranking. Correct, just less clever than bm25., Newest documents matching the filters, ignoring relevance., Extract searchable words (Latin + Devanagari) from a raw query., Turn free text into a safe FTS5 MATCH expression. Terms are OR-ed with a prefix… (+6 more)

### Community 19 - "jobs.py"
Cohesion: 0.16
Nodes (18): _job_ingest(), _job_rag_index(), _job_reconcile(), _job_run_daily(), _job_screen(), JobContext, Any, date (+10 more)

### Community 20 - "quant.py"
Cohesion: 0.08
Nodes (45): annualized_return(), annualized_volatility(), beta(), correlation(), covariance(), kurtosis(), max_drawdown(), mean() (+37 more)

### Community 21 - "doses.py"
Cohesion: 0.11
Nodes (37): _add_sell_guidance(), build_dose_run(), build_doses(), _card_horizon(), _card_value(), _confidence_for_card(), _date(), _decimal() (+29 more)

### Community 22 - "journal.py"
Cohesion: 0.11
Nodes (49): _as_date(), _confidence(), distill_lesson(), _fetch(), get_prediction(), journal_history(), JournalError, _lesson_stats() (+41 more)

### Community 23 - "test_properties.py"
Cohesion: 0.04
Nodes (78): given, atr(), bollinger_bands(), chikou_span(), donchian_channel(), ema(), kijun_sen(), latest() (+70 more)

### Community 24 - "outcomes.py"
Cohesion: 0.10
Nodes (38): _date(), _is_short(), _number(), Outcome, OutcomeResult, _prediction_symbol(), Any, datetime (+30 more)

### Community 25 - "Backtester"
Cohesion: 0.10
Nodes (34): Backtester, BacktestResult, _max_drawdown(), date, Event-driven, long-only backtester over a single symbol's price bars., Replay ``bars`` for ``strategy`` and return a :class:`BacktestResult`. Bars are…, Apply slippage: buys fill higher, sells fill lower., Largest whole-share quantity affordable within the cash budget. Budget is… (+26 more)

### Community 26 - "ChukulClient"
Cohesion: 0.09
Nodes (34): _as_records(), ChukulClient, _int(), _num(), _pick(), Any, date, Chukul JSON source adapter. Chukul (https://chukul.com) is powered by a… (+26 more)

### Community 27 - "BaseClient"
Cohesion: 0.11
Nodes (26): BaseClient, Wraps httpx with throttling, retries, and optional raw-response caching., build_retriever(), HybridRetriever, LocalRetriever, Lazily built so constructing a WebRetriever opens no connection., Local first, web only when the local result set is thin. ``min_local_hits`` is…, The right retriever for the current mode. Offline (or web disabled) gives a… (+18 more)

### Community 28 - "advisor/__init__.py"
Cohesion: 0.09
Nodes (32): band_for(), blend(), certain(), Confidence, confidence_from_history(), ConfidenceError, market(), penalise() (+24 more)

### Community 29 - "MeroShareClient"
Cohesion: 0.10
Nodes (24): _as_date(), _as_float(), _as_int(), MeroShareAuthError, MeroShareClient, MeroShareFetchError, _pick(), Any (+16 more)

### Community 30 - "JobRegistry"
Cohesion: 0.13
Nodes (10): JobRegistry, In-memory job store that runs at most one job at a time., Drop all history. Used between tests so registries never leak state., Register throwaway job kinds, and remove them again afterwards. Editing the…, A worker must never share the request-path Storage., Entering a stage checks for cancellation, so later work never starts., A Saturday must not reach the network. Every stage is skipped., stub_handlers() (+2 more)

### Community 31 - "build_plan_card"
Cohesion: 0.05
Nodes (31): build_plan_card(), build_plan_cards(), Confidence, date, Build one symbol's card, or explain why it can't be built. *today* defaults to…, Build cards for *symbols*, returning the cards and the skips separately.…, A symbol that could not be given an honest card, and why. Surfaced rather than…, Skipped (+23 more)

### Community 32 - "Plan: NEPSE Trader — Full Completion"
Cohesion: 0.05
Nodes (43): Overview, Plan: NEPSE Trader — Full Completion, Potential Risks & Gotchas (addressed), Prerequisites, Rollback Plan, Sprint 0: Engineering Foundation, Sprint 1: Tier 1 Features, Sprint 2: Analytical Upside (+35 more)

### Community 33 - "NepseAlphaClient"
Cohesion: 0.13
Nodes (11): NepseAlphaClient, Any, date, Fetch daily price bars for *symbol* from the UDF history endpoint. The endpoint…, NepseAlpha is supplementary and doesn't support whole-market fetch. Returns an…, Client for NepseAlpha's TradingView UDF datafeed., Parse TradingView UDF history JSON into PriceBar records. Expected payload…, mock (+3 more)

### Community 34 - "migrations.py"
Cohesion: 0.05
Nodes (40): Path, _applied_versions(), _create_version_table(), _m0000_initial(), _m0001_corporate_actions(), _m0002_adjusted_close(), _m0004_ai(), _m0005_advice() (+32 more)

### Community 35 - "merolagani.py"
Cohesion: 0.09
Nodes (32): HTMLParser, _build_column_map(), _cell_at(), _cell_text(), _data_rows(), _first_match(), _int(), MeroLaganiClient (+24 more)

### Community 36 - "test_costs.py"
Cohesion: 0.17
Nodes (17): CostBreakdown, CommissionSlab, CostModel, BaseModel, Nepal equity transaction cost + tax model. Values are tunable via YAML., _engine(), Tests for the Nepal cost & tax engine. The headline test reproduces the…, test_buy_breakdown_matches_worked_example() (+9 more)

### Community 37 - "MCPServer"
Cohesion: 0.12
Nodes (17): _hit_to_dict(), _holding_to_dict(), MCPServer, _normalise_symbols(), _optional_bool(), _optional_choice(), _optional_date(), _optional_int() (+9 more)

### Community 38 - "test_logging_setup.py"
Cohesion: 0.09
Nodes (37): BaseException, callback, Context, FileHandler, Logger, _root(), get_logger(), _is_control_flow_exit() (+29 more)

### Community 39 - "analyzer.py"
Cohesion: 0.13
Nodes (31): analyze(), _content_type(), decode_content(), _endpoint_key(), EndpointCandidate, _entries(), find_entries(), _is_sensitive_param() (+23 more)

### Community 40 - "Settings"
Cohesion: 0.05
Nodes (62): BaseSettings, Analyst, Connection, date, The analyst: evidence in, validated commentary out. One class tying the pieces…, One line naming why AI output is missing, or empty when it isn't. Reasons…, LLM commentary over deterministic output. Never a source of numbers., Narrative for one symbol. Bulk tier — this runs once per symbol. (+54 more)

### Community 41 - "add_trading_days"
Cohesion: 0.07
Nodes (26): add_trading_days(), _default_holidays(), _get_holidays(), is_trading_day(), load_holidays(), next_trading_day(), periods_per_year(), previous_trading_day() (+18 more)

### Community 42 - "ReconciledPrice"
Cohesion: 0.06
Nodes (40): adjust_prices(), _consensus(), ReconciledPrice, Cross-source reconciliation. The whole point of pulling the same NEPSE data…, Back-adjust reconciled closes by corporate action factors. For each symbol,…, Return (agreed_value, agreeing_sources, disputed). Greedy clustering: for each…, reconcile_bars(), _within() (+32 more)

### Community 43 - "DailyPipeline"
Cohesion: 0.10
Nodes (22): DailyPipeline, build_corpus(), index_documents(), Write pre-built documents (news, web pages) into the index., Index everything derivable for *symbols* into the document store. ``pipeline``…, pipe(), fixture, _bars() (+14 more)

### Community 44 - "_build_advisor_result"
Cohesion: 0.11
Nodes (20): _advisor_evidence(), _advisor_mode(), _advisor_positions(), _build_advisor_result(), _journal_confidence(), _latest_strategy_panel(), meroshare_holdings_cmd(), _normalise_symbols() (+12 more)

### Community 45 - "_budget"
Cohesion: 0.10
Nodes (13): _budget(), _ok(), Tests for the token budget. The behaviour that matters is the **hard stop**:…, The estimate exists so an overrun is prevented, not just detected., The weekly cap rations successful theses, not failed attempts., A provider stuck in a failure loop must still burn its call allowance., _settings(), TestCallCap (+5 more)

### Community 47 - "types.ts"
Cohesion: 0.08
Nodes (35): fetchJson(), postJson(), AiCacheStats, AiProviderLeg, BacktestRun, BacktestSummary, BulkSignalRow, Confidence (+27 more)

### Community 48 - "screen.py"
Cohesion: 0.20
Nodes (17): best_per_symbol(), Any, Backtest screening: rank strategies across symbols. Runs a panel of strategies…, Collapse a leaderboard to the single best strategy per symbol., Backtest every (symbol, strategy) pair and return a ranked leaderboard.…, screen(), ScreenRow, _strategies() (+9 more)

### Community 49 - "api.py"
Cohesion: 0.14
Nodes (23): FastAPI, advisor_run(), AdvisorRunRequest, backtest_screen(), bulk_stats(), _evidence_builder(), lifespan(), list_jobs() (+15 more)

### Community 50 - "CostEngine"
Cohesion: 0.07
Nodes (36): CostEngine, PaperTrade, field_validator, An executed paper trade with full Nepal cost breakdown., All recorded paper trades in execution order (for portfolio replay)., _Lot, PaperPortfolio, date (+28 more)

### Community 51 - "_to_money"
Cohesion: 0.08
Nodes (37): _advice_id(), advise_auction(), advise_from_plan(), _as_date(), auction_advice_history(), AuctionAdvice, _break_even_bid(), _break_even_exit_price() (+29 more)

### Community 52 - "test_mcp_protocol.py"
Cohesion: 0.11
Nodes (29): parse_message(), A parsed, structurally valid JSON-RPC request or notification., Parse one line of JSON into a :class:`Request`. Raises :class:`RpcError` with…, Request, dispatcher(), _line(), fixture, _raise_rpc_invalid_params() (+21 more)

### Community 53 - "test_meroshare.py"
Cohesion: 0.07
Nodes (39): MeroShareDisabledError, MeroShare integration is switched off in settings., MeroShareTransaction, One demat credit or debit. ``quantity`` is signed: debits are negative., Deterministic id — the portal exposes no stable row identifier. Hashing the…, demat_fingerprint(), demat_last4(), _normalise() (+31 more)

### Community 54 - "MeroShareCredentials"
Cohesion: 0.06
Nodes (32): connect(), connection_disclosure(), ConnectionResult, ensure_enabled(), _first(), OwnDetail, Client, Read-only HTTP client for the user's own MeroShare/CDSC account. **Read-only… (+24 more)

### Community 55 - "test_advisor_doses.py"
Cohesion: 0.09
Nodes (23): dose_history(), DoseError, DoseRun, latest_dose_run(), Any, Connection, ValueError, All four nested doses over one capital pool. (+15 more)

### Community 56 - "Plan: Web UI Dashboard"
Cohesion: 0.06
Nodes (32): Overview, Plan: Web UI Dashboard, Potential Risks & Gotchas, Prerequisites, Rollback Plan, Sprint 1: Backend API, Sprint 2: Frontend Foundation, Sprint 3: Dashboard + Symbols Page (+24 more)

### Community 57 - "test_web_operations.py"
Cohesion: 0.09
Nodes (13): fixture, _bars(), client(), PriceBar, ReconciledPrice, The background job engine and the operations endpoints it drives. Two halves.…, A temp database with one symbol's history, plus matching Settings., A TestClient over the seeded database, with a clean job registry. (+5 more)

### Community 58 - "App.tsx"
Cohesion: 0.07
Nodes (50): react, AiBudget, AiModelsResponse, AiTestResult, BulkSignalsResponse, BulkStatsResponse, HoldingComparison, JournalEntry (+42 more)

### Community 59 - "meroshare/__init__.py"
Cohesion: 0.05
Nodes (55): Dialect, MeroShareError, Exception, Base for every failure in this package. Messages carry no credential., :func:`redact`, plus every account identifier on this instance., import_portfolio(), ImportError_, _match_column() (+47 more)

### Community 60 - "size_position"
Cohesion: 0.11
Nodes (14): exposure_pct(), Risk-managed position sizing, stop-loss, and exposure controls. All functions…, Compute the quantity to buy using fixed-fractional position sizing. Two sizing…, Compute the stop-loss price for a long position. Uses ATR-based or percentage-…, Compute the take-profit price for a long position., Return the fraction of equity deployed in a position (0–100)., size_position(), stop_loss_price() (+6 more)

### Community 61 - "Developers Guide — NEPSE Trader"
Cohesion: 0.08
Nodes (26): 10. Layer: costs and taxes, 11. Layer: paper trading, 12. Layer: RAG, 13. Layer: AI, 14. Layer: advisor, 15. Layer: MeroShare mirror, 16. Layer: health, 17. Surface: CLI (+18 more)

### Community 62 - ".parse_announcements"
Cohesion: 0.13
Nodes (8): Parse the announcements table into documents. Columns are ``S.No | Headline |…, date, parametrize, No known-symbol set needed here — the table states the symbol., Daily re-ingestion must upsert, not accumulate., Sites reflow capitalisation; that must not spawn a duplicate document., TestDeterministicIds, TestParseAnnouncements

### Community 63 - "_run"
Cohesion: 0.10
Nodes (10): Signal, Strategy, mode="normal" ignores the analyst entirely rather than half-using it., Every failure path must yield the full deterministic report plus a banner., It must not raise out of build_rashifal — that is the whole contract., A default deterministic run over three symbols., _run(), TestDegradation (+2 more)

### Community 64 - "_settings"
Cohesion: 0.11
Nodes (12): MonkeyPatch, parametrize, Tests for the runtime Settings model (modes, LLM, budget, RAG, MeroShare).…, Build Settings without reading the developer's real .env., Bulk per-symbol work must not default to a paid provider., claude_cli runs under the user's subscription — no API billing., Env vars are strings; a CSV watchlist must still parse to a list., _settings() (+4 more)

### Community 65 - "main.py"
Cohesion: 0.06
Nodes (73): command, _advisor_horizon(), _advisor_sections(), ai_models(), auction_advise_cmd(), auction_list_cmd(), backtest(), ca_add() (+65 more)

### Community 66 - "PriceBar"
Cohesion: 0.17
Nodes (11): _clamp01(), _clean_indicators(), Signal, Clamp ``x`` into [0, 1] (Signal.strength is validated ``0 <= s <= 1``)., Drop None entries; Signal.indicators is ``dict[str, float]``., Return signals for ``bars`` (chronological ascending)., Return (closes, has_close). ``closes`` carries the last valid close forward…, Convenience: the signal for the last day, or None if none produced. (+3 more)

### Community 67 - "fixtures.ts"
Cohesion: 0.05
Nodes (41): aiBudget, aiModels, aiTestOk, auctionAdvice, backtestRun, bulkSignals, bulkStats, confidence (+33 more)

### Community 68 - "test_ingest_news.py"
Cohesion: 0.24
Nodes (5): extract_symbols(), Symbols mentioned in *text*, in first-seen order. Without a ``known_symbols``…, Tests for news + announcement ingestion. Two things carry this module and are…, No known-symbol set means no tagging — mistagging is worse than nothing., TestExtractSymbols

### Community 69 - "test_pipeline.py"
Cohesion: 0.08
Nodes (25): CostEngine, build_clients(), _construct(), Settings, Storage, Daily orchestration: ingest -> reconcile -> signals -> report. This is the glue…, Instantiate the source clients to run. By default this honours…, SourceClient (+17 more)

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
Cohesion: 0.19
Nodes (12): Any, Path, Config file validation using JSON Schema. Provides validation functions for the…, Validate a single YAML file against its JSON Schema. Returns a (possibly empty)…, _validate(), validate_yaml(), Path, Tests for config file validation. (+4 more)

### Community 74 - "nepse_trader/models.py"
Cohesion: 0.11
Nodes (25): _expected_outcome(), _latest_atr(), Decimal, Deterministic plan cards: the numbers behind the daily prescription. Every…, Wilder ATR over the reconciled history, or None if it can't be computed., PnL at *exit_price*, net of entry costs, exit costs and CGT. The gross figure…, Long-only, event-driven backtester with the full Nepal cost model. The engine…, Nepal equity transaction cost & tax engine. Computes the full, realistic cost… (+17 more)

### Community 75 - "htmlparse.py"
Cohesion: 0.15
Nodes (22): has_header(), Row, Resilient HTML table extraction with a pluggable backend. Two backends produce…, Return the Scrapling Selector class, or None if unavailable., Resolve the effective parse engine name ('scrapling' or 'selectolax')., Return rows of (tag, text) cell tuples for the first table matching…, The text of the ``<td>`` cells in a row (ignoring header ``<th>`` cells)., resolve_engine() (+14 more)

### Community 76 - "compilerOptions"
Cohesion: 0.08
Nodes (23): DOM, src, vite/client, compilerOptions, allowArbitraryExtensions, allowImportingTsExtensions, erasableSyntaxOnly, jsx (+15 more)

### Community 77 - "test_health.py"
Cohesion: 0.10
Nodes (24): health(), Check every moving part: schema, data freshness, sources, RAG, AI, MeroShare.…, check_ai(), check_meroshare(), problems(), Any, Connection, Whether AI mode could actually answer, and how much budget is left. Reads the… (+16 more)

### Community 78 - "SourceClient"
Cohesion: 0.29
Nodes (5): date, Interface every source adapter implements. Concrete clients (ShareSansar,…, SourceClient, FloorsheetEntry, A single matched trade from the floorsheet (transaction-level data).

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

### Community 83 - "get"
Cohesion: 0.07
Nodes (51): get, HTTPException, advisor_doses_latest(), advisor_history(), advisor_latest(), auction_advice_history_endpoint(), auction_latest_endpoint(), backtest_run() (+43 more)

### Community 84 - "Dispatcher"
Cohesion: 0.15
Nodes (12): MethodHandler, Dispatcher, error_response(), Any, JSON-RPC 2.0 framing and dispatch for the MCP server — transport-agnostic. This…, Routes JSON-RPC methods to registered handlers. Deliberately a plain name →…, Dispatch a parsed request. Returns ``None`` for notifications., Parse and dispatch one wire line. Never raises. Returns the response dict to… (+4 more)

### Community 85 - "Document"
Cohesion: 0.07
Nodes (40): _breadth_documents(), _corporate_action_documents(), _documents_for_symbol(), _flush(), IndexReport, _periods(), Corpus construction: walk the database, emit documents, write the index.…, What an indexing run produced. (+32 more)

### Community 86 - ".daily_report"
Cohesion: 0.09
Nodes (15): IngestReport, Any, date, PriceBar, ReconciledPrice, Async variant: fetches from all sources concurrently., Call a client fetch method, isolating its failure to that data type., Reconciled history for a symbol as PriceBars (for indicators). (+7 more)

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

### Community 91 - "rashifal.py"
Cohesion: 0.09
Nodes (25): Persist one dose run and exactly four child rows atomically., save_doses(), _attach_narrative(), build_rashifal(), latest_run(), _note_text(), date, PlanCard (+17 more)

### Community 92 - "SellCandidate"
Cohesion: 0.20
Nodes (8): build_sell_queue(), Which held positions to exit, from the engine's own view of each symbol.…, A held position the engine wants out of, and why., SellCandidate, _bars(), date, PlanCard, TestSellQueue

### Community 93 - ".complete"
Cohesion: 0.20
Nodes (6): Best available answer to *prompt*, or a response explaining the gap. ``task``…, Everything ``ai models`` prints: chains, availability, caps, cache., A refusal, logged in the ledger so the reason survives the run., Provider names to try, in order, for *tier*., A cached provider instance, or None if the name is unknown., The legs of *tier*'s chain that are configured well enough to try.

### Community 94 - "walkforward.py"
Cohesion: 0.21
Nodes (12): _param_grid(), Any, Walk-forward optimisation with expanding or rolling windows. Splits price…, walk_forward(), WFOFold, WFResult, _bars(), Tests for walk-forward optimisation. (+4 more)

### Community 95 - "test_reporting.py"
Cohesion: 0.11
Nodes (29): backtest_report(), Path, ReconciledPrice, Markdown table of reconciled prices, flagging low-confidence / disputed rows., Markdown summary of backtest performance metrics., Write a combined daily report with a top title and one ``##`` per section., Send a plain-text message via Telegram Bot API., Build a GitHub markdown table of signals (pure, exact-text testable). (+21 more)

### Community 96 - "JobBusy"
Cohesion: 0.12
Nodes (23): BaseModel, AiTestRequest, AuctionAdviceRequest, CorporateActionRequest, JobSubmitRequest, JournalDistillRequest, JournalReviewRequest, MeroShareImportRequest (+15 more)

### Community 97 - ".parse_news_list"
Cohesion: 0.21
Nodes (3): Parse a ShareSansar news listing page into news documents. The listing is a…, Fuzzy date parsing would turn "11% dividend" into the 11th of this month., TestParseNewsList

### Community 98 - "_advisor_run_response"
Cohesion: 0.24
Nodes (15): _advisor_run_response(), _attach_dose_cards(), _confidence_response(), _dose_response(), _dose_run_response(), _plan_card_response(), Any, Make persisted and in-memory confidence values share one API shape. Fresh… (+7 more)

### Community 99 - "conftest.py"
Cohesion: 0.14
Nodes (14): Config, Session, _isolate_run_logs(), fixture, Path, pytest_configure(), pytest_runtest_logreport(), pytest_sessionfinish() (+6 more)

### Community 100 - "post"
Cohesion: 0.10
Nodes (24): auction_advice_endpoint(), cancel_job(), journal_distill_endpoint(), _journal_error(), journal_retire_endpoint(), journal_review_endpoint(), journal_score_endpoint(), journal_score_one_endpoint() (+16 more)

### Community 101 - "_settings"
Cohesion: 0.10
Nodes (22): ai_budget(), ai_models(), ai_test(), health_report(), _meroshare_enabled(), _meroshare_settings(), meroshare_status(), meroshare_sync() (+14 more)

### Community 102 - "check_schema"
Cohesion: 0.43
Nodes (3): check_schema(), Every migration in the registry applied, and nothing unknown applied., TestSchema

### Community 103 - "NEPSE Trader — Agent Context"
Cohesion: 0.13
Nodes (14): Completed advisor scope, Current State, Key Design Decisions, NEPSE Trader — Agent Context, Open Questions / Planned, Project, Project Structure, Recent Sprint Progress (+6 more)

### Community 104 - "test_advisor_rashifal.py"
Cohesion: 0.14
Nodes (12): Describe the tape in one phrase, from advancers vs decliners., _regime(), _buys(), conn(), fixture, parametrize, Signal, Tests for the rashifal composer. Two properties matter more than the rest, and… (+4 more)

### Community 105 - "check_freshness"
Cohesion: 0.14
Nodes (15): check_database(), check_freshness(), check_ingest(), date, The database exists, is readable, and holds price rows., How far behind the newest reconciled close is, counted in trading days., The error rate over the most recent ingest attempts, per source., Trading days strictly after *start* up to and including *end*. (+7 more)

### Community 106 - "SourceSpec"
Cohesion: 0.11
Nodes (14): EndpointSpec, SourceSpec, MeroLaganiFundamentalsClient, Fundamentals data scraping from MeroLagani company detail pages., Fetch fundamental data for a single symbol from MeroLagani., Fetch and parse fundamentals for *symbol*., FundamentalData, test_config_driven_urls_override_defaults() (+6 more)

### Community 107 - "TokenBudget"
Cohesion: 0.07
Nodes (19): BudgetSummary, iso_week(), Connection, date, Spend accounting over the ``ai_budget_ledger`` table., ``(billable_calls, billable_tokens)`` for today. Cache hits excluded., Whether one more call fits inside the caps. ``estimated_tokens`` lets a large…, Append one call to the ledger, successful or not. Failures are recorded with… (+11 more)

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

### Community 114 - "NewsClient"
Cohesion: 0.48
Nodes (3): NewsClient, News plus announcements, deduplicated by ``doc_id``., ShareSansar news + announcement listings as retrievable documents.

### Community 115 - "_ensure_app_settings"
Cohesion: 0.13
Nodes (17): _advisor_symbols(), _ensure_app_settings(), get_meroshare_setting(), get_watchlist(), put_meroshare_setting(), put_watchlist(), Effective integration toggle with its DB-or-environment provenance., Persist a local toggle, or clear it with ``{"enabled": null}``. (+9 more)

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

### Community 122 - "Check"
Cohesion: 0.14
Nodes (12): Check, check_journal(), check_paper(), check_rag(), _guarded(), Corpus size, per-kind coverage, and whether ranked search is available., Prediction lifecycle backlog: what is open, scored-but-unreviewed, retired., The replay-derived paper account, if anything was ever traded. (+4 more)

### Community 123 - "NEPSE Trader"
Cohesion: 0.18
Nodes (11): Advisor, journal and MeroShare, Architecture, Daily automation, Data sources & reliability, Disclaimer, Documentation, Install, Nepal cost & tax model (+3 more)

### Community 124 - "test_cli.py"
Cohesion: 0.18
Nodes (3): fixture, CLI smoke tests via Typer's CliRunner (no network)., _temp_db()

### Community 125 - "NEPSE Trader — project skill"
Cohesion: 0.20
Nodes (9): Common tasks → commands, Companion skills, Fetch / parse engines, Hard rules (do not cross), NEPSE Trader — project skill, Setup (once), The once-a-day run (the main thing), When a source breaks (endpoint discovery) (+1 more)

### Community 126 - "test_rag_index.py"
Cohesion: 0.15
Nodes (16): FixtureRequest, has_fts5(), _m0003_rag_documents(), Probe whether this SQLite build has the FTS5 extension compiled in. FTS5 ships…, Document corpus for retrieval, plus an FTS5 index over it when available.…, _conn(), _conn_without_fts(), _corpus() (+8 more)

### Community 127 - "FakeAnalyst"
Cohesion: 0.26
Nodes (6): FakeAnalyst, _note(), Returns valid notes and records every call, so we can assert on inputs., The card already has the engine's action; a second opinion beside it is how a…, TestAIMode, _thesis()

### Community 128 - "config.py"
Cohesion: 0.18
Nodes (13): load_cost_model(), load_sources(), Path, Configuration loading: app settings + source endpoint map + cost model.…, _read_yaml(), SourcesConfig, Validate all config files. Returns list of error messages (empty = OK)., validate_all() (+5 more)

### Community 129 - "Alerter"
Cohesion: 0.11
Nodes (15): Alerter, Response, Pluggable alert backends: Telegram, Discord, SMTP, and generic webhook. Every…, Thin POST wrapper kept separate so tests can monkeypatch it., POST the alert if a webhook is set; return success. No webhook -> False, no…, Send a message to a Discord channel via webhook., Send an email via SMTP. Returns True on success., test_alerter_no_webhook_returns_false_no_network() (+7 more)

### Community 131 - "Per-site capture recipes"
Cohesion: 0.22
Nodes (9): 1. ShareSansar — `sharesansar.har` (PRIMARY), 2. Chukul — `chukul.har` (verify inferred /v1/ paths), 3. MeroLagani — `merolagani.har` (secondary HTML), 4. NepseAlpha — `nepsealpha.har` (TradingView UDF, Cloudflare-gated), 5. NEPSE official — `nepse_official.har` (reference / replay only), HAR Capture Plan — NEPSE data sources, How to capture a HAR (Chrome / Firefox / Edge), Per-site capture recipes (+1 more)

### Community 132 - "Job"
Cohesion: 0.13
Nodes (10): Job, JobStage, _now(), Settings, Storage, A unit of background work and everything the UI needs to render it., Start *kind* in a worker thread and return its job immediately. Raises…, Ask a job to stop. Returns the job, or None when the id is unknown. Cancelling… (+2 more)

### Community 133 - "plugins"
Cohesion: 0.22
Nodes (8): oxc, typescript, warn, plugins, rules, react/only-export-components, react/rules-of-hooks, $schema

### Community 134 - "DoseReport"
Cohesion: 0.15
Nodes (4): DoseReport, Compatibility/reporting view of the four nested doses., Adapt a budgeted report to the persisted ``dose_runs`` contract., _report_as_run()

### Community 135 - "TestExtractResultLinks"
Cohesion: 0.22
Nodes (6): extract_result_links(), Result URLs from the configured search endpoint, best first., Pull outbound result URLs from a search results page. DuckDuckGo's HTML…, Turn a search-engine redirect link into the destination URL., _unwrap_redirect(), TestExtractResultLinks

### Community 136 - "scripts"
Cohesion: 0.25
Nodes (8): scripts, build, coverage, dev, lint, preview, test, test:run

### Community 137 - "NEPSE risk & position sizing — project skill"
Cohesion: 0.29
Nodes (6): Ask the engine for exact costs (don't approximate), Fit-check an existing paper portfolio, Hard rules, Nepal mechanics you MUST respect, NEPSE risk & position sizing — project skill, Sizing protocol (fixed-fractional, R-based)

### Community 138 - "news.py"
Cohesion: 0.27
Nodes (11): _clean(), _headline_key(), _nearby_date(), _news_document(), _parse_date(), date, datetime, News and company announcements — the RAG corpus the database cannot derive.… (+3 more)

### Community 139 - "_DummyStrategy"
Cohesion: 0.38
Nodes (5): _bar(), _buy_sig(), _DummyStrategy, Signal, TestStopLossInBacktest

### Community 140 - "FetchResult"
Cohesion: 0.27
Nodes (4): FetchResult, Any, Ingestion subpackage: per-source clients that fetch PUBLIC market data., retry

### Community 141 - "TestCitations"
Cohesion: 0.31
Nodes (4): normalise_citations(), Coerce whatever the model wrote into ``["[E1]", "[E3]"]`` form. Models write…, A marker only means something if it can match an evidence item., TestCitations

### Community 142 - "NEPSE backtest protocol — project skill"
Cohesion: 0.33
Nodes (5): Hard rules, NEPSE backtest protocol — project skill, Red flags that mean "do not deploy", The protocol (run in order), Why discipline matters on NEPSE specifically

### Community 143 - "TestClient"
Cohesion: 0.31
Nodes (3): parametrize, _settings(), TestClient

### Community 144 - "23. All the settings"
Cohesion: 0.29
Nodes (7): 23. All the settings, AI providers, AI spending caps, Analysis, Fetching politely, Search and MeroShare, Where things live

### Community 145 - "package.json"
Cohesion: 0.40
Nodes (4): name, private, type, version

### Community 146 - "_client"
Cohesion: 0.46
Nodes (4): _client(), mock, A missing news leg costs commentary, never numbers — it must not raise., TestFetch

### Community 147 - "_decide"
Cohesion: 0.23
Nodes (6): _decide(), Signal, Turn the strategy panel's votes into an action, conviction and reasons.…, AVOID exists for the AI vocabulary; the engine has no rule that emits it., _signal(), TestDecide

### Community 148 - "React + TypeScript + Vite"
Cohesion: 0.50
Nodes (3): Expanding the Oxlint configuration, React Compiler, React + TypeScript + Vite

### Community 149 - "Health.tsx"
Cohesion: 0.20
Nodes (10): HealthCheck, HealthReport, HealthSnapshot, HealthStatus, BADGE_VARIANT, CheckRow(), HealthPage(), ICONS (+2 more)

### Community 158 - "ExplodingAnalyst"
Cohesion: 0.29
Nodes (4): RuntimeError, ExplodingAnalyst, A badly-behaved analyst: raises instead of degrading., _raise_runtime()

### Community 170 - "ToolSpec"
Cohesion: 0.29
Nodes (3): One MCP tool: what the model sees, and what runs when it is called.…, The ``tools/list`` representation (handler is not serialisable)., ToolSpec

### Community 171 - "3. Robustness & resilience"
Cohesion: 0.40
Nodes (5): 3.1 Async, concurrent ingestion — **high impact**, `ingest/base.py`, 3.2 Per-source circuit breaker — **medium**, 3.3 Respect `Retry-After` and `robots.txt` programmatically — **medium**, 3.4 Schema-driven HTML parsing — **medium**, `ingest/sharesansar.py`, `merolagani.py`, 3. Robustness & resilience

### Community 172 - "TestSectorOfTheDay"
Cohesion: 0.39
Nodes (3): The sector with the best mean change today. Takes an already-grouped mapping so…, _sector_of_the_day(), TestSectorOfTheDay

### Community 173 - "_drive"
Cohesion: 0.33
Nodes (6): _drive(), Run serve_stdio over StringIO. Returns (responses, raw stdout text)., With explicit streams the loop must leave sys.stdout untouched., test_end_to_end_initialize_list_and_call_over_the_stdio_loop(), test_serve_stdio_does_not_leak_the_real_stdout_rebinding(), test_stdio_loop_returns_cleanly_on_eof()

### Community 174 - "._split_csv"
Cohesion: 0.40
Nodes (3): Any, field_validator, Accept a comma-separated string from env for list-valued settings.

### Community 175 - "PlanCard"
Cohesion: 0.17
Nodes (4): PlanCard, One symbol's prescription. Every field here is engine-computed., DegradingAnalyst, The documented failure mode: returns None and reports why.

### Community 177 - "add_corporate_action"
Cohesion: 0.40
Nodes (6): CorporateAction, add_corporate_action(), _corporate_action_response(), list_corporate_actions(), Stored corporate actions, optionally for one symbol., Record a corporate action by hand. Prices stay as published — this table is the…

### Community 178 - "progress_spinner"
Cohesion: 0.12
Nodes (21): ai_budget(), ai_test(), rag_index(), Build the searchable document corpus from what's already in the database. Runs…, A router over the real database. Opens the DB; caller keeps the Storage., Today's LLM spend against the caps, plus cache size., Send one tiny prompt through a chain and report what answered. This spends real…, Quantitative statistics per symbol over reconciled history. Annualised return &… (+13 more)

### Community 180 - "plan_cards_md"
Cohesion: 0.38
Nodes (4): plan_cards_md(), Render plan cards as one table row per symbol. Cards are…, _card(), TestPlanCardsMd

### Community 181 - "card"
Cohesion: 0.50
Nodes (4): card(), fixture, PlanCard, storage()

### Community 182 - "_seed"
Cohesion: 0.40
Nodes (5): fixture, Write both raw and reconciled bars: tools read from each side., _seed(), server(), storage()

### Community 183 - "conn"
Cohesion: 0.67
Nodes (3): conn(), fixture, Path

### Community 184 - "conn"
Cohesion: 0.67
Nodes (3): conn(), fixture, Path

### Community 185 - "server.py"
Cohesion: 0.14
Nodes (17): Exception, A protocol-level failure that must surface as a JSON-RPC ``error``. Method…, RpcError, build_server(), _json_text(), The MCP server: a declarative tool registry plus the stdio loop. An MCP client…, Construct a fully wired :class:`MCPServer`. Separate from :func:`serve_stdio`…, Resolved I/O plus whether we own (and may therefore guard) real stdout. (+9 more)

### Community 187 - "conn"
Cohesion: 0.67
Nodes (3): conn(), fixture, Path

### Community 188 - "conn"
Cohesion: 0.67
Nodes (3): conn(), fixture, Path

### Community 189 - "do_not_touch_md"
Cohesion: 0.50
Nodes (3): do_not_touch_md(), Render the excluded symbols with their reasons. A symbol missing from the…, TestDoNotTouchMd

### Community 190 - "sell_queue_md"
Cohesion: 0.50
Nodes (3): Render the exit queue: what to sell, why, and the earliest legal date., sell_queue_md(), TestSellQueueMd

## Knowledge Gaps
- **401 isolated node(s):** `Mover`, `BacktestSummary`, `Confidence`, `RagHit`, `JobStatus` (+396 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **28 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Settings` connect `Settings` to `_settings`, `LLMProvider`, `config.py`, `LLMResponse`, `TestExtractResultLinks`, `base.py`, `ResponseCache`, `FetchResult`, `TestCitations`, `parse_into`, `TestExtractJson`, `MeroShareHolding`, `_client`, `test_mcp_server.py`, `TestClient`, `BaseClient`, `MeroShareClient`, `MCPServer`, `ToolSpec`, `DailyPipeline`, `_budget`, `._split_csv`, `TestAdvisor`, `_drive`, `test_meroshare.py`, `MeroShareCredentials`, `_seed`, `server.py`, `TestMeroShareImport`, `meroshare/__init__.py`, `.parse_announcements`, `_settings`, `main.py`, `test_ingest_news.py`, `test_health.py`, `SourceClient`, `TestHtmlToText`, `Document`, `.parse_news_list`, `check_schema`, `check_freshness`, `TokenBudget`, `TestRagSearch`, `Check`?**
  _High betweenness centrality (0.143) - this node is a cross-community bridge._
- **Why does `PriceBar` connect `PriceBar` to `test_rag_corpus.py`, `reporting.py`, `Storage`, `base.py`, `test_nepse_official.py`, `SourceName`, `_DummyStrategy`, `test_strategies.py`, `MeroShareHolding`, `test_mcp_server.py`, `test_properties.py`, `outcomes.py`, `Backtester`, `ChukulClient`, `build_plan_card`, `NepseAlphaClient`, `merolagani.py`, `ReconciledPrice`, `DailyPipeline`, `screen.py`, `CostEngine`, `_seed`, `test_pipeline.py`, `SmaCrossStrategy`, `nepse_trader/models.py`, `test_health.py`, `SourceClient`, `Document`, `SellCandidate`, `walkforward.py`, `test_reporting.py`, `test_advisor_rashifal.py`, `check_freshness`, `test_cli_advisor.py`?**
  _High betweenness centrality (0.051) - this node is a cross-community bridge._
- **Why does `Storage` connect `Storage` to `LLMProvider`, `Path`, `SourceName`, `ResponseCache`, `MeroShareHolding`, `test_mcp_server.py`, `journal.py`, `ExplodingAnalyst`, `migrations.py`, `Settings`, `ToolSpec`, `ReconciledPrice`, `_build_advisor_result`, `TestSectorOfTheDay`, `_budget`, `PlanCard`, `DailyPipeline`, `progress_spinner`, `CostEngine`, `card`, `_seed`, `test_advisor_doses.py`, `conn`, `server.py`, `conn`, `conn`, `conn`, `test_meroshare.py`, `_run`, `main.py`, `test_pipeline.py`, `nepse_trader/models.py`, `test_health.py`, `rashifal.py`, `SellCandidate`, `test_advisor_rashifal.py`, `check_freshness`, `test_cli_advisor.py`, `FakeAnalyst`?**
  _High betweenness centrality (0.048) - this node is a cross-community bridge._
- **Are the 140 inferred relationships involving `Settings` (e.g. with `Analyst` and `BudgetStatus`) actually correct?**
  _`Settings` has 140 INFERRED edges - model-reasoned connections that need verification._
- **Are the 75 inferred relationships involving `Document` (e.g. with `JournalError` and `Prediction`) actually correct?**
  _`Document` has 75 INFERRED edges - model-reasoned connections that need verification._
- **Are the 54 inferred relationships involving `DocumentIndex` (e.g. with `JournalError` and `Prediction`) actually correct?**
  _`DocumentIndex` has 54 INFERRED edges - model-reasoned connections that need verification._
- **Are the 13 inferred relationships involving `Storage` (e.g. with `_Result` and `DegradingAnalyst`) actually correct?**
  _`Storage` has 13 INFERRED edges - model-reasoned connections that need verification._