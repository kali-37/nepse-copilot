import { useCallback, useEffect, useState } from 'react';
import { Database, Plug, Plus, Table2 } from 'lucide-react';
import { api } from '../api/client';
import type { CorporateActionRow, SourcesResponse, TablePage, TableSummary } from '../api/types';
import { Badge } from '../components/ui/Badge';
import { Card } from '../components/ui/Card';
import { DataTable } from '../components/ui/DataTable';
import { ErrorState } from '../components/ui/ErrorState';
import { LoadingSpinner } from '../components/ui/LoadingSpinner';

const PAGE_SIZE = 100;

function cell(value: unknown): string {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'number') return Number(value.toFixed(4)).toString();
  return String(value);
}

/** Manual entry for a bonus / rights / split / dividend. NEPSE publishes these
 *  as announcements, not as a feed, so somebody has to type them in. */
function CorporateActionForm({ onAdded }: { onAdded: (row: CorporateActionRow) => void }) {
  const [form, setForm] = useState({
    symbol: '',
    ex_date: '',
    action_type: 'bonus',
    ratio_numerator: 1,
    ratio_denominator: 10,
    notes: '',
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onAdded(
        await api.addCorporateAction({
          symbol: form.symbol.trim().toUpperCase(),
          ex_date: form.ex_date,
          action_type: form.action_type,
          ratio_numerator: Number(form.ratio_numerator),
          ratio_denominator: Number(form.ratio_denominator),
          notes: form.notes.trim() || undefined,
        })
      );
      setForm({ ...form, symbol: '', notes: '' });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="flex flex-wrap items-end gap-3">
      <label className="block text-sm">
        <span className="mb-1 block text-xs font-medium text-text-secondary">Symbol</span>
        <input
          required
          value={form.symbol}
          onChange={(e) => setForm({ ...form, symbol: e.target.value })}
          className="h-10 w-32 rounded-lg border border-border bg-surface px-3 text-sm uppercase text-text-primary"
        />
      </label>
      <label className="block text-sm">
        <span className="mb-1 block text-xs font-medium text-text-secondary">Ex date</span>
        <input
          required
          type="date"
          value={form.ex_date}
          onChange={(e) => setForm({ ...form, ex_date: e.target.value })}
          className="h-10 rounded-lg border border-border bg-surface px-3 text-sm text-text-primary"
        />
      </label>
      <label className="block text-sm">
        <span className="mb-1 block text-xs font-medium text-text-secondary">Type</span>
        <select
          value={form.action_type}
          onChange={(e) => setForm({ ...form, action_type: e.target.value })}
          className="h-10 rounded-lg border border-border bg-surface px-3 text-sm text-text-primary"
        >
          {['bonus', 'rights', 'split', 'dividend'].map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </label>
      <label className="block text-sm">
        <span className="mb-1 block text-xs font-medium text-text-secondary">Ratio</span>
        <span className="flex items-center gap-1">
          <input
            type="number"
            min={1}
            value={form.ratio_numerator}
            onChange={(e) => setForm({ ...form, ratio_numerator: Number(e.target.value) })}
            aria-label="Ratio numerator"
            className="h-10 w-16 rounded-lg border border-border bg-surface px-2 text-sm text-text-primary"
          />
          <span className="text-text-tertiary">:</span>
          <input
            type="number"
            min={1}
            value={form.ratio_denominator}
            onChange={(e) => setForm({ ...form, ratio_denominator: Number(e.target.value) })}
            aria-label="Ratio denominator"
            className="h-10 w-16 rounded-lg border border-border bg-surface px-2 text-sm text-text-primary"
          />
        </span>
      </label>
      <label className="block flex-1 text-sm">
        <span className="mb-1 block text-xs font-medium text-text-secondary">Notes</span>
        <input
          value={form.notes}
          onChange={(e) => setForm({ ...form, notes: e.target.value })}
          className="h-10 w-full min-w-40 rounded-lg border border-border bg-surface px-3 text-sm text-text-primary"
        />
      </label>
      <button
        disabled={busy}
        className="inline-flex h-10 items-center gap-2 rounded-lg bg-nepse-600 px-4 text-sm font-semibold text-white hover:bg-nepse-700 disabled:opacity-50"
      >
        <Plus className="h-4 w-4" />
        {busy ? 'Saving...' : 'Record'}
      </button>
      {error && <p className="w-full text-sm text-negative">{error}</p>}
    </form>
  );
}

export function DataPage() {
  const [tables, setTables] = useState<TableSummary[]>([]);
  const [sources, setSources] = useState<SourcesResponse | null>(null);
  const [actions, setActions] = useState<CorporateActionRow[]>([]);
  const [selected, setSelected] = useState<string>('');
  const [page, setPage] = useState<TablePage | null>(null);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [reading, setReading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.tables(), api.sources(), api.corporateActions()])
      .then(([nextTables, nextSources, nextActions]) => {
        setTables(nextTables.tables);
        setSources(nextSources);
        setActions(nextActions);
        setSelected(nextTables.tables[0]?.name ?? '');
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, []);

  const read = useCallback((name: string, at: number) => {
    if (!name) return;
    setReading(true);
    api
      .table(name, { limit: PAGE_SIZE, offset: at })
      .then(setPage)
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setReading(false));
  }, []);

  useEffect(() => {
    read(selected, offset);
  }, [read, selected, offset]);

  if (loading) return <LoadingSpinner text="Reading the database..." />;
  if (error && tables.length === 0) return <ErrorState message={error} />;

  const total = page?.total ?? 0;
  const shown = page?.rows.length ?? 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Data</h1>
        <p className="mt-1 text-sm text-text-secondary">
          Everything stored locally, rendered in the page. Nothing here is exported or downloaded
          &mdash; the database file itself is the artefact.
        </p>
      </div>

      <Card title="Tables">
        <div className="flex flex-wrap gap-1.5">
          {tables.map((table) => (
            <button
              key={table.name}
              onClick={() => {
                setSelected(table.name);
                setOffset(0);
              }}
              className={`rounded px-3 py-1.5 text-xs font-medium transition-colors ${
                selected === table.name
                  ? 'bg-nepse-600 text-white'
                  : 'bg-surface-tertiary text-text-secondary hover:text-text-primary'
              }`}
            >
              {table.name}
              <span className="ml-1.5 opacity-70">{table.rows.toLocaleString()}</span>
            </button>
          ))}
        </div>
      </Card>

      <Card
        title={selected || 'No table'}
        actions={
          total > 0 ? (
            <span className="text-xs text-text-tertiary">
              {offset + 1}&ndash;{offset + shown} of {total.toLocaleString()}
            </span>
          ) : undefined
        }
      >
        {reading ? (
          <LoadingSpinner text="Reading rows..." />
        ) : !page || page.rows.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-12 text-text-tertiary">
            <Table2 className="h-8 w-8" />
            <p className="text-sm">This table has no rows yet.</p>
          </div>
        ) : (
          <>
            <DataTable
              columns={page.columns.map((key) => ({
                key,
                label: key.replace(/_/g, ' '),
                render: (row: Record<string, unknown>) => cell(row[key]),
              }))}
              data={page.rows}
              label={selected}
            />
            {total > PAGE_SIZE && (
              <div className="mt-4 flex items-center justify-center gap-2 border-t border-border pt-4">
                <button
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                  className="rounded-lg px-3 py-1.5 text-sm font-medium text-text-secondary hover:bg-surface-tertiary disabled:opacity-40"
                >
                  Previous
                </button>
                <span className="text-sm text-text-tertiary">
                  Page {Math.floor(offset / PAGE_SIZE) + 1} of {Math.ceil(total / PAGE_SIZE)}
                </span>
                <button
                  disabled={offset + PAGE_SIZE >= total}
                  onClick={() => setOffset(offset + PAGE_SIZE)}
                  className="rounded-lg px-3 py-1.5 text-sm font-medium text-text-secondary hover:bg-surface-tertiary disabled:opacity-40"
                >
                  Next
                </button>
              </div>
            )}
          </>
        )}
      </Card>

      <Card title="Corporate actions">
        <p className="mb-4 text-sm text-text-secondary">
          Prices stay as published. This table records that a bonus or split happened, so a price
          gap can be explained instead of being read as a crash.
        </p>
        <CorporateActionForm onAdded={(row) => setActions([row, ...actions])} />
        <div className="mt-4">
          <DataTable
            columns={[
              { key: 'symbol', label: 'Symbol', sortable: true },
              { key: 'ex_date', label: 'Ex date', sortable: true },
              { key: 'action_type', label: 'Type' },
              { key: 'description', label: 'Description' },
              { key: 'factor', label: 'Factor', render: (row) => cell(row.factor) },
              { key: 'source', label: 'Source' },
              { key: 'notes', label: 'Notes', className: 'text-text-secondary' },
            ]}
            data={actions}
            label="Corporate actions"
          />
        </div>
      </Card>

      <Card title="Sources">
        <div className="space-y-3">
          {(sources?.sources ?? []).map((source) => (
            <div key={source.name} className="border-b border-border pb-3 last:border-0 last:pb-0">
              <div className="flex flex-wrap items-center gap-2">
                <Plug className="h-3.5 w-3.5 text-text-tertiary" />
                <span className="font-semibold text-text-primary">{source.name}</span>
                <Badge
                  text={source.enabled ? 'enabled' : 'disabled'}
                  variant={source.enabled ? 'success' : 'default'}
                />
                {sources?.enabled_in_settings.includes(source.name) && (
                  <Badge text="in settings" variant="info" />
                )}
                {source.confidence && <Badge text={`confidence ${source.confidence}`} />}
              </div>
              <p className="mt-1 text-xs text-text-tertiary">
                {source.access_method} · {source.base_url}
              </p>
              {source.endpoints.length > 0 && (
                <p className="mt-1 text-xs text-text-secondary">
                  {source.endpoints.map((ep) => ep.name).join(', ')}
                </p>
              )}
            </div>
          ))}
          {!sources?.sources.length && (
            <div className="flex flex-col items-center gap-2 py-8 text-text-tertiary">
              <Database className="h-8 w-8" />
              <p className="text-sm">No sources are configured.</p>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
}
