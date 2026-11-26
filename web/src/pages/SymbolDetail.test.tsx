import { describe, expect, it } from 'vitest';
import { http, HttpResponse, delay } from 'msw';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SymbolDetailPage } from './SymbolDetail';
import { renderWithProviders } from '../test/renderWithProviders';
import { server } from '../test/server';
import * as fx from '../test/fixtures';

/** SymbolDetail reads :symbol from the route, so every render supplies one. */
function renderDetail(symbol = 'NABIL') {
  return renderWithProviders(<SymbolDetailPage />, {
    route: `/symbols/${symbol}`,
    path: '/symbols/:symbol',
  });
}

describe('SymbolDetailPage', () => {
  it('renders without crashing', () => {
    expect(() => renderDetail()).not.toThrow();
  });

  it('takes the symbol from the route param and upper-cases it', async () => {
    renderDetail('nabil');
    expect(
      await screen.findByRole('heading', { level: 1, name: 'NABIL' })
    ).toBeInTheDocument();
  });

  it('shows a loading state before the data arrives', async () => {
    server.use(
      http.get('*/api/symbols/:symbol/prices', async () => {
        await delay(50);
        return HttpResponse.json(fx.prices);
      })
    );
    renderDetail();
    expect(screen.getByText('Loading NABIL data...')).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByText('Price history')).toBeInTheDocument()
    );
  });

  it('renders the happy path: price, signals, quant stats and fundamentals', async () => {
    renderDetail();

    expect(
      await screen.findByRole('heading', { level: 1, name: 'NABIL' })
    ).toBeInTheDocument();
    expect(screen.getByText('Nabil Bank Limited')).toBeInTheDocument();

    // Latest close 1275 with +2.00% vs the previous close of 1250.
    expect(screen.getByText('NPR 1275.00')).toBeInTheDocument();
    expect(screen.getByText('+2.00%')).toBeInTheDocument();

    // Signals panel.
    expect(screen.getByText('Signals')).toBeInTheDocument();
    expect(screen.getByText('BUY')).toBeInTheDocument();
    expect(screen.getByText('HOLD')).toBeInTheDocument();
    expect(screen.getByText('NPR 1250.00')).toBeInTheDocument();
    expect(screen.getByText('NPR 1272.50')).toBeInTheDocument();

    // Quant panel.
    expect(screen.getByText('Quantitative stats')).toBeInTheDocument();
    expect(screen.getByText('42.18%')).toBeInTheDocument();
    expect(screen.getByText('0.658')).toBeInTheDocument();
    expect(screen.getByText('-31.44%')).toBeInTheDocument();

    // Fundamentals panel.
    expect(screen.getByText('Provider fundamentals')).toBeInTheDocument();
    expect(screen.getByText('Commercial Banks')).toBeInTheDocument();
    expect(screen.getByText('NPR 1280.00')).toBeInTheDocument();
    expect(screen.getByText('43.21')).toBeInTheDocument();
    expect(screen.getByText('29.51')).toBeInTheDocument();
    // 2.15e10 / 1e7 => 2150.0Cr
    expect(screen.getByText('NPR 2150.0Cr')).toBeInTheDocument();

    // The chart container renders; recharts SVG internals are not asserted.
    expect(screen.queryByText('No price data')).not.toBeInTheDocument();
  });

  it('shows statement provenance and unknown checks next to the provider snapshot', async () => {
    const source = 'https://www.nabilbank.com/reports/annual.pdf';
    const hash = 'a'.repeat(64);
    server.use(http.get('*/api/decisions/fundamentals/:symbol', () => HttpResponse.json({
      asset_kind: 'stock', source: 'Official issuer document excerpts', snapshot_date: '2026-11-24',
      rating: 'supported', eps: 30, book_value: 200, current_pe: 25.5, current_pbv: 2.55,
      multiplier: 1, needs_refresh: false, reasons: [], limitations: [],
      verification: {
        status: 'matched_official_excerpt', period_start: '2025-07-16', period_end: '2026-07-15',
        period_basis: 'annual', available_at: '2026-11-22T03:00:00Z', matched_metrics: ['eps', 'book_value'],
        missing_metrics: ['npl_pct'], conflicts: [],
        source_documents: [{ evidence_id: 'official-a', source_url: source, source_kind: 'issuer', document_sha256: hash,
          available_at: '2026-11-22T03:00:00Z', published_on: '2026-08-10', verified_at: '2026-11-22T03:00:00Z' }],
        note: 'The issuer’s statement supplies the matched values.',
      },
      financial_checks: [
        { metric: 'eps', label: 'Earnings per share', value: 30, unit: 'NPR_per_share', verdict: 'pass', reason: 'Positive reported earnings.' },
        { metric: 'npl_pct', label: 'Non-performing loans', value: null, unit: null, verdict: 'unknown', reason: 'Official evidence unavailable.' },
      ],
    })));
    renderDetail();

    expect(await screen.findByText('Matched official evidence')).toBeInTheDocument();
    expect(screen.getByText(/2 matched metrics · 1 required item missing/)).toBeInTheDocument();
    await userEvent.click(screen.getByText('Financial checks & sources'));
    expect(screen.getByText('Non-performing loans')).toBeVisible();
    expect(screen.getByText('Unknown')).toBeVisible();
    expect(screen.getByRole('link', { name: /Open source document/ })).toHaveAttribute('href', source);
    expect(screen.getByText(hash)).toBeVisible();
    expect(screen.getByText('Issuer statement')).toBeVisible();
    expect(screen.getByText('Provider fundamentals')).toBeInTheDocument();
  });

  it.each(['short_history', 'missing_statistics'])('keeps fund analysis visible with %s', async scenario => {
    const missing = scenario === 'short_history'
      ? { skewness: null, kurtosis: null }
      : { total_return_pct: null, annualized_return_pct: null, annualized_vol_pct: null,
        sharpe: null, sortino: null, max_drawdown_pct: null, skewness: null,
        kurtosis: null, var_95_pct: null };
    server.use(
      http.get('*/api/symbols/:symbol/quant', () => HttpResponse.json({ ...fx.quantStats, symbol: 'MNMF2', n: 3, ...missing })),
      http.get('*/api/symbols/:symbol/fundamentals', () => HttpResponse.json({ ...fx.fundamentals,
        company_name: 'Muktinath Mutual Fund 2', sector: 'Mutual Fund', eps: 0, book_value: 0 })),
      http.get('*/api/decisions/fundamentals/:symbol', () => HttpResponse.json({
        asset_kind: 'mutual_fund', rating: 'fund_review', source: 'Public snapshot',
        snapshot_date: '2026-11-25', eps: null, book_value: null, current_pe: null,
        current_pbv: null, multiplier: 0, needs_refresh: false,
        reasons: ['Dated NAV and fund terms need review.'], limitations: ['NAV is not verified.'],
      }))
    );
    renderDetail('MNMF2');

    expect(await screen.findByText('Mutual fund · valuation review needed')).toBeInTheDocument();
    expect(screen.getByText('Dated NAV and fund terms need review.')).toBeInTheDocument();
    expect(screen.queryByText('EPS')).not.toBeInTheDocument();
    expect(screen.queryByText(/deterioration/)).not.toBeInTheDocument();
    const skewness = screen.getByText('Skewness').parentElement!;
    expect(within(skewness).getByText('—')).toBeInTheDocument();
    expect(within(skewness).queryByText('0.000')).not.toBeInTheDocument();
    if (scenario === 'missing_statistics') {
      for (const label of ['Total Return', 'Ann. Return', 'Ann. Volatility', 'Sharpe', 'Sortino', 'Max Drawdown', 'VaR (95%)']) {
        expect(within(screen.getByText(label).parentElement!).getByText('—')).toBeInTheDocument();
      }
    }
  });

  it('highlights a large drawdown reported as a positive loss magnitude', async () => {
    server.use(http.get('*/api/symbols/:symbol/quant', () => HttpResponse.json({ ...fx.quantStats, max_drawdown_pct: 31.44 })));
    renderDetail();
    expect(await screen.findByText('31.44%')).toHaveClass('text-negative');
  });

  it('renders empty states when every endpoint returns nothing', async () => {
    server.use(
      http.get('*/api/symbols/:symbol/prices', () => HttpResponse.json([])),
      http.get('*/api/symbols/:symbol/signals', () => HttpResponse.json([])),
      http.get('*/api/symbols/:symbol/quant', () =>
        HttpResponse.json({ detail: 'no quant data' }, { status: 404 })
      ),
      http.get('*/api/symbols/:symbol/fundamentals', () =>
        HttpResponse.json({ detail: 'no fundamentals' }, { status: 404 })
      )
    );
    renderDetail();

    expect(await screen.findByText('No price data')).toBeInTheDocument();
    expect(screen.getByText('No signals')).toBeInTheDocument();
    expect(screen.getByText('Not enough data')).toBeInTheDocument();
    // Fundamentals card is omitted entirely when the fetch fails.
    expect(screen.queryByText('Provider fundamentals')).not.toBeInTheDocument();
    // No price means no quoted close.
    expect(screen.queryByText(/^NPR 1275\.00$/)).not.toBeInTheDocument();
  });

  it('renders the error state when the prices request fails', async () => {
    server.use(
      http.get(
        '*/api/symbols/:symbol/prices',
        () => new HttpResponse('price history unavailable', { status: 500 })
      )
    );
    renderDetail();

    expect(
      await screen.findByText(/price history unavailable/)
    ).toBeInTheDocument();
    expect(screen.queryByText('Price history')).not.toBeInTheDocument();
  });

  it('still renders the page when only the optional panels fail', async () => {
    // Prices drive the error state; signals/quant/fundamentals are allSettled.
    server.use(
      http.get(
        '*/api/symbols/:symbol/signals',
        () => new HttpResponse('signal engine down', { status: 500 })
      ),
      http.get(
        '*/api/symbols/:symbol/quant',
        () => new HttpResponse('quant down', { status: 500 })
      )
    );
    renderDetail();

    expect(await screen.findByText('Price history')).toBeInTheDocument();
    expect(screen.getByText('No signals')).toBeInTheDocument();
    expect(screen.getByText('Not enough data')).toBeInTheDocument();
    // Fundamentals still succeeded.
    expect(screen.getByText('Commercial Banks')).toBeInTheDocument();
  });

  it('refetches when the user picks a different range', async () => {
    const ranges: (string | null)[] = [];
    server.use(
      http.get('*/api/symbols/:symbol/prices', ({ request }) => {
        ranges.push(new URL(request.url).searchParams.get('limit'));
        return HttpResponse.json(fx.prices);
      })
    );
    renderDetail();
    await screen.findByText('Price history');

    await userEvent.click(screen.getByRole('button', { name: 'ALL' }));

    // 3M asks for 500 bars, ALL asks for 2000.
    await waitFor(() => expect(ranges).toContain('2000'));
    expect(ranges[0]).toBe('500');
  });
});
