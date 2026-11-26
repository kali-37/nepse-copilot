import { describe, expect, it } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { ResearchPage } from './Research';
import { renderWithProviders } from '../test/renderWithProviders';
import { server } from '../test/server';

describe('ResearchPage', () => {
  it('shows corpus coverage and recent research', async () => {
    renderWithProviders(<ResearchPage />);
    expect(await screen.findByRole('heading', { name: 'Research' })).toBeInTheDocument();
    expect(await screen.findByText('1250')).toBeInTheDocument();
    expect(screen.getByText('FTS5 / BM25')).toBeInTheDocument();
  });

  it('searches and displays citation evidence', async () => {
    renderWithProviders(<ResearchPage />);
    await userEvent.type(await screen.findByRole('textbox', { name: 'Research query' }), 'NABIL');
    await userEvent.click(screen.getByRole('button', { name: 'Search evidence' }));
    expect(await screen.findByText('NABIL update')).toBeInTheDocument();
    expect(screen.getByText(/Citation pack/)).toBeInTheDocument();
  });

  it('distinguishes provider inventory from current matched statements and links to source checks', async () => {
    server.use(http.get('*/api/research/financial-evidence', () => HttpResponse.json({
      provider_symbols: 90, matched_symbols: 1, complete_symbols: 0, symbols: [
        { symbol: 'NABIL', period_end: '2026-07-15', period_basis: 'annual', metrics: ['eps', 'book_value'], status: 'matched_official_excerpt' },
        { symbol: 'EBL', period_end: '2023-07-15', period_basis: 'annual', metrics: [], status: 'stale' },
      ],
    })));
    renderWithProviders(<ResearchPage />);
    await userEvent.click(screen.getByText('Financial evidence coverage'));
    expect(await screen.findByRole('link', { name: 'NABIL' })).toHaveAttribute('href', '/symbols/NABIL');
    expect(screen.getByText('Symbols with provider snapshots')).toBeVisible();
    expect(screen.getByText('90')).toBeVisible();
    expect(screen.getByText('Symbols with current matched official evidence')).toBeVisible();
    expect(screen.getByText('1')).toBeVisible();
    expect(screen.getByText('Symbols passing all required verified checks').parentElement).toHaveTextContent('0');
    expect(screen.getByText('2 matched values')).toBeVisible();
    expect(screen.getByText('Stale evidence')).toBeVisible();
  });
});
