import { useEffect, useState } from 'react';
import { Activity, Filter, Radar, Sigma } from 'lucide-react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';
import type { BulkSignalsResponse, BulkStatsResponse } from '../api/types';
import { Badge } from '../components/ui/Badge';
import { Card } from '../components/ui/Card';
import { DataTable } from '../components/ui/DataTable';
import { LoadingSpinner } from '../components/ui/LoadingSpinner';
import { StatCard } from '../components/ui/StatCard';

const ACTION_VARIANT: Record<string, 'success' | 'danger' | 'default'> = {
  BUY: 'success',
  SELL: 'danger',
  HOLD: 'default',
};

const DEFAULT_STRATEGY = 'sma_cross';

function num(value: unknown, digits = 2): string {
  if (value === null || value === undefined) return '—';
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed.toFixed(digits) : String(value);
}

export function SignalsPage() {
  const [strategies, setStrategies] = useState<string[]>([]);
  const [strategy, setStrategy] = useState(DEFAULT_STRATEGY);
  const [symbols, setSymbols] = useState('');
  const [top, setTop] = useState(25);
  const [actionableOnly, setActionableOnly] = useState(false);
  const [signals, setSignals] = useState<BulkSignalsResponse | null>(null);
  const [stats, setStats] = useState<BulkStatsResponse | null>(null);
  const [tab, setTab] = useState<'signals' | 'stats'>('signals');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // The registry is fixed per build, so this is fetched once. If it cannot be
  // read the picker still offers the default the API itself defaults to.
  useEffect(() => {
    api
      .strategies()
      .then((res) => setStrategies(res.strategies))
      .catch(() => setStrategies([DEFAULT_STRATEGY]));
  }, []);

  const run = async () => {
    setLoading(true);
    setError(null);
    const list = symbols.trim() ? symbols.trim().toUpperCase() : undefined;
    try {
      if (tab === 'signals') {
        setSignals(await api.bulkSignals({ strategy, symbols: list, top, actionableOnly }));
      } else {
        setStats(await api.bulkStats({ symbols: list, top }));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const rows = signals?.rows ?? [];
  const buys = rows.filter((row) => row.action === 'BUY').length;
  const sells = rows.filter((row) => row.action === 'SELL').length;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Signals</h1>
        <p className="mt-1 text-sm text-text-secondary">
          The latest signal for every symbol at once, and the quantitative table behind it. A signal
          is a description of price history, not a recommendation.
        </p>
      </div>

      {signals && (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatCard label="Symbols evaluated" value={signals.count} icon={<Radar className="h-4 w-4" />} />
          <StatCard label="Buy" value={buys} changeType="positive" />
          <StatCard label="Sell" value={sells} changeType="negative" />
          <StatCard label="Strategy" value={signals.strategy} icon={<Activity className="h-4 w-4" />} />
        </div>
      )}

      <Card>
        <div className="mb-4 flex gap-1.5">
          {(['signals', 'stats'] as const).map((name) => (
            <button
              key={name}
              onClick={() => setTab(name)}
              className={`rounded px-3 py-1.5 text-sm font-medium transition-colors ${
                tab === name
                  ? 'bg-nepse-600 text-white'
                  : 'bg-surface-tertiary text-text-secondary hover:text-text-primary'
              }`}
            >
              {name === 'signals' ? 'Signals' : 'Statistics'}
            </button>
          ))}
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            void run();
          }}
          className="flex flex-wrap items-end gap-4"
        >
          {tab === 'signals' && (
            <label className="block text-sm">
              <span className="mb-1 block text-xs font-medium text-text-secondary">Strategy</span>
              <select
                value={strategy}
                onChange={(e) => setStrategy(e.target.value)}
                className="h-10 rounded-lg border border-border bg-surface px-3 text-sm text-text-primary"
              >
                {strategies.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
          )}

          <label className="block text-sm">
            <span className="mb-1 block text-xs font-medium text-text-secondary">
              Symbols (blank = first N stored)
            </span>
            <input
              value={symbols}
              onChange={(e) => setSymbols(e.target.value)}
              placeholder="NABIL,ADBL"
              className="h-10 w-52 rounded-lg border border-border bg-surface px-3 text-sm uppercase text-text-primary"
            />
          </label>

          <label className="block text-sm">
            <span className="mb-1 block text-xs font-medium text-text-secondary">How many</span>
            <input
              type="number"
              value={top}
              min={1}
              max={500}
              onChange={(e) => setTop(Number(e.target.value))}
              className="h-10 w-24 rounded-lg border border-border bg-surface px-3 text-sm text-text-primary"
            />
          </label>

          {tab === 'signals' && (
            <label className="flex h-10 items-center gap-2 text-sm text-text-secondary">
              <input
                type="checkbox"
                checked={actionableOnly}
                onChange={(e) => setActionableOnly(e.target.checked)}
                className="h-4 w-4 rounded border-border accent-nepse-600"
              />
              <Filter className="h-3.5 w-3.5" /> Actionable only
            </label>
          )}

          <button
            disabled={loading}
            className="inline-flex h-10 items-center gap-2 rounded-lg bg-nepse-600 px-5 text-sm font-semibold text-white hover:bg-nepse-700 disabled:opacity-50"
          >
            {tab === 'signals' ? <Radar className="h-4 w-4" /> : <Sigma className="h-4 w-4" />}
            {loading ? 'Working...' : tab === 'signals' ? 'Read signals' : 'Compute statistics'}
          </button>
        </form>

        {tab === 'signals' && (
          <p className="mt-3 text-xs text-text-tertiary">
            Reading signals recomputes them from stored prices and saves the result, so the numbers
            here match what the advisor sees.
          </p>
        )}
      </Card>

      {error && (
        <div className="border-l-4 border-negative bg-red-50 p-3 text-sm text-negative dark:bg-red-900/20">
          {error}
        </div>
      )}

      {loading && <LoadingSpinner text="Working through the symbols..." />}

      {!loading && tab === 'signals' && signals && (
        <Card title={`Latest signal per symbol · ${signals.strategy}`}>
          <DataTable
            columns={[
              {
                key: 'symbol',
                label: 'Symbol',
                sortable: true,
                render: (row) => (
                  <Link
                    to={`/symbols/${row.symbol}`}
                    className="font-medium text-nepse-600 hover:underline"
                  >
                    {row.symbol}
                  </Link>
                ),
              },
              { key: 'business_date', label: 'As of' },
              {
                key: 'action',
                label: 'Action',
                sortable: true,
                render: (row) => (
                  <Badge text={row.action} variant={ACTION_VARIANT[row.action] ?? 'default'} />
                ),
              },
              {
                key: 'strength',
                label: 'Strength',
                sortable: true,
                render: (row) => num(row.strength, 3),
              },
              { key: 'price', label: 'Price', render: (row) => num(row.price) },
              {
                key: 'reason',
                label: 'Because',
                className: 'text-text-secondary',
                render: (row) => row.reason || '—',
              },
            ]}
            data={rows}
          />
        </Card>
      )}

      {!loading && tab === 'stats' && stats && (
        <Card
          title={`Quantitative statistics · ${stats.symbols.length} symbols`}
          actions={
            stats.periods_per_year ? (
              <span className="text-xs text-text-tertiary">
                {stats.periods_per_year} periods/year
              </span>
            ) : undefined
          }
        >
          {stats.rows.length === 0 ? (
            <p className="py-8 text-center text-sm text-text-tertiary">
              No symbol had enough price history to compute statistics.
            </p>
          ) : (
            <DataTable
              columns={Object.keys(stats.rows[0]).map((key) => ({
                key,
                label: key.replace(/_/g, ' '),
                sortable: true,
                render: (row: Record<string, unknown>) =>
                  typeof row[key] === 'number' ? num(row[key], 3) : String(row[key] ?? '—'),
              }))}
              data={stats.rows}
            />
          )}
        </Card>
      )}

      {!loading && !error && !signals && !stats && (
        <Card>
          <div className="flex flex-col items-center gap-3 py-12 text-text-tertiary">
            <Radar className="h-10 w-10" />
            <p className="text-sm">
              Choose a strategy and press <strong>Read signals</strong>.
            </p>
          </div>
        </Card>
      )}
    </div>
  );
}
