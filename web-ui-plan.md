# Plan: Web UI Dashboard

**Generated**: 2026-07-22
**Estimated Complexity**: High

## Overview

Add a React single-page application (SPA) backed by a FastAPI REST server to
the NEPSE Trader project. The web UI surfaces the same data the CLI exposes
— market breadth, symbol OHLCV charts, portfolio, backtest leaderboard —
through a modern responsive interface with interactive charts, dark/light
theme, and real-time data refresh.

**Architecture**:
```
browser (React SPA)  ←→  FastAPI (/:5000)
                              |
                         Storage / Pipeline
                              |
                           SQLite DB
```

The FastAPI server reads the DB directly (read-only queries + an
`/api/ingest` trigger that calls Pipeline). The React app is built with Vite
and served from FastAPI as static files in production; during dev the Vite
dev-server proxies API calls to FastAPI.

## Prerequisites

- Python 3.11+
- Node.js 20+ / npm (for frontend build)
- FastAPI + uvicorn added to `pyproject.toml` core deps
- pydantic models already exist for all data shapes

## Sprint 1: Backend API

**Goal**: FastAPI server exposing all data endpoints the dashboard needs,
plus optional CORS for dev-mode hot-reload.

**Demo/Validation**:
```bash
pip install -e .  &&  uvicorn nepse_trader.web.api:app --reload
curl http://localhost:8000/api/dashboard
```

### Task 1.1: Add FastAPI + uvicorn deps
- **Files**: `pyproject.toml`
- Add `fastapi>=0.115`, `uvicorn[standard]>=0.32` to `[project] dependencies
- Run `pip install -e .` to install

### Task 1.2: Create FastAPI app skeleton
- **Files**: `nepse_trader/web/__init__.py`, `nepse_trader/web/api.py`
- Create the package
- Instantiate `FastAPI(title="NEPSE Trader API", version="0.1.0")`
- Add CORS middleware (allow `http://localhost:5173` in dev)
- Add lifespan context manager that creates Storage once
- Endpoint test: `GET /api/health` → `{"status": "ok"}`

### Task 1.3: Dashboard + symbols endpoints
- **Files**: `nepse_trader/web/api.py`
- `GET /api/dashboard` → `Storage.db_stats()`
- `GET /api/market-breadth?date=YYYY-MM-DD` → `Pipeline.market_breadth()`
- `GET /api/movers?date=YYYY-MM-DD&top=5` → `Pipeline.top_movers()`
- `GET /api/symbols` → `list[str]` from `Storage.symbols()`

### Task 1.4: Symbol detail endpoints
- **Files**: `nepse_trader/web/api.py`
- `GET /api/symbols/{symbol}/prices` → `Storage.reconciled_history()`
- `GET /api/symbols/{symbol}/signals?strategy=sma_cross` → `Pipeline.signals_for()`
- `GET /api/symbols/{symbol}/quant` → `Pipeline.quant_stats()`
- `GET /api/symbols/{symbol}/fundamentals` → `MeroLaganiFundamentalsClient.fetch_fundamentals()`

### Task 1.5: Portfolio + backtest endpoints
- **Files**: `nepse_trader/web/api.py`
- `GET /api/portfolio?cash=100000` → `PaperPortfolio.to_dict()`
- `GET /api/backtest/screen` — query params for strategies, cash, min_bars, rank_by → `Pipeline.screen_strategies()`
- `GET /api/backtest/run?symbol=X&strategy=sma_cross&cash=100000` → single backtest

### Task 1.6: Ingest trigger endpoint
- `POST /api/ingest?date=YYYY-MM-DD` → `Pipeline.ingest()` (or async variant), returns `IngestReport.as_dict()`
- Protected by a simple configurable API key header

### Task 1.7: API tests
- **Files**: `tests/test_web_api.py`
- Mock Storage/Pipeline, use `TestClient` from FastAPI
- Test each endpoint: status code, response shape, empty-db edge cases
- 1 test per endpoint minimum

## Sprint 2: Frontend Foundation

**Goal**: Vite + React + TypeScript project with routing, theme, and the
core page shell. No data integration yet — just the UI skeleton.

**Demo/Validation**:
```bash
cd web  &&  npm run dev
# opens http://localhost:5173 — see nav + empty pages
```

### Task 2.1: Scaffold Vite React project + install deps
- **Dir**: `web/` (project root sibling of `nepse_trader/`)
- `npm create vite@latest web -- --template react-ts`
- Install: `react-router-dom`, `recharts`, `lucide-react` (icons), `clsx`
- Install dev deps: `tailwindcss`, `@tailwindcss/vite`, `@types/react`, `@types/react-router-dom`

### Task 2.2: Tailwind design system
- **Files**: `web/src/index.css`, `web/src/App.tsx`
- Configure Tailwind with custom design tokens (colors, spacing, border-radius)
- Dark mode via `class` strategy (toggled via button)
- Global CSS: CSS custom properties for chart colours, consistent spacing scale
- Base layout: sidebar nav (collapsible on mobile) + main content area

### Task 2.3: App shell + routing
- **Files**: `web/src/App.tsx`, `web/src/layouts/RootLayout.tsx`, `web/src/pages/*.tsx`
- Pages: `Dashboard`, `Symbols`, `SymbolDetail`, `Portfolio`, `Backtest`
- React Router v7 flat routes:
  - `/` → Dashboard
  - `/symbols` → Symbols list
  - `/symbols/:symbol` → Symbol detail
  - `/portfolio` → Portfolio
  - `/backtest` → Backtest
- RootLayout: sidebar with nav links, header with theme toggle + API status indicator

