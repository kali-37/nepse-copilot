import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { JobConsole } from './JobConsole';
import * as fx from '../test/fixtures';

describe('JobConsole', () => {
  it('lists every stage, with a counter only where the work is countable', () => {
    render(<JobConsole job={fx.runningJob} />);

    expect(screen.getByText('Job run-daily')).toBeInTheDocument();
    expect(screen.getByText('Download from sources')).toBeInTheDocument();
    expect(screen.getByText('Cross-check sources')).toBeInTheDocument();
    expect(screen.getByText('Signals, stats and backtests')).toBeInTheDocument();

    // Only the reconcile stage reports a total, so only it gets an x/y counter.
    expect(screen.getByText('12/244')).toBeInTheDocument();
    expect(screen.queryByText('0/0')).not.toBeInTheDocument();
    // Per-stage detail is the live "what it is chewing on right now".
    expect(screen.getByText('NABIL')).toBeInTheDocument();
  });

  it('draws a progress bar only for a running stage that counts', () => {
    render(<JobConsole job={fx.runningJob} />);

    // 12 of 244 ≈ 5%.
    const bar = screen.getByRole('progressbar', { name: 'Cross-check sources progress' });
    expect(bar).toHaveAttribute('aria-valuenow', '5');
    expect(bar).toHaveAttribute('aria-valuemax', '100');
    // The finished stage and the pending one get no bar.
    expect(screen.getAllByRole('progressbar')).toHaveLength(1);
  });

  it('keeps the counter but drops the bar once a stage finishes', () => {
    render(<JobConsole job={fx.doneJob} />);

    expect(screen.getByText('244/244')).toBeInTheDocument();
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
  });

  it('shows the job status and the log tail', () => {
    render(<JobConsole job={fx.doneJob} />);

    expect(screen.getByText('done')).toBeInTheDocument();
    expect(screen.getByLabelText('Job log')).toHaveTextContent(
      'reconciled 244 symbols; 3 low-confidence/disputed'
    );
  });

  it('omits the log element entirely when nothing has been logged', () => {
    render(<JobConsole job={{ ...fx.doneJob, log: [] }} />);

    expect(screen.queryByLabelText('Job log')).not.toBeInTheDocument();
  });

  it('surfaces the failure reason of a failed job', () => {
    render(<JobConsole job={fx.failedJob} />);

    expect(screen.getByText('failed')).toBeInTheDocument();
    expect(
      screen.getByText('No symbols in the database yet — ingest and reconcile first.')
    ).toBeInTheDocument();
  });

  it('offers Cancel while the job is alive and calls back when pressed', async () => {
    const onCancel = vi.fn();
    render(<JobConsole job={fx.runningJob} onCancel={onCancel} />);

    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it('disables Cancel once cancellation has been asked for', () => {
    render(
      <JobConsole job={{ ...fx.runningJob, cancel_requested: true }} onCancel={vi.fn()} />
    );

    // Cooperative cancel: the job stops at its next checkpoint, not instantly,
    // so the button says what is actually happening.
    const button = screen.getByRole('button', { name: 'Stopping...' });
    expect(button).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Cancel' })).not.toBeInTheDocument();
  });

  it('hides Cancel on a job that has already finished', () => {
    render(<JobConsole job={fx.doneJob} onCancel={vi.fn()} />);

    expect(screen.queryByRole('button', { name: /Cancel|Stopping/ })).not.toBeInTheDocument();
  });

  it('renders the result view only once the job has succeeded', () => {
    const result = <p>the in-page result</p>;

    render(<JobConsole job={fx.runningJob}>{result}</JobConsole>);
    expect(screen.queryByText('the in-page result')).not.toBeInTheDocument();

    render(<JobConsole job={fx.failedJob}>{result}</JobConsole>);
    expect(screen.queryByText('the in-page result')).not.toBeInTheDocument();

    render(<JobConsole job={fx.doneJob}>{result}</JobConsole>);
    expect(screen.getByText('the in-page result')).toBeInTheDocument();
  });
});
