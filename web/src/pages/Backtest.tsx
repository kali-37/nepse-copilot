import { useState } from 'react';
import { api } from '../api/client';
import type { ScreenRow } from '../api/types';
import { Card } from '../components/ui/Card';
import { DataTable } from '../components/ui/DataTable';
import { ErrorState } from '../components/ui/ErrorState';
import { LoadingSpinner } from '../components/ui/LoadingSpinner';
import { Play, FlaskConical } from 'lucide-react';

const RANK_OPTIONS = [
  { value: 'sharpe', label: 'Sharpe' },
  { value: 'total_return_pct', label: 'Total Return' },
  { value: 'cagr_pct', label: 'CAGR' },
  { value: 'max_drawdown_pct', label: 'Max Drawdown' },
  { value: 'win_rate_pct', label: 'Win Rate' },
];

export function BacktestPage() {
  const [results, setResults] = useState<ScreenRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [rankBy, setRankBy] = useState('sharpe');
  const [minBars, setMinBars] = useState(60);
  const [strategies, setStrategies] = useState('all');
  const [maxPe, setMaxPe] = useState('');
  const [maxPbv, setMaxPbv] = useState('');

  const run = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.backtestScreen({
        strategies,
        cash: 100_000,
        min_bars: minBars,
        rank_by: rankBy,
        top: 50,
        max_pe: maxPe ? Number(maxPe) : undefined,
        max_pbv: maxPbv ? Number(maxPbv) : undefined,
      });
      setResults(data);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Backtest</h1>
        <p className="mt-1 text-sm text-text-secondary">
          Multi-symbol, multi-strategy backtest leaderboard
        </p>
      </div>

      <Card>
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-text-secondary">
              Rank by
            </label>
            <select
              value={rankBy}
              onChange={(e) => setRankBy(e.target.value)}
              className="rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text-primary focus:border-nepse-500 focus:outline-none"
            >
              {RANK_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-text-secondary">
              Min bars
            </label>
            <input
              type="number"
              aria-label="Min bars"
              value={minBars}
              onChange={(e) => setMinBars(Number(e.target.value))}
              className="w-20 rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text-primary focus:border-nepse-500 focus:outline-none"
            />
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-text-secondary">
              Strategies
            </label>
            <input
              type="text"
              value={strategies}
              onChange={(e) => setStrategies(e.target.value)}
              placeholder="all or comma list"
              className="w-40 rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text-primary focus:border-nepse-500 focus:outline-none"
            />
          </div>

          <label className="block text-xs text-text-secondary">
            Maximum P/E
            <input aria-label="Maximum P/E" type="number" min="0.01" step="0.1" value={maxPe} onChange={(event) => setMaxPe(event.target.value)}
              className="mt-1 block w-24 rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text-primary" />
          </label>
          <label className="block text-xs text-text-secondary">
            Maximum P/B
            <input aria-label="Maximum P/B" type="number" min="0.01" step="0.1" value={maxPbv} onChange={(event) => setMaxPbv(event.target.value)}
              className="mt-1 block w-24 rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text-primary" />
          </label>
          <button
            onClick={run}
            disabled={loading}
            className="flex items-center gap-2 rounded-lg bg-nepse-600 px-5 py-2 text-sm font-medium text-white transition-colors hover:bg-nepse-700 disabled:opacity-50"
          >
            <Play className="h-4 w-4" />
            {loading ? 'Running...' : 'Run'}
          </button>
        </div>
      </Card>
      {(maxPe || maxPbv) && <p className="text-xs text-text-secondary">Valuation filters use dated, stored fundamentals. Download them in Operations; symbols with missing valuations are excluded.</p>}

      {error && <ErrorState message={error} onRetry={run} />}

      {loading && <LoadingSpinner text="Running backtests..." />}

      {!loading && results.length > 0 && (
        <Card>
          <DataTable
            columns={[
              { key: 'symbol', label: 'Symbol', sortable: true },
              { key: 'strategy', label: 'Strategy', sortable: true },
              {
                key: 'total_return_pct',
                label: 'Return %',
                sortable: true,
                render: (r) => {
                  const v = Number(r.total_return_pct);
                  return (
                    <span className={v >= 0 ? 'text-positive' : 'text-negative'}>
                      {v >= 0 ? '+' : ''}{v.toFixed(2)}%
                    </span>
                  );
                },
              },
              {
                key: 'cagr_pct',
                label: 'CAGR %',
                sortable: true,
                render: (r) => {
                  const v = Number(r.cagr_pct);
                  return (
                    <span className={v >= 0 ? 'text-positive' : 'text-negative'}>
                      {v.toFixed(2)}%
                    </span>
                  );
                },
              },
              {
                key: 'sharpe',
                label: 'Sharpe',
                sortable: true,
                render: (r) => Number(r.sharpe).toFixed(3),
              },
              {
                key: 'max_drawdown_pct',
                label: 'Max DD %',
                sortable: true,
                render: (r) => {
                  const v = Number(r.max_drawdown_pct);
                  return <span className="text-negative">{v.toFixed(2)}%</span>;
                },
              },
              {
                key: 'win_rate_pct',
                label: 'Win Rate %',
                sortable: true,
                render: (r) => `${Number(r.win_rate_pct).toFixed(1)}%`,
              },
              { key: 'num_trades', label: 'Trades', sortable: true },
              { key: 'exposure_pct', label: 'Exp %', render: (r) => `${Number(r.exposure_pct).toFixed(0)}%` },
            ]}
            data={results}
          />
        </Card>
      )}

      {!loading && results.length === 0 && !error && (
        <Card>
          <div className="flex flex-col items-center gap-3 py-12 text-text-tertiary">
            <FlaskConical className="h-10 w-10" />
            <p className="text-sm">Click <strong>Run</strong> to start the backtest</p>
          </div>
        </Card>
      )}
    </div>
  );
}
