import { describe, expect, it } from 'vitest';
import { http, HttpResponse, delay } from 'msw';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SignalsPage } from './Signals';
import { renderWithProviders } from '../test/renderWithProviders';
import { server } from '../test/server';
import * as fx from '../test/fixtures';

/** The <StatCard> body carrying the given label. */
function statOf(label: string): HTMLElement {
  return screen.getByText(label).parentElement!.parentElement!;
}

describe('SignalsPage', () => {
  it('renders without crashing', () => {
    expect(() => renderWithProviders(<SignalsPage />)).not.toThrow();
  });

  it('waits to be asked before computing anything', async () => {
    renderWithProviders(<SignalsPage />);

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Signals' })
    ).toBeInTheDocument();
    expect(screen.getByText(/Choose a strategy and press/)).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('fills the strategy picker from the registry', async () => {
    renderWithProviders(<SignalsPage />);

    const picker = screen.getByRole('combobox', { name: 'Strategy' });
    await waitFor(() =>
      expect(within(picker).getAllByRole('option')).toHaveLength(8)
    );
    expect(within(picker).getByRole('option', { name: 'ichimoku' })).toBeInTheDocument();
    expect(within(picker).getByRole('option', { name: 'supertrend' })).toBeInTheDocument();
    // The API's own default is pre-selected.
    expect(picker).toHaveValue('sma_cross');
  });

  it('still offers the default strategy when the registry cannot be read', async () => {
    server.use(
      http.get('*/api/strategies', () => new HttpResponse('boom', { status: 500 }))
    );
    renderWithProviders(<SignalsPage />);

    const picker = screen.getByRole('combobox', { name: 'Strategy' });
    await waitFor(() => expect(within(picker).getAllByRole('option')).toHaveLength(1));
    expect(picker).toHaveValue('sma_cross');
  });

  it('shows a spinner while the symbols are worked through', async () => {
    server.use(
      http.get('*/api/signals', async () => {
        await delay(50);
        return HttpResponse.json(fx.bulkSignals);
      })
    );
    renderWithProviders(<SignalsPage />);

    await userEvent.click(screen.getByRole('button', { name: 'Read signals' }));
    expect(screen.getByText('Working through the symbols...')).toBeInTheDocument();
    expect(await screen.findByRole('table')).toBeInTheDocument();
  });

  it('renders one signal per symbol, with the action and a link to the symbol', async () => {
    renderWithProviders(<SignalsPage />);
    await userEvent.click(screen.getByRole('button', { name: 'Read signals' }));

    const table = within(await screen.findByRole('table'));
    expect(table.getByRole('link', { name: 'NABIL' })).toHaveAttribute(
      'href',
      '/symbols/NABIL'
    );
    expect(table.getByRole('cell', { name: 'BUY' })).toBeInTheDocument();
    expect(table.getByRole('cell', { name: 'SELL' })).toBeInTheDocument();
    expect(table.getByRole('cell', { name: 'HOLD' })).toBeInTheDocument();
    // Strength to three places, price to two.
    expect(table.getByRole('cell', { name: '0.720' })).toBeInTheDocument();
    expect(table.getByRole('cell', { name: '1180.25' })).toBeInTheDocument();
    expect(table.getByRole('cell', { name: 'fast SMA crossed above slow SMA' })).toBeInTheDocument();
    // The HOLD row has neither strength nor a reason.
    expect(table.getAllByRole('cell', { name: '—' })).toHaveLength(2);

    expect(within(statOf('Symbols evaluated')).getByText('3')).toBeInTheDocument();
    expect(within(statOf('Buy')).getByText('1')).toBeInTheDocument();
    expect(within(statOf('Sell')).getByText('1')).toBeInTheDocument();
  });

  it('asks for exactly what the form says', async () => {
    let url = '';
    server.use(
      http.get('*/api/signals', ({ request }) => {
        url = request.url;
        return HttpResponse.json(fx.bulkSignals);
      })
    );
    renderWithProviders(<SignalsPage />);
    await waitFor(() =>
      expect(
        within(screen.getByRole('combobox', { name: 'Strategy' })).getAllByRole('option')
      ).toHaveLength(8)
    );

    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Strategy' }), 'macd');
    await userEvent.type(screen.getByRole('textbox'), 'nabil,hbl');
    await userEvent.clear(screen.getByRole('spinbutton'));
    await userEvent.type(screen.getByRole('spinbutton'), '40');
    await userEvent.click(screen.getByRole('checkbox'));
    await userEvent.click(screen.getByRole('button', { name: 'Read signals' }));

    await waitFor(() => expect(url).toContain('strategy=macd'));
    const params = new URL(url).searchParams;
    // Symbols are upper-cased for the operator.
    expect(params.get('symbols')).toBe('NABIL,HBL');
    expect(params.get('top')).toBe('40');
    expect(params.get('actionable_only')).toBe('true');
  });

  it('switches to the statistics table, which takes no strategy', async () => {
    renderWithProviders(<SignalsPage />);

    await userEvent.click(screen.getByRole('button', { name: 'Statistics' }));
    // A statistic describes price history; no strategy is involved.
    expect(screen.queryByRole('combobox', { name: 'Strategy' })).not.toBeInTheDocument();
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Compute statistics' }));

    expect(
      await screen.findByText('Quantitative statistics · 2 symbols')
    ).toBeInTheDocument();
    expect(screen.getByText('252 periods/year')).toBeInTheDocument();
    const table = within(screen.getByRole('table'));
    expect(table.getByRole('columnheader', { name: 'max drawdown pct' })).toBeInTheDocument();
    expect(table.getByRole('cell', { name: '18.432' })).toBeInTheDocument();
    expect(table.getByRole('cell', { name: '-22.750' })).toBeInTheDocument();
  });

  it('says so when no symbol had enough history for statistics', async () => {
    server.use(
      http.get('*/api/stats', () =>
        HttpResponse.json({ symbols: [], periods_per_year: 252, rows: [] })
      )
    );
    renderWithProviders(<SignalsPage />);

    await userEvent.click(screen.getByRole('button', { name: 'Statistics' }));
    await userEvent.click(screen.getByRole('button', { name: 'Compute statistics' }));

    expect(
      await screen.findByText('No symbol had enough price history to compute statistics.')
    ).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('surfaces a rejected request instead of an empty table', async () => {
    server.use(
      http.get('*/api/signals', () =>
        HttpResponse.json({ detail: 'unknown strategy: nope' }, { status: 400 })
      )
    );
    renderWithProviders(<SignalsPage />);

    await userEvent.click(screen.getByRole('button', { name: 'Read signals' }));

    expect(await screen.findByText(/unknown strategy: nope/)).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });
});
