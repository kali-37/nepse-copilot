import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { server } from '../../test/server';
import { PerformanceEvidence } from './PerformanceEvidence';
import { FundamentalsPanel } from './FundamentalsPanel';

const report = {
  engine_version: 'decision_v1', total: 1, resolved: 1, tracking_since: '2026-11-25T02:00:00Z',
  status: 'collecting_evidence', outcomes: { EXPIRED_UP: 1 }, method: 'Fixed100-share forward benchmark.',
  note: 'Small samples cannot establish an investment edge.', recent: [],
  buckets: [{ lower: .7, upper: .8, samples: 1, profitable_rate: 0,
    interval_low: 0, interval_high: .793, mean_score: .72, mean_net_return: -.8, mean_excess_return: 0 }],
};

describe('recommendation evidence', () => {
  it('loads the track record on demand and shows net profitability without calling scores probabilities', async () => {
    let reads = 0;
    server.use(http.get('*/api/decisions/performance', () => { reads++; return HttpResponse.json(report); }));
    render(<PerformanceEvidence />);
    expect(reads).toBe(0);
    await userEvent.click(screen.getByText('Recommendation track record · measured evidence'));
    await screen.findByText('Collecting evidence');
    expect(reads).toBe(1);
    expect(screen.getByText('0.0%')).toBeInTheDocument();
    expect(screen.getByText('-0.8%')).toBeInTheDocument();
    expect(screen.getByText(/not calibrated win probabilities/)).toBeInTheDocument();
  });

  it('shows absent prospective evidence without inventing historical success', async () => {
    server.use(http.get('*/api/decisions/performance', () => HttpResponse.json({ ...report, total: 0, resolved: 0, buckets: [], outcomes: {} })));
    render(<PerformanceEvidence />);
    await userEvent.click(screen.getByText('Recommendation track record · measured evidence'));
    await screen.findByText(/Past calls are not imported/);
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });

  it('explains fund-specific missing evidence without displaying fake company ratios', () => {
    render(<FundamentalsPanel report={{ asset_kind: 'mutual_fund', rating: 'fund_review',
      source: 'Public snapshot', snapshot_date: '2026-11-25', eps: null, book_value: null,
      current_pe: null, current_pbv: null, multiplier: 0, needs_refresh: false,
      reasons: ['Dated NAV and fund terms need review.'], limitations: ['NAV is not verified.'] }} />);
    expect(screen.getByText('Mutual fund · valuation review needed')).toBeInTheDocument();
    expect(screen.queryByText('Reported EPS')).not.toBeInTheDocument();
    expect(screen.getByText(/Company earnings rules are not applied/)).toBeInTheDocument();
  });
});
