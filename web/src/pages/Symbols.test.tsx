import { describe, expect, it } from 'vitest';
import { http, HttpResponse, delay } from 'msw';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SymbolsPage } from './Symbols';
import { renderWithProviders } from '../test/renderWithProviders';
import { server } from '../test/server';
import * as fx from '../test/fixtures';

describe('SymbolsPage', () => {
  it('renders without crashing', () => {
    expect(() => renderWithProviders(<SymbolsPage />)).not.toThrow();
  });

  it('shows a loading state before the symbols arrive', async () => {
    server.use(
      http.get('*/api/symbols', async () => {
        await delay(50);
        return HttpResponse.json(fx.symbols);
      })
    );
    renderWithProviders(<SymbolsPage />);
    expect(screen.getByText('Loading symbols...')).toBeInTheDocument();
    await waitFor(() =>
      expect(
        screen.getByRole('heading', { level: 1, name: 'Symbols' })
      ).toBeInTheDocument()
    );
  });

  it('renders the happy path: a button per symbol and a count', async () => {
    renderWithProviders(<SymbolsPage />);

    expect(
      await screen.findByRole('heading', { level: 1, name: 'Symbols' })
    ).toBeInTheDocument();
    expect(screen.getByText('5 of 5 symbols')).toBeInTheDocument();

    for (const sym of fx.symbols) {
      expect(screen.getByRole('button', { name: sym })).toBeInTheDocument();
    }
  });

  it('filters symbols as the user types in the search box', async () => {
    renderWithProviders(<SymbolsPage />);
    await screen.findByRole('button', { name: 'NABIL' });

    await userEvent.type(
      screen.getByPlaceholderText('Search symbols...'),
      'nab'
    );

    expect(screen.getByText('1 of 5 symbols')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'NABIL' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'HBL' })).not.toBeInTheDocument();
  });

  it('shows a no-match message when the search excludes everything', async () => {
    renderWithProviders(<SymbolsPage />);
    await screen.findByRole('button', { name: 'NABIL' });

    await userEvent.type(
      screen.getByPlaceholderText('Search symbols...'),
      'zzzz'
    );

    expect(
      screen.getByText('No symbols match your search')
    ).toBeInTheDocument();
  });

  it('renders the empty state when the database has no symbols', async () => {
    server.use(http.get('*/api/symbols', () => HttpResponse.json([])));
    renderWithProviders(<SymbolsPage />);

    expect(
      await screen.findByText('No symbols in database')
    ).toBeInTheDocument();
    expect(screen.getByText('0 of 0 symbols')).toBeInTheDocument();
  });

  it('renders the error state when the request fails', async () => {
    server.use(
      http.get(
        '*/api/symbols',
        () => new HttpResponse('symbols unavailable', { status: 500 })
      )
    );
    renderWithProviders(<SymbolsPage />);

    expect(await screen.findByText(/symbols unavailable/)).toBeInTheDocument();
    expect(
      screen.queryByRole('heading', { level: 1, name: 'Symbols' })
    ).not.toBeInTheDocument();
  });

  it('navigates to the symbol detail route when a symbol is clicked', async () => {
    renderWithProviders(<SymbolsPage />, { route: '/symbols' });
    await userEvent.click(await screen.findByRole('button', { name: 'NABIL' }));

    // The detail route is not mounted in this render, so the symbol grid
    // unmounts once navigation happens.
    await waitFor(() =>
      expect(
        screen.queryByRole('button', { name: 'NABIL' })
      ).not.toBeInTheDocument()
    );
  });
});
