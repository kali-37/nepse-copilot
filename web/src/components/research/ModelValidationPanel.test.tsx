import { beforeEach, describe, expect, it } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import type { ModelSummary } from '../../api/modelValidation';
import { server } from '../../test/server';
import { ModelValidationPanel } from './ModelValidationPanel';

const makeModel = (passed = true): ModelSummary => ({
  id: 'model-test', horizon_days: 3, created_at: '2026-11-25T08:00:00Z', data_as_of: '2026-11-24',
  status: passed ? 'candidate' : 'rejected', gate: { passed, reasons: passed ? [] : ['Too few held-out outcomes for advisory use.'] },
  metrics: { test_samples: 250, test_dates: 60, brier_score: .19, baseline_brier_score: .25,
    log_loss: .58, baseline_log_loss: .69, ece: .04, auc: .72, selected_trades: 90,
    mean_net_return: .6, coverage: .8 },
  boundaries: { train_end: '2025-12-31', calibration_end: '2026-06-30', test_end: '2026-11-24' },
  limitations: ['Modeled fills are not broker-confirmed trades.'],
});
let models: ModelSummary[];
let reads: number;

beforeEach(() => {
  models = []; reads = 0;
  server.use(http.get('*/api/research/models', () => {
    reads++;
    return HttpResponse.json({ models, active: Object.fromEntries(models.filter(m => m.status === 'active').map(m => [String(m.horizon_days), m.id])) });
  }));
});

async function openPanel() {
  render(<ModelValidationPanel />);
  await userEvent.click(screen.getByText('Trained model validation'));
}

