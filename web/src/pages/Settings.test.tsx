import { describe, expect, it } from 'vitest';
import { http, HttpResponse } from 'msw';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SettingsPage } from './Settings';
import { renderWithProviders } from '../test/renderWithProviders';
import { server } from '../test/server';
import * as fx from '../test/fixtures';

describe('SettingsPage', () => {
  it('renders service state and the configured watchlist', async () => {
    renderWithProviders(<SettingsPage />);
    expect(await screen.findByRole('heading', { name: 'Settings' })).toBeInTheDocument();
    expect(screen.getByDisplayValue('NABIL')).toBeInTheDocument();
    expect(screen.getAllByText('Enabled').length).toBeGreaterThan(0);
    expect(screen.getByText('18')).toBeInTheDocument();
  });

  it('saves an edited watchlist', async () => {
    renderWithProviders(<SettingsPage />);
    await screen.findByRole('heading', { name: 'Settings' });
    const input = screen.getByLabelText('Symbols');
    await userEvent.clear(input);
    await userEvent.type(input, 'NICA, HBL');
    await userEvent.click(screen.getByRole('button', { name: 'Save watchlist' }));
    expect(await screen.findByText('Saved 1 watchlist symbols.')).toBeInTheDocument();
  });

  it('persists the MeroShare integration toggle and refreshes effective status', async () => {
    server.use(
      http.put('*/api/settings/meroshare', () => HttpResponse.json({ enabled: false, source: 'database', env_enabled: false, updated_at: '2026-08-24T00:00:00Z' })),
      http.get('*/api/meroshare/status', () => HttpResponse.json({ ...fx.meroshareStatus, enabled: false })),
    );
    renderWithProviders(<SettingsPage />);
    await screen.findByRole('heading', { name: 'Settings' });
    const toggle = screen.getByRole('checkbox', { name: 'Enable MeroShare integration' });
    expect(toggle).toBeChecked();
    await userEvent.click(toggle);
    expect(await screen.findByText('MeroShare integration disabled.')).toBeInTheDocument();
  });
});
