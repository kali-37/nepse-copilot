import { describe, it, expect, beforeEach, vi } from 'vitest';
import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { DashboardPage } from './Dashboard';
import { server } from '../test/server';
import { renderWithProviders } from '../test/renderWithProviders';
import { decisionBoard } from '../test/decisionFixture';
import { decisionApi } from '../api/decisions';

beforeEach(() => {
  server.use(http.get('*/api/decisions', () => HttpResponse.json(decisionBoard)));
});
describe('decision dashboard', () => {
  it.each(['success', 'failure'])('keeps saved cash when an older refresh read ends in %s', async outcome => {
    let resolveOld!: (board: typeof decisionBoard) => void;
    let rejectOld!: (error: Error) => void;
    const pending = new Promise<typeof decisionBoard>((resolve, reject) => {
      resolveOld = resolve; rejectOld = reject;
    });
    const reads = vi.spyOn(decisionApi, 'board')
      .mockResolvedValueOnce(decisionBoard).mockReturnValueOnce(pending);
    server.use(
      http.post('*/api/jobs', () => HttpResponse.json({ id: 'cash-race', kind: 'refresh-today', status: 'queued', stages: [] })),
      http.get('*/api/jobs/cash-race', () => HttpResponse.json({ id: 'cash-race', kind: 'refresh-today', status: 'done', stages: [] })),
      http.put('*/api/decisions/cash', () => HttpResponse.json({ ...decisionBoard, available_cash: 250000 }))
    );
    try {
      renderWithProviders(<DashboardPage />);
      await screen.findByText('NABIL');
      await userEvent.click(screen.getByRole('button', { name: 'Refresh today' }));
      await waitFor(() => expect(reads).toHaveBeenCalledTimes(2), { timeout: 4000 });
      await userEvent.click(screen.getByRole('button', { name: 'Edit' }));
      const input = screen.getByRole('spinbutton', { name: 'Available cash (NPR)' });
      await userEvent.clear(input); await userEvent.type(input, '250000');
      await userEvent.click(screen.getByRole('button', { name: 'Save' }));
      await screen.findByText('NPR 250,000.00');
      await act(async () => {
        if (outcome === 'success') resolveOld(decisionBoard);
        else rejectOld(new Error('Late refresh error'));
      });
      expect(screen.getByText('NPR 250,000.00')).toBeInTheDocument();
      expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    } finally { reads.mockRestore(); }
  });
  it('keeps completed refresh advice when an older request fails afterwards', async () => {
    let rejectOld!: (error: Error) => void;
    const first = new Promise<never>((_, reject) => { rejectOld = reject; });
    const reads = vi.spyOn(decisionApi, 'board')
      .mockReturnValueOnce(first).mockResolvedValue(decisionBoard);
    server.use(
      http.get('*/api/jobs', () => HttpResponse.json({ jobs: [], running: 'race', kinds: [] })),
      http.get('*/api/jobs/race', () => HttpResponse.json({ id: 'race', kind: 'refresh-today', status: 'done', stages: [] }))
    );
    try {
      renderWithProviders(<DashboardPage />);
      await screen.findByText('NABIL');
      expect(reads).toHaveBeenCalledTimes(2);
      await act(async () => { rejectOld(new Error('Market data was still changing')); });
      expect(screen.queryByRole('alert')).not.toBeInTheDocument();
      expect(screen.getByText('NABIL')).toBeInTheDocument();
    } finally { reads.mockRestore(); }
  });
  it('puts daily buys, evidence scores and held-stock exits first', async () => {
    renderWithProviders(<DashboardPage />);
    expect(await screen.findByText('NABIL')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Your next move.' })).toBeInTheDocument();
    expect(screen.getByText('64% evidence score')).toBeInTheDocument();
    expect(screen.getByText('88% holding evidence')).toBeInTheDocument();
    expect(screen.getByText('Consider selling')).toBeInTheDocument();
    expect(screen.getByText(/using the last published session/)).toBeInTheDocument();
    expect(screen.getByText('2026-11-19', { selector: 'strong' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('tab', { name: 'Monthly' }));
    expect(screen.getByText('EBL')).toBeInTheDocument();
    expect(screen.getByText('73% evidence score')).toBeInTheDocument();
    expect(screen.queryByText('NABIL')).not.toBeInTheDocument();
  });
  it.each([true, false])('shows a separate model probability only when eligible (%s)', async eligible => {
    const candidate = {
      ...decisionBoard.buys.day[0],
      model_estimate: {
        model_id: 'model-example', probability: .582, event: 'net_profitable_modeled_trade_given_entry',
        horizon_days: 3, as_of: '2026-11-19', label: 'Validated model estimate',
        limitations: ['Uses a modeled 100-share trade.'], eligible_for_advisory: eligible,
      },
    };
    server.use(http.get('*/api/decisions', () => HttpResponse.json({
      ...decisionBoard, buys: { ...decisionBoard.buys, day: [candidate] },
    })));
    renderWithProviders(<DashboardPage />);
    expect(await screen.findByText('64% evidence score')).toBeInTheDocument();
    if (eligible) {
      const estimate = screen.getByRole('complementary', { name: 'Trained model estimate' });
      expect(within(estimate).getByText('58.2%')).toBeInTheDocument();
      expect(within(estimate).getByText(/assumes an entry fill/i)).toBeInTheDocument();
    } else {
      expect(screen.queryByRole('complementary', { name: 'Trained model estimate' })).not.toBeInTheDocument();
    }
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

it('shows the buy reasons openly and remembers the original holding plan', async () => {
  server.use(http.get('*/api/decisions', () => HttpResponse.json({ ...decisionBoard, holdings: [{ ...decisionBoard.holdings[0],
    holding_horizon: 'monthly', review_on: '2026-11-02', plan_key: 'entry1',
    original_plan: { id: 'original1', opened_on: '2026-10-01', horizon_days: 22, purchase_price: 500,
      stop: 470, target: 540, rationale: ['Monthly earnings and trend supported entry.'],
      confidence: { value: .72, basis: 'Entry evidence from completed historical setups.', label: 'Combined evidence' }, origin: null },
    advice_history: [{ market_date: '2026-11-19', previous_action: 'hold', action: 'sell', plan_key: 'entry1',
      trigger_code: 'target_hit', reason: 'Saved target reached.', evaluated_at: '2026-11-19T15:01:00Z' }],
  }] })));
  renderWithProviders(<DashboardPage />);
  await screen.findByText('NABIL');
  expect(screen.getByText('Why buy NABIL?')).toBeInTheDocument();
  expect(screen.getByText('Medium-term trend is rising')).toBeVisible();
  expect(screen.getByText(/Changed HOLD → SELL on 2026-11-19/)).toBeInTheDocument();
  await userEvent.click(screen.getByText('Original buy reason & past advice'));
  expect(screen.getByText('Monthly earnings and trend supported entry.')).toBeVisible();
  expect(screen.getByText(/72% entry confidence/)).toBeVisible();
});

it('shows lower-risk investments as a dated watchlist without promised bank returns', async () => {
  server.use(http.get('*/api/decisions', () => HttpResponse.json({ ...decisionBoard, investments: {
    candidates: [{ symbol: 'SCB', company_name: 'Standard Chartered Bank', sector: 'Bank', horizon_days: 252,
      reference_price: 650, rationale: ['Positive reported EPS and reasonable valuation.'], owned: false,
      score: .74, confidence: { value: .74, label: 'Screen evidence', basis: 'Valuation and historical risk.' },
      chart: [], snapshot_date: '2026-11-19', history_from: '2025-10-15', history_to: '2026-11-19',
      historical_net_annual_return: 8.4, max_drawdown: 9.1, annual_volatility: 13.2,
      pe: 24, pbv: 2.8, eps: 27, declared_dividend_pct: null, limitations: 'Cash dividends are excluded.' }],
    checked_fundamentals: 15, fundamentals_missing: 333, criteria: 'Positive EPS and limited historical drawdown.', note: 'Research watchlist.',
  } })));
  renderWithProviders(<DashboardPage />);
  await screen.findByText('SCB');
  expect(screen.getByRole('heading', { name: 'Lower-risk investments' })).toBeInTheDocument();
  expect(screen.getByText('+8.40% / year')).toBeInTheDocument();
  expect(screen.getByText('9.1%')).toBeInTheDocument();
  expect(screen.getByText(/Historical growth is not a promised return/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'I bought this investment' }));
  expect(screen.getByLabelText('Planned holding period')).toHaveValue('252');
});
