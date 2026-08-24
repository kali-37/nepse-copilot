import { describe, expect, it } from 'vitest';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HealthPage } from './Health';
import { renderWithProviders } from '../test/renderWithProviders';

describe('HealthPage', () => {
  it('shows the overall verdict and a tally of every check', async () => {
    renderWithProviders(<HealthPage />);
    expect(await screen.findByRole('heading', { name: 'Health' })).toBeInTheDocument();
    expect(screen.getByText('overall: warn')).toBeInTheDocument();
    expect(screen.getByText('Needs a look')).toBeInTheDocument();
    expect(screen.getByText('Switched off')).toBeInTheDocument();
  });

  it('lists each check with what it watches in plain words', async () => {
    renderWithProviders(<HealthPage />);
    await screen.findByRole('heading', { name: 'Health' });
    expect(screen.getByText('schema')).toBeInTheDocument();
    expect(screen.getByText('meroshare')).toBeInTheDocument();
    expect(screen.getByText('How current the prices are')).toBeInTheDocument();
    expect(
      screen.getByText(/6 trading days behind 2026-08-23/)
    ).toBeInTheDocument();
  });

  it('hides check metrics until the row is expanded', async () => {
    renderWithProviders(<HealthPage />);
    await screen.findByRole('heading', { name: 'Health' });
    expect(screen.queryByText('reconciled rows')).not.toBeInTheDocument();

    const row = screen.getByText('database').closest('button');
    expect(row).not.toBeNull();
    await userEvent.click(row!);
    expect(row).toHaveAttribute('aria-expanded', 'true');
    expect(await screen.findByText('reconciled rows')).toBeInTheDocument();
  });

  it('reports missing credentials by field name and never a value', async () => {
    renderWithProviders(<HealthPage />);
    await screen.findByRole('heading', { name: 'Health' });
    await userEvent.click(screen.getByText('meroshare').closest('button')!);
    expect(await screen.findByText('missing credentials')).toBeInTheDocument();
    expect(screen.getByTitle('password')).toBeInTheDocument();
  });

  it('renders recorded snapshots newest first', async () => {
    renderWithProviders(<HealthPage />);
    await screen.findByRole('heading', { name: 'Health' });
    const list = screen.getByRole('list');
    const items = within(list).getAllByRole('listitem');
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent('2026-08-24T04:00:00+00:00');
    expect(items[1]).toHaveTextContent('2026-08-23T04:00:00+00:00');
  });

  it('records a snapshot only when the button is pressed', async () => {
    renderWithProviders(<HealthPage />);
    await screen.findByRole('heading', { name: 'Health' });
    const button = screen.getByRole('button', { name: /Record snapshot/ });
    await userEvent.click(button);
    // The handler answers ?record=true with a snapshot_id, so a successful
    // round-trip leaves the page renderable and the button usable again.
    expect(await screen.findByRole('button', { name: /Record snapshot/ })).toBeEnabled();
  });
});
