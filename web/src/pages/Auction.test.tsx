import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AuctionPage } from './Auction';
import { renderWithProviders } from '../test/renderWithProviders';
import { server } from '../test/server';
import * as fx from '../test/fixtures';

describe('AuctionPage', () => {
  it('renders the manual-only fee ladder and saved advice', async () => {
    renderWithProviders(<AuctionPage />);
    expect(await screen.findByRole('heading', { name: 'Auction advice' })).toBeInTheDocument();
    expect(screen.getByText('Advice only. No bid is submitted.')).toBeInTheDocument();
    expect(screen.getAllByText('Conservative ceiling').length).toBeGreaterThan(0);
    expect(screen.getAllByText('NABIL').length).toBeGreaterThan(0);
    expect(screen.getByText('NPR 108.00')).toBeInTheDocument();
  });

  it('sends the explicit auction assumptions to the advice endpoint', async () => {
    let body: Record<string, unknown> | null = null;
    server.use(http.post('*/api/auction/advice', async ({ request }) => {
      body = await request.json() as Record<string, unknown>;
      return HttpResponse.json(fx.auctionAdvice);
    }));
    renderWithProviders(<AuctionPage />);
    await screen.findByRole('heading', { name: 'Auction advice' });
    await userEvent.type(screen.getByRole('textbox', { name: 'Auction symbol' }), 'NABIL');
    await userEvent.click(screen.getByRole('button', { name: 'Calculate advice' }));
    expect(await screen.findByText('NPR 315.00')).toBeInTheDocument();
    expect(body).toMatchObject({ symbol: 'NABIL', units: 10, min_bid_price: 100, edge_buffer_pct: 0.1 });
  });
});
