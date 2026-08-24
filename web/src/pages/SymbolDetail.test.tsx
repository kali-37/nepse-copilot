import { describe, expect, it } from 'vitest';
import { http, HttpResponse, delay } from 'msw';
import { screen, waitFor } from '@testing-library/react';
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
    expect(screen.getByText('Fundamentals')).toBeInTheDocument();
    expect(screen.getByText('Commercial Banks')).toBeInTheDocument();
    expect(screen.getByText('NPR 1280.00')).toBeInTheDocument();
    expect(screen.getByText('43.21')).toBeInTheDocument();
    expect(screen.getByText('29.51')).toBeInTheDocument();
    // 2.15e10 / 1e7 => 2150.0Cr
    expect(screen.getByText('NPR 2150.0Cr')).toBeInTheDocument();

    // The chart container renders; recharts SVG internals are not asserted.
    expect(screen.queryByText('No price data')).not.toBeInTheDocument();
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
    expect(screen.queryByText('Fundamentals')).not.toBeInTheDocument();
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
