import { useEffect, useMemo, useState } from 'react';
import { History, Play, Terminal } from 'lucide-react';
import { api } from '../api/client';
import type { Job, JobKind } from '../api/types';
import { JobConsole } from '../components/JobConsole';
import { Badge } from '../components/ui/Badge';
import { Card } from '../components/ui/Card';
import { DataTable } from '../components/ui/DataTable';
import { useJob } from '../hooks/useJob';

/** Which parameter controls each job kind exposes, and what it is for. */
interface KindSpec {
  kind: JobKind;
  label: string;
  blurb: string;
  fields: Array<'business_date' | 'since' | 'until' | 'source' | 'all_sources' | 'strategies' | 'top' | 'rank_by' | 'cash' | 'min_bars' | 'symbols' | 'recent_days' | 'news'>;
}

const KINDS: KindSpec[] = [
  { kind: 'fundamentals', label: 'Download fundamentals', blurb: 'Store dated company valuations and sectors for offline research and screening.', fields: ['symbols'] },
  { kind: 'floorsheet', label: 'Download broker trades', blurb: 'Store published matched contracts for broker buy/sell flow analysis.', fields: ['business_date'] },
  {
    kind: 'backfill',
    label: 'Download price history',
    blurb: 'Load published daily prices for your symbols, then cross-check and adjust them for stored corporate actions. Repeating this updates existing prices.',
    fields: ['symbols', 'since', 'until', 'source'],
  },
  {
    kind: 'run-daily',
    label: 'Daily run',
    blurb:
      'Download, cross-check, then the full analytics report. The one you would schedule. Skipped automatically when the date is not a NEPSE trading day.',
    fields: ['business_date', 'all_sources', 'strategies', 'top', 'rank_by', 'cash'],
  },
  {
    kind: 'ingest',
    label: 'Download prices',
    blurb: 'Pull public end-of-day data from the configured sources into the local database.',
    fields: ['business_date', 'all_sources'],
  },
  {
    kind: 'reconcile',
    label: 'Cross-check sources',
    blurb: 'Turn per-source prices into one confidence-scored consensus per symbol.',
    fields: ['business_date'],
  },
  {
    kind: 'screen',
    label: 'Backtest everything',
    blurb: 'Every strategy against every symbol, ranked. Full Nepal costs on each simulated fill.',
    fields: ['strategies', 'rank_by', 'cash', 'min_bars', 'top'],
  },
  {
    kind: 'rag-index',
    label: 'Rebuild search index',
    blurb:
      'Build the searchable evidence library from stored data. Offline unless you tick news, which fetches from the web.',
    fields: ['symbols', 'recent_days', 'strategies', 'news'],
  },
];

const RANK_OPTIONS = ['sharpe', 'total_return_pct', 'cagr_pct', 'max_drawdown_pct', 'win_rate_pct'];

const FIELD_LABEL: Record<string, string> = {
  business_date: 'Trading date',
  since: 'History from',
  until: 'History through (blank = today)',
  source: 'History source',
  all_sources: 'Every source, not just enabled ones',
  strategies: 'Strategies',
  top: 'Max symbols',
  rank_by: 'Rank by',
  cash: 'Starting cash (NPR)',
  min_bars: 'Skip symbols under N bars',
  symbols: 'Symbols (comma list, blank = all)',
  recent_days: 'Price days per symbol',
  news: 'Also fetch news (uses the network)',
};

const DEFAULTS: Record<string, string | number | boolean> = {
  business_date: '',
  since: '',
  until: '',
  source: 'sharesansar',
  all_sources: true,
  strategies: 'all',
  top: 25,
  rank_by: 'sharpe',
  cash: 100000,
  min_bars: 60,
  symbols: '',
  recent_days: 10,
  news: false,
};

/** Markdown sections are shown as-is. The report is already tables of text, and
 *  a markdown renderer would be a dependency for no extra clarity. */
function ReportSections({ sections }: { sections: Record<string, string> }) {
  const titles = Object.keys(sections);
  const [open, setOpen] = useState(titles[0] ?? '');
  if (titles.length === 0) return null;
  return (
    <div className="mt-4">
      <div className="flex flex-wrap gap-1.5">
        {titles.map((title) => (
          <button
            key={title}
            onClick={() => setOpen(title === open ? '' : title)}
            className={`rounded px-2.5 py-1 text-xs font-medium transition-colors ${
              open === title
                ? 'bg-nepse-600 text-white'
                : 'bg-surface-tertiary text-text-secondary hover:text-text-primary'
            }`}
          >
            {title}
          </button>
        ))}
      </div>
      {open && (
        <pre className="mt-3 max-h-96 overflow-auto rounded bg-surface-tertiary p-3 text-xs leading-relaxed text-text-secondary">
          {sections[open]}
        </pre>
      )}
    </div>
  );
}

