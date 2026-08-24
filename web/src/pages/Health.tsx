import { useEffect, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  CircleSlash,
  History,
  XCircle,
} from 'lucide-react';
import { api } from '../api/client';
import type { HealthCheck, HealthReport, HealthSnapshot, HealthStatus } from '../api/types';
import { Badge } from '../components/ui/Badge';
import { Card } from '../components/ui/Card';
import { ErrorState } from '../components/ui/ErrorState';
import { LoadingSpinner } from '../components/ui/LoadingSpinner';
import { StatCard } from '../components/ui/StatCard';

const BADGE_VARIANT: Record<HealthStatus, 'success' | 'warning' | 'danger' | 'default'> = {
  ok: 'success',
  warn: 'warning',
  fail: 'danger',
  off: 'default',
};

const ICONS: Record<HealthStatus, React.ReactNode> = {
  ok: <CheckCircle2 className="h-4 w-4 text-positive" />,
  warn: <AlertTriangle className="h-4 w-4 text-amber-500" />,
  fail: <XCircle className="h-4 w-4 text-negative" />,
  off: <CircleSlash className="h-4 w-4 text-text-tertiary" />,
};

/** What each check is actually watching, in plain words. */
const WHAT_IT_WATCHES: Record<string, string> = {
  schema: 'Database migrations applied',
  database: 'Row counts and file size',
  freshness: 'How current the prices are',
  ingest: 'Recent download success rate',
  config: 'YAML config and enabled sources',
  rag: 'Evidence library and ranked search',
  ai: 'Provider availability and token budget',
  meroshare: 'Read-only holdings mirror',
  journal: 'Prediction lifecycle backlog',
  paper: 'Simulated portfolio replay',
};

function metricRows(metrics: Record<string, unknown>): Array<[string, string]> {
  return Object.entries(metrics).map(([key, value]) => {
    const text =
      value === null || value === undefined
        ? '—'
        : Array.isArray(value)
          ? value.length
            ? value.join(', ')
            : '—'
          : typeof value === 'object'
            ? JSON.stringify(value)
            : String(value);
    return [key.replace(/_/g, ' '), text];
  });
}

function CheckRow({ check }: { check: HealthCheck }) {
  const [open, setOpen] = useState(false);
  const rows = metricRows(check.metrics);
  return (
    <div className="border-b border-border py-3 last:border-b-0">
      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="flex w-full items-start gap-3 text-left"
      >
        <span className="mt-0.5">{ICONS[check.status]}</span>
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-semibold capitalize text-text-primary">{check.name}</span>
            <Badge text={check.status} variant={BADGE_VARIANT[check.status]} />
            <span className="text-xs text-text-tertiary">{WHAT_IT_WATCHES[check.name] ?? ''}</span>
          </span>
          <span className="mt-1 block text-sm text-text-secondary">{check.detail}</span>
        </span>
      </button>
      {open && rows.length > 0 && (
        <dl className="mt-3 ml-7 grid gap-x-6 gap-y-1 sm:grid-cols-2">
          {rows.map(([label, value]) => (
            <div key={label} className="flex justify-between gap-3 text-xs">
              <dt className="text-text-tertiary">{label}</dt>
              <dd className="truncate font-medium text-text-secondary" title={value}>
                {value}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}

export function HealthPage() {
  const [report, setReport] = useState<HealthReport | null>(null);
  const [history, setHistory] = useState<HealthSnapshot[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [recording, setRecording] = useState(false);

  const load = () => {
    setLoading(true);
    setError(null);
    Promise.all([api.healthReport(), api.healthHistory(20)])
      .then(([nextReport, nextHistory]) => {
        setReport(nextReport);
        setHistory(nextHistory);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  // Recording is an explicit act, not a side effect of viewing: plain reads must
  // never grow the snapshot table.
  const record = async () => {
    setRecording(true);
    try {
      setReport(await api.healthReport(true));
      setHistory(await api.healthHistory(20));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRecording(false);
    }
  };

  if (error && !report) return <ErrorState message={error} onRetry={load} />;
  if (loading || !report) return <LoadingSpinner text="Checking every moving part..." />;

  const counts = report.counts;
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">Health</h1>
          <p className="mt-1 text-sm text-text-secondary">
            Every check is a local read — nothing is downloaded and no AI budget is spent
            &middot; generated {report.generated_at}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Badge text={`overall: ${report.status}`} variant={BADGE_VARIANT[report.status]} />
          <button
            onClick={() => void record()}
            disabled={recording}
            className="inline-flex h-10 items-center gap-2 rounded bg-nepse-600 px-4 text-sm font-semibold text-white hover:bg-nepse-700 disabled:opacity-50"
          >
            <History className="h-4 w-4" />
            {recording ? 'Recording...' : 'Record snapshot'}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Healthy" value={counts.ok ?? 0} icon={ICONS.ok} />
        <StatCard label="Needs a look" value={counts.warn ?? 0} icon={ICONS.warn} />
        <StatCard label="Failing" value={counts.fail ?? 0} icon={ICONS.fail} />
        <StatCard label="Switched off" value={counts.off ?? 0} icon={ICONS.off} />
      </div>

      <Card title="Checks">
        <div>
          {report.checks.map((check) => (
            <CheckRow key={check.name} check={check} />
          ))}
        </div>
      </Card>

      <Card title="Recorded snapshots">
        {history.length === 0 ? (
          <p className="text-sm text-text-secondary">
            Nothing recorded yet. Use <span className="font-medium">Record snapshot</span>, or run{' '}
            <code className="rounded bg-surface-tertiary px-1">health --record</code> from cron.
          </p>
        ) : (
          <ul className="space-y-2">
            {history.map((row) => (
              <li key={row.id} className="flex flex-wrap items-center gap-3 text-sm">
                <Activity className="h-3.5 w-3.5 text-text-tertiary" />
                <span className="text-text-secondary">{row.captured_at}</span>
                <Badge text={row.status} variant={BADGE_VARIANT[row.status]} />
                <span className="text-xs text-text-tertiary">
                  {row.ok} ok &middot; {row.warn} warn &middot; {row.fail} fail &middot; {row.off} off
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
