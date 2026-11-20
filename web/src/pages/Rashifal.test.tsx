import { it, expect } from 'vitest';
import { http, HttpResponse } from 'msw';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { RashifalPage } from './Rashifal';
import { renderWithProviders } from '../test/renderWithProviders';
import { server } from '../test/server';
import { decisionBoard } from '../test/decisionFixture';
it('Rashifal starts with monthly advice and keeps daily buys one tap away', async () => {
  server.use(http.get('*/api/decisions', () => HttpResponse.json(decisionBoard)));
  renderWithProviders(<RashifalPage />);
  expect(await screen.findByText('EBL')).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Your Rashifal.' })).toBeInTheDocument();
  expect(screen.getByRole('tab', { name: 'Monthly' })).toHaveAttribute('aria-selected', 'true');
  await userEvent.click(screen.getByRole('tab', { name: 'Daily' }));
  expect(screen.getByText('NABIL')).toBeInTheDocument();
});
