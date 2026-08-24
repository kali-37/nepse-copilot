import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MeroSharePage } from './MeroShare';
import { renderWithProviders } from '../test/renderWithProviders';
import { server } from '../test/server';

describe('MeroSharePage', () => {
  it('shows the read-only boundary and mirrored holding', async () => {
    renderWithProviders(<MeroSharePage />);
    expect(await screen.findByRole('heading', { name: 'MeroShare' })).toBeInTheDocument();
    expect(screen.getByText('Read-only boundary')).toBeInTheDocument();
    expect(screen.getByRole('cell', { name: 'NABIL' })).toBeInTheDocument();
    expect(screen.getAllByText('NPR 12,750.00')).toHaveLength(2);
  });

  it('imports pasted CSV through the read-only endpoint', async () => {
    let received = '';
    server.use(
      http.post('*/api/meroshare/import', async ({ request }) => {
        const body = await request.json() as { csv_text: string };
        received = body.csv_text;
        return HttpResponse.json({ ok: true, method: 'csv', holdings: 1, transactions: 0, error: '', ran_at: '2026-08-22T10:00:00Z' });
      })
    );
    renderWithProviders(<MeroSharePage />);
    await screen.findByRole('heading', { name: 'MeroShare' });
    await userEvent.type(screen.getByRole('textbox', { name: 'Portfolio CSV' }), 'Symbol,Current Balance\nNABIL,10');
    await userEvent.click(screen.getByRole('button', { name: 'Import CSV' }));
    expect(await screen.findByText(/Imported 1 holdings/)).toBeInTheDocument();
    expect(received).toContain('NABIL,10');
  });
});
