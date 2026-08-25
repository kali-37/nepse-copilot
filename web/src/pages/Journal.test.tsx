import { describe, expect, it } from 'vitest';
import { http, HttpResponse, delay } from 'msw';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { JournalPage } from './Journal';
import { renderWithProviders } from '../test/renderWithProviders';
import { server } from '../test/server';
import * as fx from '../test/fixtures';

/** The shared default for /api/journal/history is empty — Rashifal's tests rely
 *  on that — so every test here supplies the history it wants. */
function withHistory(entries = fx.journalHistory) {
  server.use(http.get('*/api/journal/history', () => HttpResponse.json(entries)));
}

/** The <Card> body that carries the given title. */
function cardOf(title: string): HTMLElement {
  return screen.getByRole('heading', { name: title }).parentElement!.parentElement!;
}

/** The <StatCard> body carrying the given label. */
function statOf(label: string): HTMLElement {
  return screen.getByText(label).parentElement!.parentElement!;
}

describe('JournalPage', () => {
  it('renders without crashing', () => {
    withHistory();
    expect(() => renderWithProviders(<JournalPage />)).not.toThrow();
  });

  it('shows a loading state before the journal arrives', async () => {
    server.use(
      http.get('*/api/journal/history', async () => {
        await delay(50);
        return HttpResponse.json(fx.journalHistory);
      })
    );
    renderWithProviders(<JournalPage />);

    expect(screen.getByText('Loading the journal...')).toBeInTheDocument();
    expect(
      await screen.findByRole('heading', { level: 1, name: 'Journal' })
    ).toBeInTheDocument();
  });

  it('counts the scoreboard: predictions, queue, hit rate and buckets', async () => {
    withHistory();
    renderWithProviders(<JournalPage />);
    await screen.findByRole('heading', { level: 1, name: 'Journal' });

    expect(within(statOf('Predictions')).getByText('2')).toBeInTheDocument();
    expect(within(statOf('Awaiting review')).getByText('1')).toBeInTheDocument();
    // One of the two entries has been judged, and it hit.
    expect(within(statOf('Hit rate')).getByText('100%')).toBeInTheDocument();
    expect(within(statOf('Hit rate')).getByText('1/1 judged')).toBeInTheDocument();
    expect(within(statOf('Calibration buckets')).getByText('2')).toBeInTheDocument();
  });

  it('shows an em dash for a hit rate with nothing judged yet', async () => {
    withHistory([fx.journalHistory[1]]);
    renderWithProviders(<JournalPage />);
    await screen.findByRole('heading', { level: 1, name: 'Journal' });

    expect(within(statOf('Hit rate')).getByText('—')).toBeInTheDocument();
    expect(within(statOf('Hit rate')).queryByText(/judged/)).not.toBeInTheDocument();
  });

  it('puts claimed confidence next to the realized hit rate', async () => {
    withHistory();
    renderWithProviders(<JournalPage />);

    const table = within(await screen.findByRole('table', { name: 'Calibration' }));
    expect(table.getByRole('columnheader', { name: 'hit rate pct' })).toBeInTheDocument();
    expect(table.getByRole('cell', { name: 'LIKELY' })).toBeInTheDocument();
    expect(table.getByRole('cell', { name: '75' })).toBeInTheDocument();
    expect(table.getByRole('cell', { name: '0.72' })).toBeInTheDocument();
    expect(table.getByRole('cell', { name: '37.5' })).toBeInTheDocument();
  });

  it('lists every prediction with its confidence and realized result', async () => {
    withHistory();
    renderWithProviders(<JournalPage />);

    const table = within(await screen.findByRole('table', { name: 'All predictions' }));
    expect(table.getByRole('cell', { name: 'NABIL' })).toBeInTheDocument();
    expect(table.getByRole('cell', { name: 'HBL' })).toBeInTheDocument();
    // Confidence reads as a percentage plus the band it falls in.
    expect(table.getByRole('cell', { name: '72% LIKELY' })).toBeInTheDocument();
    expect(table.getByRole('cell', { name: '45% COIN_FLIP' })).toBeInTheDocument();
    expect(table.getByRole('cell', { name: '+840.00' })).toBeInTheDocument();
    // An unscored prediction has no realized number to show.
    expect(table.getByRole('cell', { name: '—' })).toBeInTheDocument();
    expect(table.getByRole('cell', { name: 'retired' })).toBeInTheDocument();
    expect(table.getByRole('cell', { name: 'open' })).toBeInTheDocument();
  });

  it('narrows the list to one status on request', async () => {
    let url = '';
    server.use(
      http.get('*/api/journal/history', ({ request }) => {
        url = request.url;
        const status = new URL(request.url).searchParams.get('status');
        return HttpResponse.json(
          status ? fx.journalHistory.filter((row) => row.status === status) : fx.journalHistory
        );
      })
    );
    renderWithProviders(<JournalPage />);
    await screen.findByRole('table', { name: 'All predictions' });

    await userEvent.selectOptions(screen.getByLabelText('Status filter'), 'open');

    await waitFor(() => expect(url).toContain('status=open'));
    const table = within(screen.getByRole('table', { name: 'All predictions' }));
    expect(table.getByRole('cell', { name: 'HBL' })).toBeInTheDocument();
    expect(table.queryByRole('cell', { name: 'NABIL' })).not.toBeInTheDocument();
  });

  it('opens a prediction for review when its row is picked', async () => {
    withHistory();
    renderWithProviders(<JournalPage />);

    const table = within(await screen.findByRole('table', { name: 'All predictions' }));
    await userEvent.click(table.getByRole('cell', { name: 'HBL' }));

    const panel = within(cardOf('HBL · day'));
    expect(panel.getByText('2026-08-10')).toBeInTheDocument();
    expect(panel.getByText('2026-08-13')).toBeInTheDocument();
    expect(panel.getByText('hold')).toBeInTheDocument();
    expect(panel.getByText('+300.00')).toBeInTheDocument();
    expect(panel.getByText('not scored')).toBeInTheDocument();
    expect(
      panel.getByText('Said 45% confident (COIN_FLIP) because house prior.')
    ).toBeInTheDocument();
    // Nothing has been written yet, so there is nothing to save.
    expect(panel.getByRole('button', { name: 'Save review' })).toBeDisabled();
    expect(panel.getByRole('button', { name: 'Keep as lesson' })).toBeDisabled();
    expect(panel.getByRole('button', { name: 'Retire' })).toBeEnabled();
  });

  it('saves a written review and shows what came back', async () => {
    withHistory();
    let body: Record<string, unknown> = {};
    server.use(
      http.post('*/api/journal/:id/review', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(fx.journalHistory[0]);
      })
    );
    renderWithProviders(<JournalPage />);
    const table = within(await screen.findByRole('table', { name: 'All predictions' }));
    await userEvent.click(table.getByRole('cell', { name: 'HBL' }));

    await userEvent.type(
      screen.getByRole('textbox', { name: /What actually happened/ }),
      '  the stop was too tight  '
    );
    await userEvent.click(screen.getByRole('button', { name: 'Save review' }));

    await waitFor(() => expect(body.review).toBe('the stop was too tight'));
    // The panel re-renders around whatever the server returned.
    expect(await screen.findByRole('heading', { name: 'NABIL · week' })).toBeInTheDocument();
  });

  it('closes the panel once a lesson has been kept', async () => {
    withHistory();
    let body: Record<string, unknown> = {};
    server.use(
      http.post('*/api/journal/:id/distill', async ({ request, params }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ prediction_id: String(params.id), lesson_id: 4 });
      })
    );
    renderWithProviders(<JournalPage />);
    const table = within(await screen.findByRole('table', { name: 'All predictions' }));
    await userEvent.click(table.getByRole('cell', { name: 'HBL' }));

    await userEvent.type(
      screen.getByRole('textbox', { name: 'The one sentence worth keeping' }),
      'Size stops off ATR.'
    );
    await userEvent.click(screen.getByRole('button', { name: 'Keep as lesson' }));

    await waitFor(() => expect(body.lesson).toBe('Size stops off ATR.'));
    // A distilled lesson is not an entry, so the panel has nothing left to show.
    await waitFor(() =>
      expect(screen.queryByRole('heading', { name: 'HBL · day' })).not.toBeInTheDocument()
    );
  });

  it('retires a prediction and keeps the panel on the retired entry', async () => {
    withHistory();
    renderWithProviders(<JournalPage />);
    const table = within(await screen.findByRole('table', { name: 'All predictions' }));
    await userEvent.click(table.getByRole('cell', { name: 'HBL' }));

    await userEvent.click(screen.getByRole('button', { name: 'Retire' }));

    const panel = within(cardOf('HBL · day'));
    await waitFor(() => expect(panel.getByText('retired')).toBeInTheDocument());
  });

  it('reports that nothing was due when scoring finds no deadline passed', async () => {
    withHistory();
    renderWithProviders(<JournalPage />);
    await screen.findByRole('heading', { level: 1, name: 'Journal' });

    await userEvent.click(screen.getByRole('button', { name: 'Score now' }));

    expect(
      await screen.findByText(
        'Nothing was due for scoring — every open prediction is still inside its horizon.'
      )
    ).toBeInTheDocument();
  });

  it('counts what scoring settled', async () => {
    withHistory();
    server.use(
      http.post('*/api/journal/score', () => HttpResponse.json([{ id: 1 }, { id: 2 }]))
    );
    renderWithProviders(<JournalPage />);
    await screen.findByRole('heading', { level: 1, name: 'Journal' });

    await userEvent.click(screen.getByRole('button', { name: 'Score now' }));

    expect(
      await screen.findByText('Scored 2 predictions against stored prices.')
    ).toBeInTheDocument();
  });

  it('renders the error state when the journal cannot be read', async () => {
    server.use(
      http.get(
        '*/api/journal/history',
        () => new HttpResponse('journal read failed', { status: 500 })
      )
    );
    renderWithProviders(<JournalPage />);

    expect(await screen.findByText(/journal read failed/)).toBeInTheDocument();
    expect(
      screen.queryByRole('heading', { level: 1, name: 'Journal' })
    ).not.toBeInTheDocument();
  });
});
