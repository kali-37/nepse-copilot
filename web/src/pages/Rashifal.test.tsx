import { describe, expect, it } from 'vitest';
import { http, HttpResponse, delay } from 'msw';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RashifalPage } from './Rashifal';
import { renderWithProviders } from '../test/renderWithProviders';
import { server } from '../test/server';
import * as fx from '../test/fixtures';

describe('RashifalPage', () => {
  it('renders the prescription, doses and confidence copy', async () => {
    renderWithProviders(<RashifalPage />);
    expect(await screen.findByRole('heading', { name: 'Rashifal' })).toBeInTheDocument();
    expect(screen.getAllByText('NABIL').length).toBeGreaterThan(0);
    expect(screen.getByText('Four doses')).toBeInTheDocument();
    expect(screen.getAllByText('more likely than not').length).toBeGreaterThan(0);
    expect(screen.getAllByText(/NPR 1,140.00/).length).toBeGreaterThan(0);
  });

  it('sends normal/offline settings and capital when running', async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post('*/api/advisor/run', async ({ request }) => {
        body = await request.json() as Record<string, unknown>;
        await delay(10);
        return HttpResponse.json(fx.rashifal);
      })
    );
    renderWithProviders(<RashifalPage />);
    await screen.findByRole('heading', { name: 'Rashifal' });
    await userEvent.clear(screen.getByRole('spinbutton', { name: 'Capital' }));
    await userEvent.type(screen.getByRole('spinbutton', { name: 'Capital' }), '250000');
    await userEvent.click(screen.getByRole('button', { name: 'Run prescription' }));
    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toMatchObject({ mode: 'normal', online: false, horizon: 'week', equity: 250000 });
  });

  it('shows expected versus realized outcomes, reviews and distilled lessons', async () => {
    server.use(http.get('*/api/journal/history', () => HttpResponse.json(fx.journalHistory)));
    renderWithProviders(<RashifalPage />);
    expect(await screen.findByText('Past calls & outcomes')).toBeInTheDocument();
    expect(screen.getByText('TARGET HIT')).toBeInTheDocument();
    expect(screen.getByText('NPR 840.00')).toBeInTheDocument();
    expect(screen.getByText(/The breakout held on improving breadth/)).toBeInTheDocument();
    expect(screen.getByText(/Require breadth confirmation/)).toBeInTheDocument();
  });

  it('can run the yearly prescription horizon', async () => {
    let body: Record<string, unknown> | null = null;
    server.use(http.post('*/api/advisor/run', async ({ request }) => {
      body = await request.json() as Record<string, unknown>;
      return HttpResponse.json({ ...fx.rashifal, horizon: 'year' });
    }));
    renderWithProviders(<RashifalPage />);
    await screen.findByRole('heading', { name: 'Rashifal' });
    await userEvent.click(screen.getByRole('button', { name: 'Year' }));
    await userEvent.click(screen.getByRole('button', { name: 'Run prescription' }));
    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toMatchObject({ horizon: 'year' });
  });
});
