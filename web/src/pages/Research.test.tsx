import { describe, expect, it } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ResearchPage } from './Research';
import { renderWithProviders } from '../test/renderWithProviders';

describe('ResearchPage', () => {
  it('shows corpus coverage and recent research', async () => {
    renderWithProviders(<ResearchPage />);
    expect(await screen.findByRole('heading', { name: 'Research' })).toBeInTheDocument();
    expect(screen.getByText('1250')).toBeInTheDocument();
    expect(screen.getByText('FTS5 / BM25')).toBeInTheDocument();
  });

  it('searches and displays citation evidence', async () => {
    renderWithProviders(<ResearchPage />);
    await screen.findByRole('heading', { name: 'Research' });
    await userEvent.type(screen.getByRole('textbox', { name: 'Research query' }), 'NABIL');
    await userEvent.click(screen.getByRole('button', { name: 'Search evidence' }));
    expect(await screen.findByText('NABIL update')).toBeInTheDocument();
    expect(screen.getByText(/Citation pack/)).toBeInTheDocument();
  });
});