### Task 2.4: Shared UI components
- **Files**: `web/src/components/ui/` — `Card`, `Badge`, `Table`, `StatCard`, `LoadingSpinner`, `ErrorState`
- Consistent styling via Tailwind + clsx
- Loading/empty/error states for every component
- DataTable with sortable columns (for leaderboard, signals, etc.)

## Sprint 3: Dashboard + Symbols Page

**Goal**: Wire up data fetching, show live data on the dashboard overview
and symbols pages. Interactive charts for symbol detail.

**Demo/Validation**:
- Dashboard shows real DB stats + market breadth
- Symbols list is populated from API
- Symbol detail shows OHLCV chart + signals + fundamentals

### Task 3.1: API client layer
- **Files**: `web/src/api/client.ts`, `web/src/api/types.ts`
- Thin `fetch`-based wrapper around all `/api/*` endpoints
- TypeScript interfaces matching API response shapes (generated from pydantic models manually)
- Error handling: network errors → `ErrorState`; empty data → empty state

### Task 3.2: Dashboard page
- **Files**: `web/src/pages/Dashboard.tsx`
- Stat cards row: symbols, sources, bars reconciled, DB size, latest date
- Market breadth card: advancers/decliners/unchanged in a horizontal bar
- Ingest log: mini-table of last 10 runs
- Top movers: gainers + losers side by side
- Auto-refresh every 60s

### Task 3.3: Symbols list page
- **Files**: `web/src/pages/Symbols.tsx`
- Search/filter input (filters client-side by symbol text)
- DataTable: Symbol, Latest Close, Change %, Volume, Actions (→ detail)
- Pagination if > 100 symbols

### Task 3.4: Symbol detail page
- **Files**: `web/src/pages/SymbolDetail.tsx`, `web/src/components/charts/OHLCVChart.tsx`
- Price chart (OHLCV candlestick or line chart) using Recharts
- Time range selector: 1M / 3M / 6M / 1Y / ALL
- Signals table for the symbol
- Quant stats section (Sharpe, Sortino, VaR, MaxDD, etc.)
- Fundamentals section (EPS, PE, PBV, market cap, 52W high/low)

## Sprint 4: Portfolio + Backtest Pages

**Goal**: Portfolio overview and interactive backtest leaderboard.

**Demo/Validation**:
- Portfolio shows holdings, P&L, trade history
- Backtest page shows leaderboard, can filter/rank

### Task 4.1: Portfolio page
- **Files**: `web/src/pages/Portfolio.tsx`
- Summary cards: Cash, Equity, Realized PnL, Unrealized PnL, Total Return %
- Holdings table: Symbol, Qty, Avg Cost, Current Price, Market Value, P&L
- Trade history table: Date, Side, Symbol, Qty, Price, Net Amount
- Equity curve chart (line chart of portfolio value over time)

### Task 4.2: Backtest leaderboard page
- **Files**: `web/src/pages/Backtest.tsx`
- Parameter panel: strategies (multi-select), cash, min bars, rank by
- "Run" button triggers screen → shows spinner → results
- Leaderboard table with sortable columns
- Click a row → expand detail (symbol + strategy backtest summary)
- Best-per-symbol toggle

## Sprint 5: Polish & Production

**Goal**: Dark mode, responsive layout, FastAPI serves built frontend, tests
pass end-to-end.

**Demo/Validation**:
- `docker compose up` or `uvicorn nepse_trader.web.api:app` → working app
- Dark/light toggle persists
- Mobile layout works
- All tests pass

### Task 5.1: Dark mode
- Theme toggle in header
- Persist preference in `localStorage`
- Tailwind `dark:` variants on all pages

### Task 5.2: Responsive layout
- Sidebar collapses to bottom nav on <768px
- Charts resize to container
- Tables horizontally scrollable on mobile

### Task 5.3: FastAPI serves built frontend
- **Files**: `nepse_trader/web/api.py` — add static file mount for `web/dist/`
- Add `npm run build` to CI or developer workflow docs
- Fallback to `index.html` for client-side routing

### Task 5.4: Integration test
- **Files**: `tests/test_web_integration.py`
- Build frontend, start server with TestClient, verify HTML response for `/`
- Use `respix` to mock external APIs for ingest endpoint test

## Testing Strategy

- **Backend**: `pytest` + FastAPI `TestClient`, mock Storage via dependency
  override, 1+ test per endpoint.
- **Frontend**: Manual verification in browser during dev; consider
  `vitest` + React Testing Library for critical components later.
- **End-to-end**: Build frontend → serve from FastAPI → curl key pages.

## Potential Risks & Gotchas

- **npm version mismatch**: Current env has npm v12 which warns about Node
  v20. Install a compatible npm version (`npm i -g npm@10`) or use npx.
- **DB is read-only during dashboard use**: Storage creates one connection.
  The FastAPI app must share the connection carefully (not per-request) to
  avoid WAL lock contention. Use a single Storage instance in the lifespan.
- **Async vs sync**: FastAPI is async by default; Storage methods are sync.
  Use `run_in_executor` or FastAPI's `async def` + `def` route separation
  (FastAPI automatically runs sync `def` routes in a threadpool).
- **Vite proxy in dev**: Must proxy `/api/*` to `http://localhost:8000` to
  avoid CORS issues during hot-reload. Configure in `vite.config.ts`.
- **Large OHLCV datasets**: A symbol with years of daily data could return
  1000+ rows. The `/api/symbols/{symbol}/prices` endpoint should accept
  `?limit=500&offset=0` or use the time-range filter from the frontend.
- **Fundamentals requires network**: The fundamentals endpoint calls
  MeroLagani live. Cache results in the DB or handle timeout/errors gracefully.

## Rollback Plan

- Each commit is atomic; revert individual commits with `git revert`.
- Frontend is in `web/` — delete the directory to remove it entirely.
- FastAPI deps: revert `pyproject.toml` additions.
