import { describe, expect, it } from 'vitest';
import { http, HttpResponse, delay } from 'msw';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DashboardPage } from './Dashboard';
import { renderWithProviders } from '../test/renderWithProviders';
import { server } from '../test/server';
import * as fx from '../test/fixtures';

describe('DashboardPage', () => {
  it('renders without crashing', () => {
    expect(() => renderWithProviders(<DashboardPage />)).not.toThrow();
  });

  it('shows a loading state before the data arrives', async () => {
    server.use(
      http.get('*/api/dashboard', async () => {
        await delay(50);
        return HttpResponse.json(fx.dashboardStats);
      })
    );
    renderWithProviders(<DashboardPage />);
    expect(screen.getByText('Loading dashboard...')).toBeInTheDocument();
    await waitFor(() =>
      expect(
        screen.getByRole('heading', { level: 1, name: 'Dashboard' })
      ).toBeInTheDocument()
    );
  });

  it('renders the happy path: heading, breadth stats and movers', async () => {
    renderWithProviders(<DashboardPage />);

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Dashboard' })
    ).toBeInTheDocument();

    // Latest reconciled date from the dashboard stats.
    expect(screen.getByText('2026-08-22')).toBeInTheDocument();

    // Breadth stat cards.
    expect(screen.getByText('Symbols')).toBeInTheDocument();
    expect(screen.getByText('Advancers')).toBeInTheDocument();
    expect(screen.getByText('Decliners')).toBeInTheDocument();
    // 130/244 advancers => 53.3%
    expect(screen.getByText('53.3%')).toBeInTheDocument();
    // 96/244 decliners => 39.3%
    expect(screen.getByText('39.3%')).toBeInTheDocument();
    // 4.512e9 / 1e7 => 451.2Cr
    expect(screen.getByText('NPR 451.2Cr')).toBeInTheDocument();

    // Movers.
    expect(screen.getByText('Top gainers')).toBeInTheDocument();
    expect(screen.getByText('NABIL')).toBeInTheDocument();
    expect(screen.getByText('+9.87%')).toBeInTheDocument();
    expect(screen.getByText('Top losers')).toBeInTheDocument();
    expect(screen.getByText('HBL')).toBeInTheDocument();
    expect(screen.getByText('-7.15%')).toBeInTheDocument();

    // Database health panel.
    expect(screen.getByText('Database health')).toBeInTheDocument();
    expect(screen.getByText('154,320')).toBeInTheDocument();
    expect(screen.getByText('92.3%')).toBeInTheDocument();
  });

  it('renders the empty state when there is no market data', async () => {
    server.use(
      http.get('*/api/market-breadth', () =>
        HttpResponse.json(fx.emptyMarketBreadth)
      ),
      http.get('*/api/movers', () => HttpResponse.json(fx.emptyMovers))
    );
    renderWithProviders(<DashboardPage />);

    expect(await screen.findByText('No gainers')).toBeInTheDocument();
    expect(screen.getByText('No losers')).toBeInTheDocument();
    // Breadth percentages collapse to a literal 0 when there are no symbols.
    expect(screen.getAllByText('0').length).toBeGreaterThan(0);
    // Turnover renders as zero crore rather than NaN.
    expect(screen.getByText('NPR 0.0Cr')).toBeInTheDocument();
  });

  it('renders the error state when an endpoint fails', async () => {
    server.use(
      http.get(
        '*/api/dashboard',
        () => new HttpResponse('database is locked', { status: 500 })
      )
    );
    renderWithProviders(<DashboardPage />);

    expect(await screen.findByText(/database is locked/)).toBeInTheDocument();
    expect(
      screen.queryByRole('heading', { level: 1, name: 'Dashboard' })
    ).not.toBeInTheDocument();
  });

  it('recovers when the user retries after an error', async () => {
    let failed = false;
    server.use(
      http.get('*/api/dashboard', () => {
        if (!failed) {
          failed = true;
          return new HttpResponse('temporary failure', { status: 503 });
        }
        return HttpResponse.json(fx.dashboardStats);
      })
    );
    renderWithProviders(<DashboardPage />);

    await screen.findByText(/temporary failure/);
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Dashboard' })
    ).toBeInTheDocument();
  });
});
