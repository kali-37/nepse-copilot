import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { OperationsPage } from './Operations';
import { renderWithProviders } from '../test/renderWithProviders';
import { server } from '../test/server';
import * as fx from '../test/fixtures';

/** Start the selected job and wait for the console to appear. */
async function pressRun() {
  await userEvent.click(await screen.findByRole('button', { name: /^Run / }));
}

/** Render the page with a finished job whose result has the given shape. */
async function runWithResult(result: Record<string, unknown>, kind = 'run-daily') {
  server.use(
    http.post('*/api/jobs', () => HttpResponse.json({ ...fx.doneJob, kind, result }))
  );
  renderWithProviders(<OperationsPage />);
  await pressRun();
}

/** The <Card> body that carries the given title. */
function cardOf(title: string): HTMLElement {
  return screen.getByRole('heading', { name: title }).parentElement!.parentElement!;
}

describe('OperationsPage', () => {
  it('starts a dated history download from the selected verified source', async () => {
    let submitted: { kind?: string; params?: Record<string, unknown> } = {};
    server.use(http.post('*/api/jobs', async ({ request }) => {
      submitted = await request.json() as typeof submitted;
      return HttpResponse.json({ ...fx.doneJob, kind: 'backfill' });
    }));
    renderWithProviders(<OperationsPage />);
    await userEvent.click(screen.getByRole('button', { name: 'Download price history' }));
    await userEvent.type(screen.getByLabelText('Symbols (comma list, blank = all)'), 'NABIL,EBL');
    fireEvent.change(screen.getByLabelText('History from'), { target: { value: '2024-01-01' } });
    await userEvent.selectOptions(screen.getByLabelText('History source'), 'chukul');
    await pressRun();
    await waitFor(() => expect(submitted.kind).toBe('backfill'));
    expect(submitted.params).toEqual({ symbols: 'NABIL,EBL', since: '2024-01-01', source: 'chukul' });
  });
  it('renders without crashing', () => {
    expect(() => renderWithProviders(<OperationsPage />)).not.toThrow();
  });

  it('starts idle, with every command on offer', async () => {
    renderWithProviders(<OperationsPage />);

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Operations' })
    ).toBeInTheDocument();

    for (const label of [
      'Daily run',
      'Download prices',
      'Cross-check sources',
      'Backtest everything',
      'Rebuild search index',
    ]) {
      expect(screen.getByRole('button', { name: label })).toBeInTheDocument();
    }

    expect(screen.getByText('Nothing running. Pick a command and press run.')).toBeInTheDocument();
    expect(screen.getByText('No jobs yet this session.')).toBeInTheDocument();
    // The default selection is the one an operator would schedule.
    expect(screen.getByRole('button', { name: 'Run daily run' })).toBeEnabled();
    expect(screen.getByText(/Skipped automatically when the date is not a NEPSE trading day/))
      .toBeInTheDocument();
  });

  it('swaps the option fields when a different command is picked', async () => {
    renderWithProviders(<OperationsPage />);
    await screen.findByRole('heading', { level: 1, name: 'Operations' });

    // run-daily exposes the full set.
    expect(screen.getByLabelText('Trading date')).toBeInTheDocument();
    expect(screen.getByLabelText('Starting cash (NPR)')).toBeInTheDocument();
    expect(screen.getByLabelText('Rank by')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Cross-check sources' }));

    // reconcile takes a date and nothing else.
    expect(screen.getByLabelText('Trading date')).toBeInTheDocument();
    expect(screen.queryByLabelText('Starting cash (NPR)')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Rank by')).not.toBeInTheDocument();
    expect(screen.getByText(/one confidence-scored consensus per symbol/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Run cross-check sources' })).toBeInTheDocument();
  });

  it('sends the visible defaults and omits a blank field so the server decides', async () => {
    let body: Record<string, unknown> = {};
    server.use(
      http.post('*/api/jobs', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(fx.doneJob);
      })
    );
    renderWithProviders(<OperationsPage />);
    await pressRun();

    await waitFor(() => expect(body.kind).toBe('run-daily'));
    const params = body.params as Record<string, unknown>;
    expect(params).toEqual({
      all_sources: true,
      strategies: 'all',
      top: 25,
      rank_by: 'sharpe',
      cash: 100_000,
    });
    // An untouched date field must not override the server's "today".
    expect(params.business_date).toBeUndefined();
  });

  it('sends what was typed or ticked', async () => {
    let body: Record<string, unknown> = {};
    server.use(
      http.post('*/api/jobs', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(fx.doneJob);
      })
    );
    renderWithProviders(<OperationsPage />);
    await userEvent.click(await screen.findByRole('button', { name: 'Download prices' }));

    fireEvent.change(screen.getByLabelText('Trading date'), {
      target: { value: '2026-08-22' },
    });
    await userEvent.click(
      screen.getByRole('checkbox', { name: 'Every source, not just enabled ones' })
    );
    await pressRun();

    await waitFor(() => expect(body.kind).toBe('ingest'));
    expect(body.params).toEqual({ business_date: '2026-08-22', all_sources: false });
  });

  it('re-attaches to a job that was already running when the page opened', async () => {
    server.use(
      http.get('*/api/jobs', () =>
        HttpResponse.json({
          jobs: [fx.runningJob],
          running: fx.runningJob.id,
          kinds: ['ingest', 'rag-index', 'reconcile', 'run-daily', 'screen'],
        })
      ),
      http.get('*/api/jobs/:id', () => HttpResponse.json(fx.runningJob))
    );
    renderWithProviders(<OperationsPage />);

    expect(await screen.findByText('Job run-daily')).toBeInTheDocument();
    expect(screen.getByText('12/244')).toBeInTheDocument();
    expect(
      screen.getByRole('progressbar', { name: 'Cross-check sources progress' })
    ).toBeInTheDocument();
    // One job at a time: the launcher is locked while something runs.
    expect(screen.getByRole('button', { name: 'A job is running' })).toBeDisabled();
    expect(screen.queryByText('Nothing running. Pick a command and press run.')).not.toBeInTheDocument();
  });

  it('lists recent jobs and re-opens one when its kind is clicked', async () => {
    server.use(
      http.get('*/api/jobs', () =>
        HttpResponse.json({
          jobs: [fx.doneJob],
          running: null,
          kinds: ['ingest', 'rag-index', 'reconcile', 'run-daily', 'screen'],
        })
      )
    );
    renderWithProviders(<OperationsPage />);

    // The list arrives with the mount fetch, so wait for a row before scoping.
    expect(await screen.findByRole('button', { name: 'reconcile' })).toBeInTheDocument();
    const recent = within(cardOf('Recent jobs'));
    expect(recent.getByText('done')).toBeInTheDocument();
    // Wall-clock slice of created_at, which is all an operator needs.
    expect(recent.getByText('10:00:00')).toBeInTheDocument();

    await userEvent.click(recent.getByRole('button', { name: 'reconcile' }));

    expect(await screen.findByText('Job reconcile')).toBeInTheDocument();
    expect(screen.getByLabelText('Job log')).toBeInTheDocument();
  });

  it('says plainly when a run had nothing to do', async () => {
    await runWithResult({ skipped: true, reason: '2026-08-22 is not a trading day' });

    expect(
      await screen.findByText('Nothing to do — 2026-08-22 is not a trading day.')
    ).toBeInTheDocument();
  });

  it('renders a daily-run result: summary, per-source counts and report sections', async () => {
    await runWithResult({
      summary: {
        business_date: '2026-08-22',
        reconciled: 244,
        disputed: null,
        // Nested values belong to the dedicated views below, not the summary list.
        per_strategy: { sma_cross: 12 },
      },
      ingest: { per_source: { merolagani: 244, chukul: 0 }, total_bars: 484 },
      sections: { 'Market breadth': 'breadth table text', 'Top movers': 'movers table text' },
    });

    // Summary keys are de-underscored, and a null reads as an em dash.
    const summary = (await screen.findByText('business date')).closest('dl')!;
    expect(within(summary).getByText('2026-08-22')).toBeInTheDocument();
    expect(within(summary).getByText('244')).toBeInTheDocument();
    expect(within(summary).getByText('—')).toBeInTheDocument();
    expect(within(summary).queryByText('per strategy')).not.toBeInTheDocument();

    expect(screen.getByText('Rows per source (484 total)')).toBeInTheDocument();
    expect(screen.getByText('merolagani: 244')).toBeInTheDocument();
    expect(screen.getByText('chukul: 0')).toBeInTheDocument();

    // The report opens on its first section; the rest are one click away.
    expect(screen.getByText('breadth table text')).toBeInTheDocument();
    expect(screen.queryByText('movers table text')).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Top movers' }));
    expect(screen.getByText('movers table text')).toBeInTheDocument();
    expect(screen.queryByText('breadth table text')).not.toBeInTheDocument();

    // Clicking the open section collapses it.
    await userEvent.click(screen.getByRole('button', { name: 'Top movers' }));
    expect(screen.queryByText('movers table text')).not.toBeInTheDocument();
  });

  it('renders an index result: documents per kind', async () => {
    await runWithResult({ per_kind: { price: 800, news: 450 }, total: 1250 }, 'rag-index');

    expect(await screen.findByText('Documents indexed')).toBeInTheDocument();
    expect(screen.getByText('price: 800')).toBeInTheDocument();
    expect(screen.getByText('news: 450')).toBeInTheDocument();
  });

  it('renders a screen result as a table, whatever columns it happens to have', async () => {
    await runWithResult(
      {
        rows: [
          { symbol: 'NABIL', strategy: 'sma_cross', sharpe: 1.23456789, tags: [], note: null },
        ],
      },
      'screen'
    );

    expect(await screen.findByText('1 row')).toBeInTheDocument();
    const table = within(screen.getByRole('table'));
    expect(table.getByRole('columnheader', { name: 'strategy' })).toBeInTheDocument();
    expect(table.getByRole('cell', { name: 'NABIL' })).toBeInTheDocument();
    // Numbers are trimmed to four places, empties read as em dashes.
    expect(table.getByRole('cell', { name: '1.2346' })).toBeInTheDocument();
    expect(table.getAllByRole('cell', { name: '—' })).toHaveLength(2);
  });

  it('surfaces the refusal when another job already holds the lock', async () => {
    server.use(
      http.post('*/api/jobs', () =>
        HttpResponse.json(
          { detail: 'a job is already running', running_job_id: 'job-running-1' },
          { status: 409 }
        )
      )
    );
    renderWithProviders(<OperationsPage />);
    await pressRun();

    expect(await screen.findByText(/a job is already running/)).toBeInTheDocument();
    // The refusal is not a job, so the placeholder stays put.
    expect(screen.getByText('Nothing running. Pick a command and press run.')).toBeInTheDocument();
  });
});
