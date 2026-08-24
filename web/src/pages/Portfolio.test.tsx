import { describe, expect, it } from 'vitest';
import { http, HttpResponse, delay } from 'msw';
import { screen, waitFor } from '@testing-library/react';
import { PortfolioPage } from './Portfolio';
import { renderWithProviders } from '../test/renderWithProviders';
import { server } from '../test/server';
import * as fx from '../test/fixtures';

describe('PortfolioPage', () => {
  it('renders without crashing', () => {
    expect(() => renderWithProviders(<PortfolioPage />)).not.toThrow();
  });

  it('shows a loading state before the portfolio arrives', async () => {
    server.use(
      http.get('*/api/portfolio', async () => {
        await delay(50);
        return HttpResponse.json(fx.portfolio);
      })
    );
    renderWithProviders(<PortfolioPage />);
    expect(screen.getByText('Loading portfolio...')).toBeInTheDocument();
    await waitFor(() =>
      expect(
        screen.getByRole('heading', { level: 1, name: 'Portfolio' })
      ).toBeInTheDocument()
    );
  });

  it('renders the happy path: equity totals and the holdings table', async () => {
    renderWithProviders(<PortfolioPage />);

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Portfolio' })
    ).toBeInTheDocument();

    // cash 42,500.75 + 51,000 + 8,146.50 = 101,647.25
    expect(screen.getByText('NPR 101,647.25')).toBeInTheDocument();
    expect(screen.getByText('NPR 42,500.75')).toBeInTheDocument();
    // return = 101,647.25 - 100,000 = 1,647.25 (+1.65%)
    expect(screen.getByText('NPR 1,647.25')).toBeInTheDocument();
    expect(screen.getByText('+1.65%')).toBeInTheDocument();
    expect(screen.getByText('NPR 3,210.50')).toBeInTheDocument();

    // Holdings table: headers and a row per position.
    expect(
      screen.getByRole('columnheader', { name: /Symbol/ })
    ).toBeInTheDocument();
    expect(
      screen.getByRole('columnheader', { name: /Unrealized P&L/ })
    ).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: 'NABIL' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: 'NPR 1180.25' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: '+3790.00' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: '-559.50' })).toBeInTheDocument();

    expect(screen.getByText(/6 trades recorded/)).toBeInTheDocument();
  });

  it('shows real-versus-paper holdings when the MeroShare mirror has data', async () => {
    server.use(
      http.get('*/api/meroshare/compare', () =>
        HttpResponse.json({
          rows: [
            {
              symbol: 'NABIL',
              real_quantity: 12,
              paper_quantity: 10,
              real_wacc: 1180.25,
              paper_avg_cost: 1175,
              quantity_delta: 2,
              only_in: null,
              agrees: false,
            },
          ],
          summary: { symbols: 1, agreeing: 0, mismatched: 1, only_real: 0, only_paper: 0 },
        })
      )
    );
    renderWithProviders(<PortfolioPage />);

    expect(await screen.findByText('Real versus paper')).toBeInTheDocument();
    expect(screen.getByText('Real 12 · Paper 10')).toBeInTheDocument();
    expect(screen.getByText('Review')).toBeInTheDocument();
  });

  it('renders the empty state when there are no open positions', async () => {
    server.use(http.get('*/api/portfolio', () => HttpResponse.json(fx.emptyPortfolio)));
    renderWithProviders(<PortfolioPage />);

    expect(await screen.findByText('No open positions')).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    // Singular/plural handling for zero trades.
    expect(screen.getByText(/0 trades recorded/)).toBeInTheDocument();
    // With no positions, total equity and cash are both the initial cash.
    expect(screen.getAllByText('NPR 100,000.00')).toHaveLength(2);
  });

  it('renders the error state when the request fails', async () => {
    server.use(
      http.get(
        '*/api/portfolio',
        () => new HttpResponse('portfolio replay failed', { status: 500 })
      )
    );
    renderWithProviders(<PortfolioPage />);

    expect(
      await screen.findByText(/portfolio replay failed/)
    ).toBeInTheDocument();
    expect(
      screen.queryByRole('heading', { level: 1, name: 'Portfolio' })
    ).not.toBeInTheDocument();
  });
});
