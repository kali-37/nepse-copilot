import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { api } from './client';
import { server } from '../test/server';
import * as fx from '../test/fixtures';

/**
 * Records the URLs (and methods/headers) the client actually requests for a
 * given pattern, and replies with `body`.
 */
function capture(
  method: 'get' | 'post',
  pattern: string,
  body: Parameters<typeof HttpResponse.json>[0] = {}
): { urls: string[]; requests: Request[] } {
  const urls: string[] = [];
  const requests: Request[] = [];
  server.use(
    http[method](pattern, ({ request }) => {
      urls.push(request.url);
      requests.push(request);
      return HttpResponse.json(body);
    })
  );
  return { urls, requests };
}

/** The path + query the client asked for, with the jsdom origin stripped. */
function pathOf(url: string): string {
  const u = new URL(url);
  return `${u.pathname}${u.search}`;
}

describe('api client — URL construction', () => {
  it('prefixes every request with /api', async () => {
    const { urls } = capture('get', '*/api/health', { status: 'ok' });
    await api.health();
    expect(pathOf(urls[0])).toBe('/api/health');
  });

  it('requests /api/dashboard', async () => {
    const { urls } = capture('get', '*/api/dashboard', fx.dashboardStats);
    await api.dashboard();
    expect(pathOf(urls[0])).toBe('/api/dashboard');
  });

  it('requests /api/symbols', async () => {
    const { urls } = capture('get', '*/api/symbols', fx.symbols);
    await api.symbols();
    expect(pathOf(urls[0])).toBe('/api/symbols');
  });

  it('sends an Accept: application/json header', async () => {
    const { requests } = capture('get', '*/api/dashboard', fx.dashboardStats);
    await api.dashboard();
    expect(requests[0].headers.get('Accept')).toBe('application/json');
  });

  it('uses POST for ingest and GET elsewhere', async () => {
    const post = capture('post', '*/api/ingest', { total_bars: 0 });
    const get = capture('get', '*/api/dashboard', fx.dashboardStats);
    await api.ingest();
    await api.dashboard();
    expect(post.requests[0].method).toBe('POST');
    expect(get.requests[0].method).toBe('GET');
  });
});

