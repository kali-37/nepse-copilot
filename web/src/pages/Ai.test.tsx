import { describe, expect, it } from 'vitest';
import { http, HttpResponse, delay } from 'msw';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AiPage } from './Ai';
import { renderWithProviders } from '../test/renderWithProviders';
import { server } from '../test/server';
import * as fx from '../test/fixtures';

/** The <Card> body that carries the given title. */
function cardOf(title: string): HTMLElement {
  return screen.getByRole('heading', { name: title }).parentElement!.parentElement!;
}

/** The <StatCard> body carrying the given label. */
function statOf(label: string): HTMLElement {
  return screen.getByText(label).parentElement!.parentElement!;
}

describe('AiPage', () => {
  it('renders without crashing', () => {
    expect(() => renderWithProviders(<AiPage />)).not.toThrow();
  });

  it('shows a loading state before the configuration is read', async () => {
    server.use(
      http.get('*/api/ai/models', async () => {
        await delay(50);
        return HttpResponse.json(fx.aiModels);
      })
    );
    renderWithProviders(<AiPage />);

    expect(screen.getByText('Reading provider configuration...')).toBeInTheDocument();
    expect(await screen.findByRole('heading', { level: 1, name: 'AI' })).toBeInTheDocument();
  });

  it('summarises legs, spend and cache', async () => {
    renderWithProviders(<AiPage />);
    await screen.findByRole('heading', { level: 1, name: 'AI' });

    expect(within(statOf('Usable legs')).getByText('2')).toBeInTheDocument();
    expect(within(statOf('Usable legs')).getByText('online')).toBeInTheDocument();
    expect(within(statOf('Calls today')).getByText('2 / 20')).toBeInTheDocument();
    expect(within(statOf('Calls today')).getByText('18 left')).toBeInTheDocument();
    expect(within(statOf('Tokens today')).getByText('1,000')).toBeInTheDocument();
    expect(within(statOf('Tokens today')).getByText('9,000 left')).toBeInTheDocument();
    expect(within(statOf('Cached answers')).getByText('7')).toBeInTheDocument();
    expect(within(statOf('Cached answers')).getByText('24h TTL')).toBeInTheDocument();
  });

  it('shows each tier as an ordered chain with a per-leg verdict', async () => {
    renderWithProviders(<AiPage />);
    await screen.findByRole('heading', { level: 1, name: 'AI' });

    const chains = within(cardOf('Provider chains'));
    expect(chains.getByText('bulk')).toBeInTheDocument();
    expect(chains.getByText('synthesis')).toBeInTheDocument();
    expect(chains.getByText('groq')).toBeInTheDocument();
    expect(chains.getByText('llama-3.3-70b')).toBeInTheDocument();
    // A configured key is 'ready'; a known provider without one is 'no key'.
    expect(chains.getAllByText('ready')).toHaveLength(2);
    expect(chains.getByText('no key')).toBeInTheDocument();
    // The order legs are tried in is the whole point of a chain, and each tier
    // numbers its own legs from one.
    expect(chains.getAllByText('1.')).toHaveLength(2);
    expect(chains.getAllByText('2.')).toHaveLength(1);
  });

  it('flags a provider name it does not recognise, and an empty tier', async () => {
    server.use(
      http.get('*/api/ai/models', () =>
        HttpResponse.json({
          ...fx.aiModels,
          usable_legs: 0,
          banner: 'No usable provider is configured — prose will be skipped.',
          tiers: {
            bulk: [{ name: 'kwikllm', known: false, available: false, model: null }],
            synthesis: [],
          },
        })
      )
    );
    renderWithProviders(<AiPage />);

    expect(
      await screen.findByText('No usable provider is configured — prose will be skipped.')
    ).toBeInTheDocument();
    const chains = within(cardOf('Provider chains'));
    expect(chains.getByText('unknown provider')).toBeInTheDocument();
    expect(chains.getByText('No legs configured for this tier.')).toBeInTheDocument();
  });

  it('calls nobody until the test button is pressed', async () => {
    let posts = 0;
    server.use(
      http.post('*/api/ai/test', () => {
        posts += 1;
        return HttpResponse.json(fx.aiTestOk);
      })
    );
    renderWithProviders(<AiPage />);
    await screen.findByRole('heading', { level: 1, name: 'AI' });

    // Opening the page must never spend budget.
    expect(posts).toBe(0);
    expect(screen.getByText('No test has been run this session.')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Test this chain' }));

    await waitFor(() => expect(posts).toBe(1));
  });

  it('shows what answered, and re-reads the budget the call just spent', async () => {
    let budgetReads = 0;
    server.use(
      http.get('*/api/ai/budget', () => {
        budgetReads += 1;
        return HttpResponse.json({
          ...fx.aiBudget,
          calls: budgetReads === 1 ? 2 : 3,
          calls_left: budgetReads === 1 ? 18 : 17,
        });
      })
    );
    renderWithProviders(<AiPage />);
    await screen.findByRole('heading', { level: 1, name: 'AI' });

    await userEvent.click(screen.getByRole('button', { name: 'Test this chain' }));

    const panel = within(cardOf('Send one test prompt'));
    expect(await panel.findByText('answered')).toBeInTheDocument();
    expect(panel.getByText('anthropic')).toBeInTheDocument();
    expect(panel.getByText('claude-sonnet-5')).toBeInTheDocument();
    expect(panel.getByText('42 tokens')).toBeInTheDocument();
    expect(panel.getByText('pong')).toBeInTheDocument();

    // The call it just made is reflected in the counters.
    await waitFor(() =>
      expect(within(statOf('Calls today')).getByText('3 / 20')).toBeInTheDocument()
    );
  });

  it('sends the chosen tier', async () => {
    let body: Record<string, unknown> = {};
    server.use(
      http.post('*/api/ai/test', async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...fx.aiTestOk, tier: 'bulk', provider: 'groq' });
      })
    );
    renderWithProviders(<AiPage />);
    await screen.findByRole('heading', { level: 1, name: 'AI' });

    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Tier' }), 'bulk');
    await userEvent.click(screen.getByRole('button', { name: 'Test this chain' }));

    await waitFor(() => expect(body.tier).toBe('bulk'));
  });

  it('reports a chain that nobody answered without failing the page', async () => {
    server.use(
      http.post('*/api/ai/test', () =>
        HttpResponse.json({
          ok: false,
          tier: 'synthesis',
          provider: null,
          model: null,
          total_tokens: 0,
          text: '',
          error: 'anthropic: 401 invalid x-api-key',
        })
      )
    );
    renderWithProviders(<AiPage />);
    await screen.findByRole('heading', { level: 1, name: 'AI' });

    await userEvent.click(screen.getByRole('button', { name: 'Test this chain' }));

    const panel = within(cardOf('Send one test prompt'));
    expect(await panel.findByText('no answer')).toBeInTheDocument();
    expect(panel.getByText('anthropic: 401 invalid x-api-key')).toBeInTheDocument();
    // A provider that refuses is not a broken dashboard.
    expect(screen.getByRole('heading', { level: 1, name: 'AI' })).toBeInTheDocument();
  });

  it('says the ledger is empty when no call has been made', async () => {
    renderWithProviders(<AiPage />);

    expect(
      await screen.findByText('The ledger is empty — no AI call has been made yet.')
    ).toBeInTheDocument();
    expect(cardOf('Recent spend')).toHaveTextContent(
      'Caps reset daily (2026-08-22) and weekly (2026-W34). Deep passes: 0 of 2 used.'
    );
  });

  it('lists the spend ledger once there is something in it', async () => {
    server.use(
      http.get('*/api/ai/budget', () =>
        HttpResponse.json({
          ...fx.aiBudget,
          history: [
            {
              at: '2026-08-22T09:00:00Z',
              provider: 'anthropic',
              tier: 'synthesis',
              tokens: 812,
              cost_usd: 0.004123456,
              cached: false,
            },
          ],
        })
      )
    );
    renderWithProviders(<AiPage />);

    const table = within(await screen.findByRole('table'));
    expect(table.getByRole('columnheader', { name: 'cost usd' })).toBeInTheDocument();
    expect(table.getByRole('cell', { name: 'anthropic' })).toBeInTheDocument();
    expect(table.getByRole('cell', { name: '812' })).toBeInTheDocument();
    // Costs are trimmed to four places rather than shown at full float width.
    expect(table.getByRole('cell', { name: '0.0041' })).toBeInTheDocument();
    expect(table.getByRole('cell', { name: 'false' })).toBeInTheDocument();
  });

  it('renders the error state when the provider configuration cannot be read', async () => {
    server.use(
      http.get('*/api/ai/models', () => new HttpResponse('settings unreadable', { status: 500 }))
    );
    renderWithProviders(<AiPage />);

    expect(await screen.findByText(/settings unreadable/)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { level: 1, name: 'AI' })).not.toBeInTheDocument();
  });
});