function JobResult({ job }: { job: Job }) {
  const result = job.result;
  if (!result) return null;

  if (result.skipped) {
    return (
      <p className="mt-4 rounded border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-sm text-amber-600 dark:text-amber-400">
        Nothing to do — {String(result.reason)}.
      </p>
    );
  }

  const sections = result.sections as Record<string, string> | undefined;
  const summary = result.summary as Record<string, unknown> | undefined;
  const ingest = result.ingest as { per_source?: Record<string, number>; total_bars?: number } | undefined;
  const rows = result.rows as Array<Record<string, unknown>> | undefined;
  const perKind = result.per_kind as Record<string, number> | undefined;

  return (
    <div className="mt-4 space-y-4 border-t border-border pt-4">
      {summary && (
        <dl className="grid grid-cols-2 gap-x-6 gap-y-1.5 sm:grid-cols-3">
          {Object.entries(summary)
            .filter(([, v]) => v === null || typeof v !== 'object')
            .map(([key, value]) => (
              <div key={key} className="flex justify-between gap-3 text-sm">
                <dt className="text-text-tertiary">{key.replace(/_/g, ' ')}</dt>
                <dd className="font-medium text-text-primary">{value === null ? '—' : String(value)}</dd>
              </div>
            ))}
        </dl>
      )}

      {ingest?.per_source && (
        <div>
          <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-text-secondary">
            Rows per source ({ingest.total_bars ?? 0} total)
          </h4>
          <ul className="flex flex-wrap gap-2">
            {Object.entries(ingest.per_source).map(([name, count]) => (
              <li key={name}>
                <Badge text={`${name}: ${count}`} variant={count > 0 ? 'success' : 'default'} />
              </li>
            ))}
          </ul>
        </div>
      )}

      {perKind && (
        <div>
          <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-text-secondary">
            Documents indexed
          </h4>
          <ul className="flex flex-wrap gap-2">
            {Object.entries(perKind).map(([kind, count]) => (
              <li key={kind}>
                <Badge text={`${kind}: ${count}`} variant="info" />
              </li>
            ))}
          </ul>
        </div>
      )}

      {rows && rows.length > 0 && (
        <div>
          <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-text-secondary">
            {rows.length} row{rows.length === 1 ? '' : 's'}
          </h4>
          <DataTable
            columns={Object.keys(rows[0]).map((key) => ({
              key,
              label: key.replace(/_/g, ' '),
              render: (row: Record<string, unknown>) => {
                const value = row[key];
                if (value === null || value === undefined) return '—';
                if (Array.isArray(value)) return value.length ? value.join(', ') : '—';
                if (typeof value === 'number') return Number(value.toFixed(4)).toString();
                return String(value);
              },
            }))}
            data={rows}
          />
        </div>
      )}

      {sections && <ReportSections sections={sections} />}
    </div>
  );
}