describe('api client — query-param encoding', () => {
  it('omits the query string for marketBreadth with no date', async () => {
    const { urls } = capture('get', '*/api/market-breadth', fx.marketBreadth);
    await api.marketBreadth();
    expect(pathOf(urls[0])).toBe('/api/market-breadth');
  });

  it('adds business_date for marketBreadth when given', async () => {
    const { urls } = capture('get', '*/api/market-breadth', fx.marketBreadth);
    await api.marketBreadth('2026-08-22');
    expect(pathOf(urls[0])).toBe('/api/market-breadth?business_date=2026-08-22');
  });

  it('defaults movers to top=5', async () => {
    const { urls } = capture('get', '*/api/movers', fx.movers);
    await api.movers();
    expect(pathOf(urls[0])).toBe('/api/movers?top=5');
  });

  it('serialises both movers params', async () => {
    const { urls } = capture('get', '*/api/movers', fx.movers);
    await api.movers(10, '2026-08-22');
    expect(pathOf(urls[0])).toBe('/api/movers?top=10&business_date=2026-08-22');
  });

  it('omits the query string for symbolPrices with no options', async () => {
    const { urls } = capture('get', '*/api/symbols/:symbol/prices', fx.prices);
    await api.symbolPrices('NABIL');
    expect(pathOf(urls[0])).toBe('/api/symbols/NABIL/prices');
  });

  it('serialises start, end and limit for symbolPrices', async () => {
    const { urls } = capture('get', '*/api/symbols/:symbol/prices', fx.prices);
    await api.symbolPrices('NABIL', {
      start: '2026-01-01',
      end: '2026-08-22',
      limit: 500,
    });
    expect(pathOf(urls[0])).toBe(
      '/api/symbols/NABIL/prices?start=2026-01-01&end=2026-08-22&limit=500'
    );
  });

  it('includes only the options that were supplied', async () => {
    const { urls } = capture('get', '*/api/symbols/:symbol/prices', fx.prices);
    await api.symbolPrices('NABIL', { limit: 100 });
    expect(pathOf(urls[0])).toBe('/api/symbols/NABIL/prices?limit=100');
  });

  it('drops limit=0 because the guard is truthiness-based', async () => {
    // Characterises current behaviour: `if (opts?.limit)` treats 0 as absent.
    const { urls } = capture('get', '*/api/symbols/:symbol/prices', fx.prices);
    await api.symbolPrices('NABIL', { limit: 0 });
    expect(pathOf(urls[0])).toBe('/api/symbols/NABIL/prices');
  });

  it('percent-encodes symbols in the path', async () => {
    const { urls } = capture('get', '*/api/symbols/*', fx.prices);
    await api.symbolPrices('A/B C&D');
    expect(pathOf(urls[0])).toBe('/api/symbols/A%2FB%20C%26D/prices');
  });

  it('defaults symbolSignals to the sma_cross strategy', async () => {
    const { urls } = capture('get', '*/api/symbols/:symbol/signals', fx.signals);
    await api.symbolSignals('NABIL');
    expect(pathOf(urls[0])).toBe('/api/symbols/NABIL/signals?strategy=sma_cross');
  });

  it('encodes a custom signal strategy', async () => {
    const { urls } = capture('get', '*/api/symbols/:symbol/signals', fx.signals);
    await api.symbolSignals('NABIL', 'rsi reversion&v2');
    expect(pathOf(urls[0])).toBe(
      '/api/symbols/NABIL/signals?strategy=rsi%20reversion%26v2'
    );
  });

  it('builds the quant and fundamentals paths', async () => {
    const quant = capture('get', '*/api/symbols/:symbol/quant', fx.quantStats);
    const funda = capture(
      'get',
      '*/api/symbols/:symbol/fundamentals',
      fx.fundamentals
    );
    await api.symbolQuant('NABIL');
    await api.symbolFundamentals('NABIL');
    expect(pathOf(quant.urls[0])).toBe('/api/symbols/NABIL/quant');
    expect(pathOf(funda.urls[0])).toBe('/api/symbols/NABIL/fundamentals');
  });

  it('defaults portfolio cash to 100000', async () => {
    const { urls } = capture('get', '*/api/portfolio', fx.portfolio);
    await api.portfolio();
    expect(pathOf(urls[0])).toBe('/api/portfolio?cash=100000');
  });

  it('passes an explicit portfolio cash value, including 0', async () => {
    const { urls } = capture('get', '*/api/portfolio', fx.portfolio);
    await api.portfolio(0);
    expect(pathOf(urls[0])).toBe('/api/portfolio?cash=0');
  });

  it('sends no query params for backtestScreen with no options', async () => {
    // The client appends a bare `?`; an empty query normalises away in the URL.
    const { urls } = capture('get', '*/api/backtest/screen', fx.screenRows);
    await api.backtestScreen();
    expect(pathOf(urls[0])).toBe('/api/backtest/screen');
  });

  it('serialises all backtestScreen options', async () => {
    const { urls } = capture('get', '*/api/backtest/screen', fx.screenRows);
    await api.backtestScreen({
      strategies: 'sma_cross,rsi_reversion',
      cash: 100_000,
      min_bars: 60,
      rank_by: 'sharpe',
      top: 50,
    });
    expect(pathOf(urls[0])).toBe(
      '/api/backtest/screen?strategies=sma_cross%2Crsi_reversion&cash=100000&min_bars=60&rank_by=sharpe&top=50'
    );
  });

  it('defaults backtestRun strategy and cash', async () => {
    const { urls } = capture('get', '*/api/backtest/run', fx.backtestRun);
    await api.backtestRun('NABIL');
    expect(pathOf(urls[0])).toBe(
      '/api/backtest/run?symbol=NABIL&strategy=sma_cross&cash=100000'
    );
  });

  it('encodes backtestRun symbol and strategy', async () => {
    const { urls } = capture('get', '*/api/backtest/run', fx.backtestRun);
    await api.backtestRun('A&B', 'my strategy', 5000);
    expect(pathOf(urls[0])).toBe(
      '/api/backtest/run?symbol=A%26B&strategy=my%20strategy&cash=5000'
    );
  });

  it('sends all_sources and async flags for ingest', async () => {
    const { urls } = capture('post', '*/api/ingest', { total_bars: 0 });
    await api.ingest('2026-08-22', false, true);
    expect(pathOf(urls[0])).toBe(
      '/api/ingest?business_date=2026-08-22&all_sources=false&async=true'
    );
  });

  it('defaults ingest flags and omits the date when absent', async () => {
    const { urls } = capture('post', '*/api/ingest', { total_bars: 0 });
    await api.ingest();
    expect(pathOf(urls[0])).toBe('/api/ingest?all_sources=true&async=false');
  });
});