describe('trained model validation', () => {
  it('loads saved versions only when opened and explains the probability event', async () => {
    render(<ModelValidationPanel />);
    expect(reads).toBe(0);
    await userEvent.click(screen.getByText('Trained model validation'));
    await screen.findByText(/No trained versions yet/);
    expect(reads).toBe(1);
    expect(screen.getByText(/conditional on the saved entry zone filling/)).toBeInTheDocument();
  });

  it('keeps a rejected model out of advisory use and shows its rejection evidence', async () => {
    models = [makeModel(false)];
    await openPanel();
    await screen.findByText('Research only');
    expect(screen.getByText('Too few held-out outcomes for advisory use.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Enable daily advisory' })).toBeDisabled();
    await userEvent.click(screen.getByText('Training boundaries & limitations'));
    expect(screen.getByText('2025-12-31')).toBeInTheDocument();
    expect(screen.getByText('2026-06-30')).toBeInTheDocument();
  });

  it('activates only after the server accepts a passed model and supports disabling it', async () => {
    let activations = 0;
    models = [makeModel()];
    server.use(
      http.post('*/api/research/models/model-test/activate', () => {
        activations++; models = [{ ...models[0], status: 'active' }]; return HttpResponse.json(models[0]);
      }),
      http.delete('*/api/research/models/active/3', () => {
        models = [{ ...models[0], status: 'candidate' }]; return HttpResponse.json({ disabled: true });
      }),
    );
    await openPanel();
    await screen.findByText('Validation passed');
    await userEvent.click(screen.getByRole('button', { name: 'Enable daily advisory' }));
    await screen.findByText('Advisory enabled');
    expect(activations).toBe(1);
    await userEvent.click(screen.getByRole('button', { name: 'Disable daily advisory' }));
    await screen.findByText('Validation passed');
    expect(screen.getByRole('button', { name: 'Enable daily advisory' })).toBeEnabled();
  });

  it('leaves rejected activation unchanged when the server reports a validation conflict', async () => {
    models = [makeModel()];
    server.use(http.post('*/api/research/models/model-test/activate', () => HttpResponse.json({ detail: 'Validation became stale; reevaluate this model.' }, { status: 409 })));
    await openPanel();
    await screen.findByText('Validation passed');
    await userEvent.click(screen.getByRole('button', { name: 'Enable daily advisory' }));
    await screen.findByRole('alert');
    expect(screen.getByRole('alert')).toHaveTextContent('Validation became stale');
    expect(screen.queryByText('Advisory enabled')).not.toBeInTheDocument();
  });

  it('retains confirmed activation if the following list refresh fails', async () => {
    models = [makeModel()];
    server.use(
      http.get('*/api/research/models', () => {
        reads++;
        return reads > 1 ? HttpResponse.json({ detail: 'Model list temporarily unavailable' }, { status: 503 }) : HttpResponse.json({ models, active: {} });
      }),
      http.post('*/api/research/models/model-test/activate', () => HttpResponse.json({ ...models[0], status: 'active' })),
    );
    await openPanel();
    await screen.findByText('Validation passed');
    await userEvent.click(screen.getByRole('button', { name: 'Enable daily advisory' }));
    await screen.findByRole('alert');
    expect(screen.getByText('Advisory enabled')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Disable daily advisory' })).toBeEnabled();
  });

  it('shows an active model as blocked when its current validation gate fails', async () => {
    models = [{ ...makeModel(false), status: 'active' }];
    await openPanel();
    await screen.findByText('Advisory blocked');
    expect(screen.getByRole('button', { name: 'Disable daily advisory' })).toBeEnabled();
    expect(screen.queryByRole('button', { name: 'Enable daily advisory' })).not.toBeInTheDocument();
  });

  it('blocks a historically passing version after its serving eligibility expires', async () => {
    models = [{ ...makeModel(), advisory_eligible: false, advisory_block_reason: 'Validation is stale. Evaluate a new version.' }];
    await openPanel();
    await screen.findByText('Advisory blocked');
    expect(screen.getByText('Validation is stale. Evaluate a new version.')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Enable daily advisory' })).toBeDisabled();
  });

  it('displays missing validation metrics as unknown instead of fabricated zeros', async () => {
    const model = makeModel(false);
    model.metrics = Object.fromEntries(Object.keys(model.metrics).map(k => [k, null])) as ModelSummary['metrics'];
    models = [model];
    await openPanel();
    await screen.findByText('Research only');
    expect(screen.getAllByText('— / —')).toHaveLength(2);
    expect(screen.queryByText('0.000')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Enable daily advisory' })).toBeDisabled();
  });

  it('shows held-out calibration with observed outcomes and sample accounting', async () => {
    models = [{
      ...makeModel(false),
      diagnostics: {
        reliability: [{ lower: .5, upper: .6, samples: 20, mean_probability: .55, observed_rate: .4, interval_low: .22, interval_high: .61 }],
        sampling: { attempted_calls: 400, eligible_calls: 320 },
        raw: { brier: .23, ece: .11, log_loss: .67 },
        chart_rule_baseline: { samples: 15, mean_net_return_pct: -.25 },
        matched_hold_mean_return_pct: .45,
        date_block_uncertainty: {
          method: '95% circular moving-block bootstrap over chronological prediction dates',
          block_dates: 4, full_blocks: 15, replicates: 400,
          brier_improvement_over_train: { lower: -.01, upper: .025 },
          brier_improvement_over_calibration: { lower: -.012, upper: .022 },
          selected_net_return_pct: { lower: -.1, upper: .4 },
          selected_excess_return_pct: { lower: null, upper: null },
        },
      },
    }];
    await openPanel();
    await userEvent.click(await screen.findByText('Calibration & sample coverage'));
    expect(screen.getByRole('table', { name: 'Held-out probability calibration' })).toBeVisible();
    expect(screen.getByText('55.0%')).toBeVisible();
    expect(screen.getByText('40.0%')).toBeVisible();
    expect(screen.getByText('22.0%–61.0%')).toBeVisible();
    expect(screen.getByText('-0.10% to 0.40%')).toBeVisible();
    expect(screen.getByText('Unmeasured')).toBeVisible();
    expect(screen.getByText('eligible calls')).toBeVisible();
  });

  it('submits fixed chronological training and reloads versions after job completion', async () => {
    let submission: unknown;
    server.use(
      http.post('*/api/jobs', async ({ request }) => {
        submission = await request.json();
        return HttpResponse.json({ id: 'training-1', kind: 'train-model', status: 'queued', stages: [] });
      }),
      http.get('*/api/jobs/training-1', () => {
        models = [makeModel()];
        return HttpResponse.json({ id: 'training-1', kind: 'train-model', status: 'done', stages: [] });
      }),
    );
    await openPanel();
    await screen.findByText(/No trained versions yet/);
    await userEvent.click(screen.getByRole('button', { name: 'Evaluate daily model' }));
    await waitFor(() => expect(submission).toEqual({ kind: 'train-model', params: { horizon_days: 3, max_symbols: 150, max_sessions: 1000 } }));
    expect(screen.getByRole('button', { name: 'Evaluate monthly model' })).toBeDisabled();
    await screen.findByText('Validation passed', {}, { timeout: 4000 });
    expect(screen.getByText(/Evaluation complete/)).toBeInTheDocument();
    expect(reads).toBeGreaterThan(1);
  });

  it('reattaches to an already running model evaluation', async () => {
    server.use(
      http.get('*/api/jobs', () => HttpResponse.json({ jobs: [], running: 'existing-model', kinds: ['train-model'] })),
      http.get('*/api/jobs/existing-model', () => HttpResponse.json({
        id: 'existing-model', kind: 'train-model', status: 'running', stages: [{ name: 'fit', label: 'Calibrating held-out predictions', status: 'running', detail: 'Separate calibration window', current: 3, total: 5 }],
      })),
    );
    await openPanel();
    await screen.findByText('Calibrating held-out predictions');
    expect(screen.getByText('3 / 5')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Evaluate daily model' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Cancel evaluation' })).toBeEnabled();
  });
});