export function OperationsPage() {
  const { job, error, starting, start, cancel, attach } = useJob();
  const [selected, setSelected] = useState<JobKind>('run-daily');
  const [params, setParams] = useState<Record<string, string | number | boolean>>(DEFAULTS);
  const [recent, setRecent] = useState<Job[]>([]);

  const spec = useMemo(() => KINDS.find((k) => k.kind === selected)!, [selected]);
  const status = job?.status;
  const busy = status === 'running' || status === 'queued';

  // On mount, re-attach to whatever is already running. A job started before
  // this tab existed — or before a reload — is still the operator's job.
  useEffect(() => {
    api
      .jobs(10)
      .then((list) => {
        setRecent(list.jobs);
        if (list.running) attach(list.running);
      })
      .catch(() => undefined);
  }, [attach]);

  // Refresh the history list each time a job reaches a terminal state.
  useEffect(() => {
    if (status && status !== 'running' && status !== 'queued') {
      api.jobs(10).then((list) => setRecent(list.jobs)).catch(() => undefined);
    }
  }, [status]);

  const run = () => {
    const payload: Record<string, unknown> = {};
    for (const field of spec.fields) {
      const value = params[field];
      // An empty text field means "use the server default" — sending "" would
      // override a real default with nothing.
      if (value === '' || value === undefined) continue;
      payload[field] = value;
    }
    void start(spec.kind, payload);
  };

  const setField = (field: string, value: string | number | boolean) =>
    setParams((prev) => ({ ...prev, [field]: value }));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Operations</h1>
        <p className="mt-1 text-sm text-text-secondary">
          The long-running commands, with live progress. Work continues on the server if you close
          this tab &mdash; reopen the page and it re-attaches. One job runs at a time.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,340px)_minmax(0,1fr)]">
        <div className="space-y-4">
          <Card title="What to run">
            <div className="space-y-1.5">
              {KINDS.map((k) => (
                <button
                  key={k.kind}
                  onClick={() => setSelected(k.kind)}
                  className={`w-full rounded-lg px-3 py-2 text-left text-sm transition-colors ${
                    selected === k.kind
                      ? 'bg-nepse-50 font-semibold text-nepse-700 dark:bg-nepse-900/30 dark:text-nepse-400'
                      : 'text-text-secondary hover:bg-surface-tertiary'
                  }`}
                >
                  {k.label}
                </button>
              ))}
            </div>
            <p className="mt-3 border-t border-border pt-3 text-xs text-text-tertiary">
              {spec.blurb}
            </p>
          </Card>

          <Card title="Options">
            <div className="space-y-3">
              {spec.fields.map((field) => {
                const value = params[field];
                if (typeof DEFAULTS[field] === 'boolean') {
                  return (
                    <label key={field} className="flex items-center gap-2 text-sm text-text-secondary">
                      <input
                        type="checkbox"
                        checked={Boolean(value)}
                        onChange={(e) => setField(field, e.target.checked)}
                        className="h-4 w-4 rounded border-border accent-nepse-600"
                      />
                      {FIELD_LABEL[field]}
                    </label>
                  );
                }
                if (field === 'rank_by' || field === 'source') {
                  return (
                    <label key={field} className="block text-sm">
                      <span className="text-text-secondary">{FIELD_LABEL[field]}</span>
                      <select
                        value={String(value)}
                        onChange={(e) => setField(field, e.target.value)}
                        className="mt-1 h-9 w-full rounded border border-border bg-surface px-2 text-sm text-text-primary"
                      >
                        {(field === 'source' ? ['sharesansar', 'chukul'] : RANK_OPTIONS).map((option) => (
                          <option key={option} value={option}>
                            {option.replace(/_/g, ' ')}
                          </option>
                        ))}
                      </select>
                    </label>
                  );
                }
                const numeric = typeof DEFAULTS[field] === 'number';
                return (
                  <label key={field} className="block text-sm">
                    <span className="text-text-secondary">{FIELD_LABEL[field]}</span>
                    <input
                      type={['business_date', 'since', 'until'].includes(field) ? 'date' : numeric ? 'number' : 'text'}
                      value={String(value ?? '')}
                      onChange={(e) =>
                        setField(field, numeric ? Number(e.target.value) : e.target.value)
                      }
                      className="mt-1 h-9 w-full rounded border border-border bg-surface px-2 text-sm text-text-primary"
                    />
                  </label>
                );
              })}
            </div>
            <button
              onClick={run}
              disabled={busy || starting}
              className="mt-4 inline-flex h-10 w-full items-center justify-center gap-2 rounded bg-nepse-600 text-sm font-semibold text-white hover:bg-nepse-700 disabled:opacity-50"
            >
              <Play className="h-4 w-4" />
              {busy ? 'A job is running' : starting ? 'Starting...' : `Run ${spec.label.toLowerCase()}`}
            </button>
            {error && <p className="mt-2 text-xs text-negative">{error}</p>}
          </Card>
        </div>

        <div className="space-y-4">
          {job ? (
            <JobConsole job={job} onCancel={() => void cancel()}>
              <JobResult job={job} />
            </JobConsole>
          ) : (
            <Card>
              <div className="flex flex-col items-center gap-2 py-12 text-center">
                <Terminal className="h-8 w-8 text-text-tertiary" />
                <p className="text-sm text-text-secondary">
                  Nothing running. Pick a command and press run.
                </p>
              </div>
            </Card>
          )}

          <Card title="Recent jobs">
            {recent.length === 0 ? (
              <p className="text-sm text-text-secondary">No jobs yet this session.</p>
            ) : (
              <ul className="space-y-2">
                {recent.map((row) => (
                  <li key={row.id} className="flex flex-wrap items-center gap-3 text-sm">
                    <History className="h-3.5 w-3.5 text-text-tertiary" />
                    <button
                      onClick={() => attach(row.id)}
                      className="font-medium text-nepse-600 hover:underline"
                    >
                      {row.kind}
                    </button>
                    <Badge
                      text={row.status}
                      variant={
                        row.status === 'done'
                          ? 'success'
                          : row.status === 'failed'
                            ? 'danger'
                            : row.status === 'running'
                              ? 'info'
                              : 'default'
                      }
                    />
                    <span className="text-xs text-text-tertiary">{row.created_at.slice(11, 19)}</span>
                  </li>
                ))}
              </ul>
            )}
            <p className="mt-3 border-t border-border pt-3 text-xs text-text-tertiary">
              History lives in memory and resets when the server restarts. The durable record of a
              run is the data it wrote.
            </p>
          </Card>
        </div>
      </div>
    </div>
  );
}
