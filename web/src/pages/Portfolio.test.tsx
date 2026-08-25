import { describe, expect, it } from 'vitest';
import { http, HttpResponse, delay } from 'msw';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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

    // Holdings table: headers and a row per position. Scoped by name, because
    // the page also renders the trade-history table.
    const holdings = within(screen.getByRole('table', { name: 'Holdings' }));
    expect(holdings.getByRole('columnheader', { name: /Symbol/ })).toBeInTheDocument();
    expect(
      holdings.getByRole('columnheader', { name: /Unrealized P&L/ })
    ).toBeInTheDocument();
    expect(holdings.getByRole('cell', { name: 'NABIL' })).toBeInTheDocument();
    expect(holdings.getByRole('cell', { name: 'NPR 1180.25' })).toBeInTheDocument();
    expect(holdings.getByRole('cell', { name: '+3790.00' })).toBeInTheDocument();
    expect(holdings.getByRole('cell', { name: '-559.50' })).toBeInTheDocument();

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
    expect(screen.queryByRole('table', { name: 'Holdings' })).not.toBeInTheDocument();
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

  it('lists past trades with the costs of each fill summed', async () => {
    renderWithProviders(<PortfolioPage />);

    const history = within(
      await screen.findByRole('table', { name: 'Trade history' })
    );
    // 42.49 + 1.77 + 25 + 0 = 69.26 on the buy; the sell adds CGT.
    expect(history.getByRole('cell', { name: '69.26' })).toBeInTheDocument();
    // 9.82 + 0.41 + 25 + 18.20 = 53.43
    expect(history.getByRole('cell', { name: '53.43' })).toBeInTheDocument();
    expect(history.getByRole('cell', { name: 'BUY' })).toBeInTheDocument();
    expect(history.getByRole('cell', { name: 'SELL' })).toBeInTheDocument();
  });

  it('says so plainly when no trades have been recorded', async () => {
    server.use(http.get('*/api/paper/trades', () => HttpResponse.json([])));
    renderWithProviders(<PortfolioPage />);

    expect(await screen.findByText('No trades recorded yet.')).toBeInTheDocument();
    expect(screen.queryByRole('table', { name: 'Trade history' })).not.toBeInTheDocument();
  });

  it('records a simulated fill and shows every cost that was applied', async () => {
    renderWithProviders(<PortfolioPage />);
    await screen.findByRole('heading', { level: 1, name: 'Portfolio' });

    await userEvent.type(screen.getByRole('textbox', { name: 'Symbol' }), 'nabil');
    await userEvent.type(screen.getByRole('spinbutton', { name: 'Price' }), '1180.25');
    await userEvent.type(screen.getByRole('spinbutton', { name: 'Quantity' }), '10');
    await userEvent.click(screen.getByRole('button', { name: 'Record buy' }));

    // The fee breakdown is rendered so the costs are never invisible.
    expect(await screen.findByText('commission')).toBeInTheDocument();
    expect(screen.getByText('SEBON fee')).toBeInTheDocument();
    expect(screen.getByText('DP charge')).toBeInTheDocument();
    expect(screen.getByText('capital gains tax')).toBeInTheDocument();
    // Scoped to the breakdown row: the same net also appears in the history table.
    expect(screen.getByText('net').closest('div')).toHaveTextContent('11871.76');
  });

  it('sends the symbol upper-cased and the chosen side', async () => {
    let body: Record<string, unknown> = {};
    server.use(
      http.post('*/api/paper/trades', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ trade: fx.paperTrades[1], portfolio: fx.portfolio });
      })
    );
    renderWithProviders(<PortfolioPage />);
    await screen.findByRole('heading', { level: 1, name: 'Portfolio' });

    await userEvent.type(screen.getByRole('textbox', { name: 'Symbol' }), 'hbl');
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Side' }), 'sell');
    await userEvent.type(screen.getByRole('spinbutton', { name: 'Price' }), '545.5');
    await userEvent.type(screen.getByRole('spinbutton', { name: 'Quantity' }), '5');
    await userEvent.click(screen.getByRole('button', { name: 'Record sell' }));

    await waitFor(() => expect(body.symbol).toBe('HBL'));
    expect(body.side).toBe('sell');
    expect(body.price).toBe(545.5);
    expect(body.quantity).toBe(5);
    // A blank date means "today" on the server, so nothing is sent.
    expect(body.business_date).toBeUndefined();
  });

  it('surfaces a rejected fill without clearing what was typed', async () => {
    server.use(
      http.post('*/api/paper/trades', () =>
        HttpResponse.json({ detail: 'cannot sell 999 of NABIL: only 10 held' }, { status: 400 })
      )
    );
    renderWithProviders(<PortfolioPage />);
    await screen.findByRole('heading', { level: 1, name: 'Portfolio' });

    await userEvent.type(screen.getByRole('textbox', { name: 'Symbol' }), 'NABIL');
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Side' }), 'sell');
    await userEvent.type(screen.getByRole('spinbutton', { name: 'Price' }), '1200');
    await userEvent.type(screen.getByRole('spinbutton', { name: 'Quantity' }), '999');
    await userEvent.click(screen.getByRole('button', { name: 'Record sell' }));

    expect(await screen.findByText(/only 10 held/)).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'Symbol' })).toHaveValue('NABIL');
  });
});
