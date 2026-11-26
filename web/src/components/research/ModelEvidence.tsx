import type { ModelSummary } from '../../api/modelValidation';
import { Badge } from '../ui/Badge';
import { Card } from '../ui/Card';

function metric(value: number | null, digits = 3, suffix = '') {
  return typeof value === 'number' && Number.isFinite(value) ? `${value.toFixed(digits)}${suffix}` : '—';
}

function percent(value: number | null, digits = 1) {
  return value == null ? '—' : metric(value * 100, digits, '%');
}

function ModelDiagnostics({ diagnostics }: { diagnostics: NonNullable<ModelSummary['diagnostics']> }) {
  const { reliability, raw, sampling, chart_rule_baseline: chartBaseline } = diagnostics;
  const uncertainty = diagnostics.date_block_uncertainty;
  const bins = reliability.filter(band => band.samples > 0);
  return (
    <details className="mt-4 text-sm">
      <summary className="cursor-pointer font-medium text-text-secondary">Calibration & sample coverage</summary>
      <div className="mt-3 space-y-4">
        <dl className="grid gap-3 text-text-secondary sm:grid-cols-3">
          <div><dt className="text-xs">Brier before calibration</dt><dd className="font-mono">{metric(raw.brier)}</dd></div>
          <div><dt className="text-xs">Chart-rule mean net return</dt><dd className="font-mono">{metric(chartBaseline.mean_net_return_pct, 2, '%')} ({chartBaseline.samples} trades)</dd></div>
          <div><dt className="text-xs">Matched buy-and-hold mean return</dt><dd className="font-mono">{metric(diagnostics.matched_hold_mean_return_pct, 2, '%')}</dd></div>
        </dl>
        {diagnostics.calibration_base_rate && (
          <p className="text-xs text-text-secondary">
            Calibration-window base-rate benchmark scored {metric(diagnostics.calibration_base_rate.brier)} Brier and {metric(diagnostics.calibration_base_rate.log_loss)} log loss on the held-out test.
          </p>
        )}
        {uncertainty && (
          <div>
            <p className="font-medium text-text-primary">Held-out uncertainty</p>
            <p className="mt-1 text-xs text-text-secondary">{uncertainty.method} · {uncertainty.full_blocks} full blocks of {uncertainty.block_dates} dates</p>
            <dl className="mt-2 grid gap-2 text-xs text-text-secondary sm:grid-cols-2">
              {([
                ['Brier improvement over the training base rate', uncertainty.brier_improvement_over_train, 4, ''],
                ['Brier improvement over the calibration base rate', uncertainty.brier_improvement_over_calibration, 4, ''],
                ['Selected trades’ mean net return', uncertainty.selected_net_return_pct, 2, '%'],
                ['Selected trades’ mean excess over matched hold', uncertainty.selected_excess_return_pct, 2, '%'],
              ] as const).map(([label, range, digits, suffix]) => (
                <div key={label} className="rounded-lg bg-surface-secondary p-2">
                  <dt>{label}</dt>
                  <dd className="mt-1 font-mono">
                    {range.lower != null && range.upper != null
                      ? `${metric(range.lower, digits, suffix)} to ${metric(range.upper, digits, suffix)}`
                      : 'Unmeasured'}
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        )}
        {bins.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs leading-5 text-text-secondary">
              <caption className="pb-2 text-left font-medium text-text-primary">Held-out probability calibration</caption>
              <thead>
                <tr className="border-b border-border">
                  <th scope="col" className="pr-2 pb-2 font-medium">Range</th>
                  <th scope="col" className="pr-2 pb-2 font-medium">Trades</th>
                  <th scope="col" className="pr-2 pb-2 font-medium">Mean estimate</th>
                  <th scope="col" className="pb-2 font-medium">Profitable</th>
                </tr>
              </thead>
              <tbody>
                {bins.map(band => (
                  <tr className="border-b border-border tabular-nums" key={band.lower}>
                    <th scope="row" className="py-2 pr-2 font-medium">{percent(band.lower, 0)}–{percent(band.upper, 0)}</th>
                    <td className="py-2 pr-2">{band.samples.toLocaleString()}</td>
                    <td className="py-2 pr-2">{percent(band.mean_probability)}</td>
                    <td className="py-2">
                      {percent(band.observed_rate)}
                      {band.interval_low != null && band.interval_high != null && (
                        <span className="block text-text-tertiary">{percent(band.interval_low)}–{percent(band.interval_high)}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {uncertainty && <p className="mt-2 text-xs text-text-secondary">The intervals use blocks of adjacent dates and resample stocks from each date together.</p>}
          </div>
        )}
        <div>
          <p className="font-medium text-text-primary">Sample accounting</p>
          <dl className="mt-2 grid gap-x-4 gap-y-1 text-xs text-text-secondary sm:grid-cols-2">
            {Object.entries(sampling).map(([key, count]) => (
              <div key={key} className="flex min-w-0 justify-between gap-2">
                <dt>{key.replaceAll('_', ' ')}</dt>
                <dd className="font-mono">{count.toLocaleString()}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>
    </details>
  );
}

export function ModelEvidence({ model, busy, onActivate, onDisable, buttonClass }: {
  model: ModelSummary;
  busy: boolean;
  onActivate: () => void;
  onDisable: () => void;
  buttonClass: string;
}) {
  const active = model.status === 'active';
  const mayEnable = model.gate.passed && model.status !== 'rejected' && model.advisory_eligible !== false;
  const status = mayEnable
    ? active ? 'Advisory enabled' : 'Validation passed'
    : active || model.gate.passed ? 'Advisory blocked' : 'Research only';
  const metrics = model.metrics;
  const horizon = model.horizon_days === 3 ? 'Daily' : model.horizon_days === 22 ? 'Monthly' : `${model.horizon_days}-session`;
  const partitions = model.diagnostics?.partitions;
  return (
    <Card>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-text-primary">{horizon} model · {model.horizon_days} trading sessions</h3>
        <Badge text={status} variant={active && mayEnable ? 'success' : mayEnable ? 'info' : 'warning'} />
      </div>
      <p className="mt-2 text-xs text-text-secondary">Data through {model.data_as_of} · Evaluated {model.created_at.slice(0, 10)}</p>
      <dl className="mt-4 grid grid-cols-2 gap-2 text-sm lg:grid-cols-4">
        {[
          ['Held-out samples', metric(metrics.test_samples, 0)],
          ['Held-out dates', metric(metrics.test_dates, 0)],
          ['Brier / training base rate', `${metric(metrics.brier_score)} / ${metric(metrics.baseline_brier_score)}`],
          ['Log loss / training base rate', `${metric(metrics.log_loss)} / ${metric(metrics.baseline_log_loss)}`],
          ['Calibration error', percent(metrics.ece)],
          ['AUC', metric(metrics.auc)],
          ['Selected test trades', metric(metrics.selected_trades, 0)],
          ['Mean net return', metric(metrics.mean_net_return, 2, '%')],
        ].map(([label, value]) => (
          <div key={label} className="min-w-0 rounded-lg bg-surface-secondary p-3">
            <dt className="text-xs text-text-secondary">{label}</dt>
            <dd className="mt-1 break-words font-mono font-medium text-text-primary">{value}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-3 text-xs leading-5 text-text-secondary">Lower Brier and log loss are better. Eligible trades account for {percent(metrics.coverage)} of attempted entries across all partitions.</p>
      {model.gate.reasons.length > 0 && (
        <div className="mt-4 rounded-lg border border-border p-3 text-sm">
          <strong className="text-text-primary">Validation findings</strong>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-text-secondary">
            {model.gate.reasons.map(reason => <li key={reason}>{reason}</li>)}
          </ul>
        </div>
      )}
      <details className="mt-4 text-sm">
        <summary className="cursor-pointer font-medium text-text-secondary">Training boundaries & limitations</summary>
        {partitions ? (
          <dl className="mt-3 grid gap-3 text-xs text-text-secondary sm:grid-cols-3">
            {([['train', 'Training'], ['calibration', 'Calibration'], ['test', 'Final test']] as const).map(([key, label]) => {
              const window = partitions[key];
              return (
                <div className="rounded-lg bg-surface-secondary p-2" key={key}>
                  <dt className="font-semibold text-text-primary">{label}</dt>
                  <dd>Signals {window.start} to {window.end}</dd>
                  <dd>Outcomes through {window.label_end}</dd>
                  <dd>{window.samples.toLocaleString()} trades across {window.distinct_dates} dates</dd>
                </div>
              );
            })}
          </dl>
        ) : (
          <dl className="mt-3 grid gap-2 text-text-secondary sm:grid-cols-3">
            <div><dt className="text-xs">Training signals end</dt><dd>{model.boundaries.train_end ?? '—'}</dd></div>
            <div><dt className="text-xs">Calibration signals end</dt><dd>{model.boundaries.calibration_end ?? '—'}</dd></div>
            <div><dt className="text-xs">Final test outcomes end</dt><dd>{model.boundaries.test_end ?? '—'}</dd></div>
          </dl>
        )}
        <ul className="mt-3 list-disc space-y-1 pl-5 text-text-secondary">
          {model.limitations.map(limit => <li key={limit}>{limit}</li>)}
        </ul>
        <dl className="mt-3 break-all text-xs text-text-secondary">
          <div><dt className="inline font-medium">Version</dt>{' '}<dd className="inline font-mono">{model.id}</dd></div>
          {model.diagnostics?.dataset_fingerprint && <div><dt className="inline font-medium">Dataset fingerprint</dt>{' '}<dd className="inline font-mono">{model.diagnostics.dataset_fingerprint}</dd></div>}
          {model.diagnostics?.policy_fingerprint && <div><dt className="inline font-medium">Label policy fingerprint</dt>{' '}<dd className="inline font-mono">{model.diagnostics.policy_fingerprint}</dd></div>}
        </dl>
      </details>
      {model.diagnostics && <ModelDiagnostics diagnostics={model.diagnostics} />}
      <div className="mt-4">
        {model.gate.passed && model.advisory_block_reason && <p className="mb-2 text-sm text-text-secondary">{model.advisory_block_reason}</p>}
        {active ? (
          <button className={buttonClass} disabled={busy} onClick={onDisable}>Disable {horizon.toLowerCase()} advisory</button>
        ) : (
          <button className={buttonClass} disabled={busy || !mayEnable} onClick={onActivate}>Enable {horizon.toLowerCase()} advisory</button>
        )}
      </div>
    </Card>
  );
}
