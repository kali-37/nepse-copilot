import { describe, expect, it } from 'vitest';
import { http, HttpResponse, delay } from 'msw';
import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DataPage } from './Data';
import { renderWithProviders } from '../test/renderWithProviders';
import { server } from '../test/server';
import * as fx from '../test/fixtures';

/** The <Card> body that carries the given title. */
function cardOf(title: string): HTMLElement {
  return screen.getByRole('heading', { name: title }).parentElement!.parentElement!;
}

describe('DataPage', () => {
  it('renders without crashing', () => {
    expect(() => renderWithProviders(<DataPage />)).not.toThrow();
  });

  it('shows a loading state before the database has been read', async () => {
    server.use(
      http.get('*/api/tables', async () => {
        await delay(50);
        return HttpResponse.json({ tables: fx.tableSummaries });
      })
    );
    renderWithProviders(<DataPage />);

    expect(screen.getByText('Reading the database...')).toBeInTheDocument();
    expect(await screen.findByRole('heading', { level: 1, name: 'Data' })).toBeInTheDocument();
  });

  it('lists every table with its row count and opens the first one', async () => {
    renderWithProviders(<DataPage />);
    await screen.findByRole('heading', { level: 1, name: 'Data' });

    // Each chip carries the table's name and how many rows it holds.
    expect(screen.getByRole('button', { name: /^price_bars/ })).toHaveTextContent('4,880');
    expect(screen.getByRole('button', { name: /^reconciled_prices/ })).toHaveTextContent('2,440');
    expect(screen.getByRole('button', { name: /^signals/ })).toHaveTextContent('0');

    // The first table is opened without being asked, so the page is never blank.
    const table = within(await screen.findByRole('table', { name: 'price_bars' }));
    expect(table.getByRole('columnheader', { name: 'business date' })).toBeInTheDocument();
    expect(table.getByRole('cell', { name: 'NABIL' })).toBeInTheDocument();
    expect(table.getByRole('cell', { name: '1180.25' })).toBeInTheDocument();
    expect(table.getByRole('cell', { name: '4200' })).toBeInTheDocument();
    // Which slice of the table is on screen, out of how many rows.
    expect(cardOf('price_bars')).toHaveTextContent('1–2 of 4,880');
  });

  it('pages through a table with SQL, not in the browser', async () => {
    const offsets: string[] = [];
    server.use(
      http.get('*/api/tables/:name', ({ params, request }) => {
        const offset = Number(new URL(request.url).searchParams.get('offset') ?? 0);
        offsets.push(String(offset));
        return HttpResponse.json({ ...fx.tablePage, name: String(params.name), offset });
      })
    );
    renderWithProviders(<DataPage />);
    await screen.findByRole('table', { name: 'price_bars' });

    expect(screen.getByText('Page 1 of 49')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled();

    await userEvent.click(screen.getByRole('button', { name: 'Next' }));

    await waitFor(() => expect(screen.getByText('Page 2 of 49')).toBeInTheDocument());
    expect(offsets).toContain('100');
    expect(screen.getByRole('button', { name: 'Previous' })).toBeEnabled();

    await userEvent.click(screen.getByRole('button', { name: 'Previous' }));
    await waitFor(() => expect(screen.getByText('Page 1 of 49')).toBeInTheDocument());
  });

  it('starts a newly picked table at its first page', async () => {
    const asked: string[] = [];
    server.use(
      http.get('*/api/tables/:name', ({ params, request }) => {
        const offset = Number(new URL(request.url).searchParams.get('offset') ?? 0);
        asked.push(`${String(params.name)}@${offset}`);
        return HttpResponse.json({ ...fx.tablePage, name: String(params.name), offset });
      })
    );
    renderWithProviders(<DataPage />);
    await screen.findByRole('table', { name: 'price_bars' });
    await userEvent.click(screen.getByRole('button', { name: 'Next' }));
    await waitFor(() => expect(asked).toContain('price_bars@100'));

    await userEvent.click(screen.getByRole('button', { name: /^reconciled_prices/ }));

    expect(await screen.findByRole('table', { name: 'reconciled_prices' })).toBeInTheDocument();
    expect(asked).toContain('reconciled_prices@0');
    expect(screen.getByText('Page 1 of 49')).toBeInTheDocument();
  });

  it('says plainly when the selected table is empty', async () => {
    server.use(
      http.get('*/api/tables/:name', ({ params }) =>
        HttpResponse.json({ ...fx.tablePage, name: String(params.name), rows: [], total: 0 })
      )
    );
    renderWithProviders(<DataPage />);

    expect(await screen.findByText('This table has no rows yet.')).toBeInTheDocument();
    expect(screen.queryByRole('table', { name: 'price_bars' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Next' })).not.toBeInTheDocument();
  });

  it('lists the corporate actions already recorded', async () => {
    renderWithProviders(<DataPage />);

    const table = within(await screen.findByRole('table', { name: 'Corporate actions' }));
    expect(table.getByRole('cell', { name: 'NABIL' })).toBeInTheDocument();
    expect(table.getByRole('cell', { name: '2026-08-01' })).toBeInTheDocument();
    expect(table.getByRole('cell', { name: 'bonus 1:10' })).toBeInTheDocument();
    // The adjustment factor, trimmed to four places.
    expect(table.getByRole('cell', { name: '0.9091' })).toBeInTheDocument();
    expect(table.getByRole('cell', { name: 'AGM decision' })).toBeInTheDocument();
  });

  it('records a new corporate action and puts it at the top of the list', async () => {
    let body: Record<string, unknown> = {};
    const added = {
      ...fx.corporateActions[0],
      symbol: 'HBL',
      action_type: 'rights',
      description: 'rights 1:4',
    };
    server.use(
      http.post('*/api/corporate-actions', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(added);
      })
    );
    renderWithProviders(<DataPage />);
    await screen.findByRole('table', { name: 'Corporate actions' });

    const form = within(cardOf('Corporate actions'));
    await userEvent.type(form.getByRole('textbox', { name: 'Symbol' }), 'hbl');
    fireEvent.change(form.getByLabelText('Ex date'), { target: { value: '2026-09-01' } });
    await userEvent.selectOptions(form.getByRole('combobox', { name: 'Type' }), 'rights');
    await userEvent.clear(form.getByRole('spinbutton', { name: 'Ratio denominator' }));
    await userEvent.type(form.getByRole('spinbutton', { name: 'Ratio denominator' }), '4');
    await userEvent.click(form.getByRole('button', { name: 'Record' }));

    await waitFor(() => expect(body.symbol).toBe('HBL'));
    expect(body.ex_date).toBe('2026-09-01');
    expect(body.action_type).toBe('rights');
    expect(body.ratio_numerator).toBe(1);
    expect(body.ratio_denominator).toBe(4);
    // A blank note is left out rather than stored as an empty string.
    expect(body.notes).toBeUndefined();

    const table = within(screen.getByRole('table', { name: 'Corporate actions' }));
    expect(table.getByRole('cell', { name: 'rights 1:4' })).toBeInTheDocument();
    // The symbol field is cleared so the next entry starts clean.
    expect(form.getByRole('textbox', { name: 'Symbol' })).toHaveValue('');
  });

  it('surfaces a rejected corporate action', async () => {
    server.use(
      http.post('*/api/corporate-actions', () =>
        HttpResponse.json({ detail: 'ratio_denominator must be positive' }, { status: 400 })
      )
    );
    renderWithProviders(<DataPage />);
    await screen.findByRole('table', { name: 'Corporate actions' });

    const form = within(cardOf('Corporate actions'));
    await userEvent.type(form.getByRole('textbox', { name: 'Symbol' }), 'NABIL');
    fireEvent.change(form.getByLabelText('Ex date'), { target: { value: '2026-09-01' } });
    await userEvent.click(form.getByRole('button', { name: 'Record' }));

    expect(await screen.findByText(/ratio_denominator must be positive/)).toBeInTheDocument();
  });

  it('shows which sources exist and which ones settings actually use', async () => {
    renderWithProviders(<DataPage />);
    await screen.findByRole('heading', { level: 1, name: 'Data' });

    const sources = within(cardOf('Sources'));
    expect(sources.getByText('merolagani')).toBeInTheDocument();
    expect(sources.getByText('enabled')).toBeInTheDocument();
    expect(sources.getByText('in settings')).toBeInTheDocument();
    expect(sources.getByText('confidence high')).toBeInTheDocument();
    expect(sources.getByText('scrape · https://merolagani.com')).toBeInTheDocument();
    expect(sources.getByText('today_price')).toBeInTheDocument();

    // chukul is defined but not switched on in settings.
    expect(sources.getByText('chukul')).toBeInTheDocument();
    expect(sources.getByText('disabled')).toBeInTheDocument();
    expect(sources.getAllByText('in settings')).toHaveLength(1);
  });

  it('renders the error state when the database cannot be read', async () => {
    server.use(
      http.get('*/api/tables', () => new HttpResponse('database is locked', { status: 500 }))
    );
    renderWithProviders(<DataPage />);

    expect(await screen.findByText(/database is locked/)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { level: 1, name: 'Data' })).not.toBeInTheDocument();
  });
});
