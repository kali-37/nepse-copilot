import { describe, it, expect, beforeEach } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { DashboardPage } from './Dashboard';
import { server } from '../test/server';
import { renderWithProviders } from '../test/renderWithProviders';
import { decisionBoard } from '../test/decisionFixture';

beforeEach(() => {
  server.use(http.get('*/api/decisions', () => HttpResponse.json(decisionBoard)));
});
describe('decision dashboard', () => {
  it('puts daily buys, confidence and held-stock exits first', async () => {
    renderWithProviders(<DashboardPage />);
    expect(await screen.findByText('NABIL')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Your next move.' })).toBeInTheDocument();
    expect(screen.getByText('64% confidence')).toBeInTheDocument();
    expect(screen.getByText('88% confidence')).toBeInTheDocument();
    expect(screen.getByText('Consider selling')).toBeInTheDocument();
    expect(screen.getByText(/using the last published session/)).toBeInTheDocument();
    expect(screen.getByText('2026-11-19', { selector: 'strong' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('tab', { name: 'Monthly' }));
    expect(screen.getByText('EBL')).toBeInTheDocument();
    expect(screen.getByText('73% confidence')).toBeInTheDocument();
    expect(screen.queryByText('NABIL')).not.toBeInTheDocument();
  });
  it('one refresh button submits the full refresh job and reloads advice', async () => {
    let submitted: unknown;
    let reads = 0;
    server.use(
      http.get('*/api/decisions', () => { reads++; return HttpResponse.json(decisionBoard); }),
      http.post('*/api/jobs', async ({ request }) => {
        submitted = await request.json();
        return HttpResponse.json({ id: 'refresh1', kind: 'refresh-today', status: 'queued', stages: [] });
      }),
      http.get('*/api/jobs/refresh1', () => HttpResponse.json({ id: 'refresh1', kind: 'refresh-today', status: 'done', stages: [], result: {} }))
    );
    renderWithProviders(<DashboardPage />);
    await screen.findByText('NABIL');
    await userEvent.click(screen.getByRole('button', { name: 'Refresh today' }));
    await waitFor(() => expect(submitted).toEqual({ kind: 'refresh-today', params: {} }));
    expect(screen.getByRole('button', { name: 'Refreshing…' })).toBeDisabled();
    await screen.findByText(/Refresh complete/, {}, { timeout: 4000 });
    await waitFor(() => expect(reads).toBe(2));
  });
  it('records an executed buy and displays updated personal holdings', async () => {
    let trade: Record<string, unknown> | null = null;
    server.use(http.post('*/api/decisions/trades', async ({ request }) => {
      trade = await request.json() as Record<string, unknown>;
      return HttpResponse.json({ record: { order_submitted: false }, board: { ...decisionBoard,
        holdings: [...decisionBoard.holdings, { ...decisionBoard.holdings[0], symbol: 'NABIL', action: 'hold', reason: 'Your saved exit plan has not triggered.' }],
        buys: { ...decisionBoard.buys, day: [] } } });
    }));
    renderWithProviders(<DashboardPage />);
    await screen.findByText('NABIL');
    await userEvent.click(screen.getByRole('button', { name: 'I bought this' }));
    const dialog = screen.getByRole('dialog', { name: 'Record a purchase' });
    expect(within(dialog).getByLabelText('Saved stop loss')).toHaveValue(95);
    await userEvent.click(within(dialog).getByRole('button', { name: 'Save purchase' }));
    await waitFor(() => expect(trade).toMatchObject({ symbol: 'NABIL', side: 'buy', quantity: 100, price: 100, stop: 95, target: 115, business_date: '2026-11-19' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(screen.getByText('Your saved exit plan has not triggered.')).toBeInTheDocument();
  });
  it('records sale and sends the held quantity', async () => {
    let trade: unknown;
    server.use(http.post('*/api/decisions/trades', async ({ request }) => {
      trade = await request.json(); return HttpResponse.json({ board: { ...decisionBoard, holdings: [] }, record: { order_submitted: false } });
    }));
    renderWithProviders(<DashboardPage />);
    await screen.findByText('NICA');
    await userEvent.click(screen.getByRole('button', { name: 'I sold' }));
    await userEvent.click(screen.getByRole('button', { name: 'Save sale' }));
    await waitFor(() => expect(trade).toMatchObject({ symbol: 'NICA', side: 'sell', quantity: 40, price: 550 }));
    await screen.findByText('Your holdings start here.');
  });
  it('updates available cash without treating invested capital as spendable', async () => {
    let cash: unknown;
    server.use(http.put('*/api/decisions/cash', async ({ request }) => { cash = await request.json(); return HttpResponse.json({ ...decisionBoard, available_cash: 250000 }); }));
    renderWithProviders(<DashboardPage />);
    await screen.findByText('NABIL');
    await userEvent.click(screen.getByRole('button', { name: 'Edit' }));
    const input = screen.getByRole('spinbutton', { name: 'Available cash (NPR)' });
    await userEvent.clear(input); await userEvent.type(input, '250000');
    await userEvent.click(screen.getByRole('button', { name: 'Save' }));
    await waitFor(() => expect(cash).toEqual({ cash: 250000 }));
    expect(await screen.findByText('NPR 250,000.00')).toBeInTheDocument();
  });
  it('retains actionable error text and retries loading the board', async () => {
    let first = true;
    server.use(http.get('*/api/decisions', () => {
      if (first) { first = false; return new HttpResponse('temporary database error', { status: 503 }); }
      return HttpResponse.json(decisionBoard);
    }));
    renderWithProviders(<DashboardPage />);
    await screen.findByText(/temporary database error/);
    await userEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(await screen.findByText('NABIL')).toBeInTheDocument();
  });
  it('does not force buys when fresh evidence is missing', async () => {
    server.use(http.get('*/api/decisions', () => HttpResponse.json({ ...decisionBoard, stale: true, buys: { day: [], month: [] } })));
    renderWithProviders(<DashboardPage />);
    expect(await screen.findByText('Fresh data comes first.')).toBeInTheDocument();
    expect(screen.getByText('Market data needs a refresh')).toBeInTheDocument();
  });
});

it('updates an existing exit plan without recording another purchase', async () => {
  let plan: unknown;
  server.use(http.put('*/api/decisions/holdings/NICA/plan', async ({ request }) => {
    plan = await request.json();
    return HttpResponse.json({ ...decisionBoard, holdings: [{ ...decisionBoard.holdings[0], stop: 480 }] });
  }));
  renderWithProviders(<DashboardPage />);
  await screen.findByText('NICA');
  await userEvent.click(screen.getByText('Exit plan & evidence'));
  await userEvent.click(screen.getByRole('button', { name: 'Set exit plan' }));
  const dialog = screen.getByRole('dialog', { name: 'NICA · Exit plan' });
  const stop = within(dialog).getByLabelText('Stop loss');
  await userEvent.clear(stop); await userEvent.type(stop, '480');
  await userEvent.click(within(dialog).getByRole('button', { name: 'Save exit plan' }));
  await waitFor(() => expect(plan).toMatchObject({ quantity: 40, stop: 480, average_cost: 500 }));
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  expect(screen.getByText(/40 shares/)).toBeInTheDocument();
});

it('accepts a fee-inclusive WACC with fractional paisa per share', async () => {
  server.use(http.get('*/api/decisions', () => HttpResponse.json({ ...decisionBoard,
    holdings: [{ ...decisionBoard.holdings[0], average_cost: 103.517 }] })));
  renderWithProviders(<DashboardPage />);
  await screen.findByText('NICA');
  await userEvent.click(screen.getByText('Exit plan & evidence'));
  await userEvent.click(screen.getByRole('button', { name: 'Set exit plan' }));
  const cost = screen.getByLabelText('Average cost per share, including buy fees (optional)') as HTMLInputElement;
  expect(cost).toHaveValue(103.517);
  expect(cost.checkValidity()).toBe(true);
});

it('rounds a fractional source quote to a valid trade-price input', async () => {
  server.use(http.get('*/api/decisions', () => HttpResponse.json({ ...decisionBoard,
    holdings: [{ ...decisionBoard.holdings[0], reference_price: 550.12345 }] })));
  renderWithProviders(<DashboardPage />);
  await screen.findByText('NICA');
  await userEvent.click(screen.getByRole('button', { name: 'I sold' }));
  const price = screen.getByLabelText('Actual price (NPR)') as HTMLInputElement;
  expect(price).toHaveValue(550.12);
  expect(price.checkValidity()).toBe(true);
});
