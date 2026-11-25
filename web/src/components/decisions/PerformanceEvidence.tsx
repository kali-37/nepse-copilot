import { useEffect, useState } from 'react';
import { decisionApi, type RecommendationPerformance } from '../../api/decisions';

const percent = (value: number | null) => value === null ? '—' : `${value.toFixed(1)}%`;

export function PerformanceEvidence() {
  const [open, setOpen] = useState(false);
  const [report, setReport] = useState<RecommendationPerformance | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!open || report) return;
    let active = true;
    void decisionApi.performance().then(data => { if (active) setReport(data); })
      .catch(e => { if (active) setError(e instanceof Error ? e.message : String(e)); });
    return () => { active = false; };
  }, [open, report]);
  return <details className="source-details performance-evidence" onToggle={e => setOpen(e.currentTarget.open)}>
    <summary>Recommendation track record · measured evidence</summary>
    {error && <p role="alert">{error}</p>}
    {open && !report && !error && <p role="status">Reading the recommendation journal…</p>}
    {report && <>
      <p><strong>{report.status === 'collecting_evidence' ? 'Collecting evidence' : 'Recorded historical outcomes'}</strong> · {report.resolved} resolved / {report.total} published ideas.</p>
      <p>Evidence scores are not calibrated win probabilities. These are simulated outcomes of ideas recorded before future prices were known.</p>
      {!report.total && <p>Tracking begins with fresh published buy ideas. Past calls are not imported as successful predictions.</p>}
      <p>{report.outcomes.NOT_ENTERED ?? 0} unfilled · {report.outcomes.EXCLUDED ?? 0} excluded for corporate actions · {report.outcomes.NO_DATA ?? 0} awaiting usable data. These do not enter the profitable rate.</p>
      {report.resolved > 0 && <div className="performance-table-wrap"><table><caption>Outcomes by original evidence score</caption><thead><tr><th>Score</th><th>Samples</th><th>Profitable</th><th>95% interval</th><th>Mean net return</th></tr></thead><tbody>{report.buckets.filter(b => b.samples > 0).map(b => <tr key={b.lower}><td>{Math.round(b.lower * 100)}–{Math.round(b.upper * 100)}%</td><td>{b.samples}</td><td>{percent(b.profitable_rate === null ? null : b.profitable_rate * 100)}</td><td>{percent(b.interval_low === null ? null : b.interval_low * 100)}–{percent(b.interval_high === null ? null : b.interval_high * 100)}</td><td>{percent(b.mean_net_return)}</td></tr>)}</tbody></table></div>}
      <p>{report.note}</p>
      <details><summary>How outcomes are measured</summary><p>{report.method}</p><p>Engine: {report.engine_version} · Tracking since {report.tracking_since ? new Date(report.tracking_since).toLocaleDateString('en-NP') : 'not started'}.</p></details>
    </>}
  </details>;
}