describe('api client — JSON parsing', () => {
  it('returns the parsed object body', async () => {
    await expect(api.dashboard()).resolves.toEqual(fx.dashboardStats);
  });

  it('returns the parsed array body', async () => {
    await expect(api.symbols()).resolves.toEqual(fx.symbols);
  });

  it('preserves nulls rather than coercing them', async () => {
    server.use(
      http.get('*/api/market-breadth', () =>
        HttpResponse.json(fx.emptyMarketBreadth)
      )
    );
    const breadth = await api.marketBreadth();
    expect(breadth.avg_confidence).toBeNull();
    expect(breadth.symbols).toBe(0);
  });

  it('returns nested structures intact', async () => {
    const run = await api.backtestRun('NABIL');
    expect(run.summary.sharpe).toBe(0.658);
    expect(run.equity_curve).toHaveLength(3);
    expect(run.equity_curve[0]).toEqual(['2026-08-20', 138_000]);
  });

  it('returns an empty array as an empty array', async () => {
    server.use(http.get('*/api/symbols', () => HttpResponse.json([])));
    await expect(api.symbols()).resolves.toEqual([]);
  });
});

describe('api client — error paths', () => {
  it('rejects on a 500 and includes the status and body', async () => {
    server.use(
      http.get(
        '*/api/dashboard',
        () => new HttpResponse('database is locked', { status: 500 })
      )
    );
    await expect(api.dashboard()).rejects.toThrow(/500/);
    await expect(api.dashboard()).rejects.toThrow(/database is locked/);
  });

  it('rejects on a 404 with the FastAPI detail body', async () => {
    server.use(
      http.get('*/api/symbols/:symbol/quant', () =>
        HttpResponse.json({ detail: 'No quant data for NABIL' }, { status: 404 })
      )
    );
    await expect(api.symbolQuant('NABIL')).rejects.toThrow(
      /404.*No quant data for NABIL/
    );
  });

  it('rejects on a 400 from the signals endpoint', async () => {
    server.use(
      http.get('*/api/symbols/:symbol/signals', () =>
        HttpResponse.json({ detail: 'unknown strategy' }, { status: 400 })
      )
    );
    await expect(api.symbolSignals('NABIL', 'nope')).rejects.toThrow(/400/);
  });

  it('rejects on a 502 from the fundamentals upstream', async () => {
    server.use(
      http.get('*/api/symbols/:symbol/fundamentals', () =>
        HttpResponse.json({ detail: 'Fundamentals fetch failed' }, { status: 502 })
      )
    );
    await expect(api.symbolFundamentals('NABIL')).rejects.toThrow(/502/);
  });

  it('omits the trailing colon when the error body is empty', async () => {
    server.use(
      http.get('*/api/dashboard', () => new HttpResponse(null, { status: 503 }))
    );
    await expect(api.dashboard()).rejects.toThrow(
      // no `: body` suffix when there is no body
      /^503(?! ?:)[^:]*$/
    );
  });

  it('rejects with an Error instance, not a raw value', async () => {
    server.use(
      http.get('*/api/dashboard', () => new HttpResponse('x', { status: 500 }))
    );
    await expect(api.dashboard()).rejects.toBeInstanceOf(Error);
  });

  it('rejects when the network fails', async () => {
    server.use(http.get('*/api/dashboard', () => HttpResponse.error()));
    await expect(api.dashboard()).rejects.toThrow();
  });

  it('rejects when a 2xx body is malformed JSON', async () => {
    server.use(
      http.get(
        '*/api/dashboard',
        () =>
          new HttpResponse('<html>not json</html>', {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          })
      )
    );
    await expect(api.dashboard()).rejects.toThrow();
  });

  it('rejects when a 2xx body is empty', async () => {
    server.use(
      http.get('*/api/dashboard', () => new HttpResponse('', { status: 200 }))
    );
    await expect(api.dashboard()).rejects.toThrow();
  });

  it('does not treat a 204 as a successful parse', async () => {
    server.use(
      http.get('*/api/dashboard', () => new HttpResponse(null, { status: 204 }))
    );
    await expect(api.dashboard()).rejects.toThrow();
  });

  it('surfaces errors from POST /api/ingest too', async () => {
    server.use(
      http.post(
        '*/api/ingest',
        () => new HttpResponse('scraper blocked', { status: 500 })
      )
    );
    await expect(api.ingest()).rejects.toThrow(/500.*scraper blocked/);
  });
});
