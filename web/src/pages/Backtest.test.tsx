import { describe, expect, it } from 'vitest';
import { http, HttpResponse, delay } from 'msw';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { BacktestPage } from './Backtest';
import { renderWithProviders } from '../test/renderWithProviders';
import { server } from '../test/server';
import * as fx from '../test/fixtures';

describe('BacktestPage', () => {
  it('renders without crashing', () => {
    expect(() => renderWithProviders(<BacktestPage />)).not.toThrow();
  });

  it('starts in an idle state prompting the user to run', () => {
    renderWithProviders(<BacktestPage />);

    expect(
      screen.getByRole('heading', { level: 1, name: 'Backtest' })
    ).toBeInTheDocument();
    expect(screen.getByText(/Click/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Run/ })).toBeEnabled();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('shows a loading state while the screen is running', async () => {
    server.use(
      http.get('*/api/backtest/screen', async () => {
        await delay(50);
        return HttpResponse.json(fx.screenRows);
      })
    );
    renderWithProviders(<BacktestPage />);

    await userEvent.click(screen.getByRole('button', { name: /Run/ }));

    expect(screen.getByText('Running backtests...')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Running/ })).toBeDisabled();

    await waitFor(() => expect(screen.getByRole('table')).toBeInTheDocument());
  });

  it('renders the happy path leaderboard after a run', async () => {
    renderWithProviders(<BacktestPage />);
    await userEvent.click(screen.getByRole('button', { name: /Run/ }));

    expect(await screen.findByRole('table')).toBeInTheDocument();
    expect(
      screen.getByRole('columnheader', { name: /Sharpe/ })
    ).toBeInTheDocument();

    expect(screen.getByRole('cell', { name: 'NABIL' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: 'sma_cross' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: '+42.18%' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: '0.658' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: '54.5%' })).toBeInTheDocument();

    // Negative row renders with a sign and no '+' prefix.
    expect(screen.getByRole('cell', { name: 'HBL' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: '-8.40%' })).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: '-0.212' })).toBeInTheDocument();

    // The idle prompt is gone once results exist.
    expect(screen.queryByText(/Click/)).not.toBeInTheDocument();
  });

  it('sends the form controls as query params', async () => {
    let url = '';
    server.use(
      http.get('*/api/backtest/screen', ({ request }) => {
        url = request.url;
        return HttpResponse.json(fx.screenRows);
      })
    );
    renderWithProviders(<BacktestPage />);

    await userEvent.selectOptions(screen.getByRole('combobox'), 'cagr_pct');
    const minBars = screen.getByRole('spinbutton');
    await userEvent.clear(minBars);
    await userEvent.type(minBars, '120');
    const strategies = screen.getByPlaceholderText('all or comma list');
    await userEvent.clear(strategies);
    await userEvent.type(strategies, 'sma_cross');

    await userEvent.click(screen.getByRole('button', { name: /Run/ }));
    await screen.findByRole('table');

    const params = new URL(url).searchParams;
    expect(params.get('rank_by')).toBe('cagr_pct');
    expect(params.get('min_bars')).toBe('120');
    expect(params.get('strategies')).toBe('sma_cross');
    expect(params.get('top')).toBe('50');
    expect(params.get('cash')).toBe('100000');
  });

  it('renders the empty state when the screen returns no rows', async () => {
    server.use(http.get('*/api/backtest/screen', () => HttpResponse.json([])));
    renderWithProviders(<BacktestPage />);

    await userEvent.click(screen.getByRole('button', { name: /Run/ }));

    // Falls back to the same prompt card, with no table.
    await waitFor(() => expect(screen.getByText(/Click/)).toBeInTheDocument());
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    expect(screen.queryByText('Running backtests...')).not.toBeInTheDocument();
  });

  it('renders the error state when the run fails', async () => {
    server.use(
      http.get(
        '*/api/backtest/screen',
        () => new HttpResponse('not enough bars', { status: 500 })
      )
    );
    renderWithProviders(<BacktestPage />);

    await userEvent.click(screen.getByRole('button', { name: /Run/ }));

    expect(await screen.findByText(/not enough bars/)).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    // The idle prompt is suppressed while an error is showing.
    expect(screen.queryByText(/Click/)).not.toBeInTheDocument();
  });

  it('recovers when the user retries after an error', async () => {
    let failed = false;
    server.use(
      http.get('*/api/backtest/screen', () => {
        if (!failed) {
          failed = true;
          return new HttpResponse('transient', { status: 503 });
        }
        return HttpResponse.json(fx.screenRows);
      })
    );
    renderWithProviders(<BacktestPage />);

    await userEvent.click(screen.getByRole('button', { name: /Run/ }));
    await screen.findByText(/transient/);

    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));

    expect(await screen.findByRole('table')).toBeInTheDocument();
    expect(screen.queryByText(/transient/)).not.toBeInTheDocument();
  });
});
