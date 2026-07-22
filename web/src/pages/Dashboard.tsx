import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { DashboardStats, MarketBreadth, MoversResponse } from '../api/types';
import { Card } from '../components/ui/Card';
import { StatCard } from '../components/ui/StatCard';
import { ErrorState } from '../components/ui/ErrorState';
import { LoadingSpinner } from '../components/ui/LoadingSpinner';
import { Badge } from '../components/ui/Badge';
import {
  TrendingUp,
  TrendingDown,
  Database,
  Activity,
  BarChart3,
} from 'lucide-react';

export function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [breadth, setBreadth] = useState<MarketBreadth | null>(null);
  const [movers, setMovers] = useState<MoversResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    setError(null);
    Promise.all([
      api.dashboard(),
      api.marketBreadth(),
      api.movers(5),
    ])
      .then(([s, b, m]) => {
        setStats(s);
        setBreadth(b);
        setMovers(m);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    const interval = setInterval(load, 60_000);
    return () => clearInterval(interval);
  }, []);

  if (error) return <ErrorState message={error} onRetry={load} />;
  if (loading || !stats || !breadth || !movers) return <LoadingSpinner text="Loading dashboard..." />;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Dashboard</h1>
        <p className="mt-1 text-sm text-text-secondary">
          Market overview and database summary
          {stats.latest_reconciled_date && (
            <> &middot; Latest: <span className="font-medium">{stats.latest_reconciled_date}</span></>
          )}
        </p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-5">
        <StatCard
          label="Symbols"
          value={breadth.symbols}
          icon={<BarChart3 className="h-4 w-4" />}
        />
        <StatCard
          label="Advancers"
          value={breadth.advancers}
          change={`${breadth.symbols > 0 ? ((breadth.advancers / breadth.symbols) * 100).toFixed(1) : 0}%`}
          changeType="positive"
          icon={<TrendingUp className="h-4 w-4" />}
        />
        <StatCard
          label="Decliners"
          value={breadth.decliners}
          change={`${breadth.symbols > 0 ? ((breadth.decliners / breadth.symbols) * 100).toFixed(1) : 0}%`}
          changeType="negative"
          icon={<TrendingDown className="h-4 w-4" />}
        />
        <StatCard
          label="Turnover"
          value={`NPR ${(breadth.total_turnover / 1e7).toFixed(1)}Cr`}
          icon={<Activity className="h-4 w-4" />}
        />
        <StatCard
          label="DB Size"
          value={`${stats.symbols_with_data}`}
          change={`${stats.price_bar_rows.toLocaleString()} bars`}
          icon={<Database className="h-4 w-4" />}
        />
      </div>

      {/* Market breadth bar */}
      <Card title="Market breadth">
        <div className="flex h-8 overflow-hidden rounded-lg">
          {breadth.advancers > 0 && (
            <div
              className="flex items-center justify-center bg-positive text-xs font-semibold text-white transition-all"
              style={{ width: `${(breadth.advancers / Math.max(breadth.symbols, 1)) * 100}%` }}
            >
              {breadth.advancers}
            </div>
          )}
          {breadth.unchanged > 0 && (
            <div
              className="flex items-center justify-center bg-text-tertiary text-xs font-semibold text-white transition-all"
              style={{ width: `${(breadth.unchanged / Math.max(breadth.symbols, 1)) * 100}%` }}
            >
              {breadth.unchanged}
            </div>
          )}
          {breadth.decliners > 0 && (
            <div
              className="flex items-center justify-center bg-negative text-xs font-semibold text-white transition-all"
              style={{ width: `${(breadth.decliners / Math.max(breadth.symbols, 1)) * 100}%` }}
            >
              {breadth.decliners}
            </div>
          )}
        </div>
        <div className="mt-2 flex gap-4 text-xs text-text-secondary">
          <span className="flex items-center gap-1">
            <span className="h-2.5 w-2.5 rounded bg-positive" /> Advancers ({breadth.advancers})
          </span>
          <span className="flex items-center gap-1">
            <span className="h-2.5 w-2.5 rounded bg-text-tertiary" /> Unchanged ({breadth.unchanged})
          </span>
          <span className="flex items-center gap-1">
            <span className="h-2.5 w-2.5 rounded bg-negative" /> Decliners ({breadth.decliners})
          </span>
        </div>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Gainers */}
        <Card title="Top gainers">
          <div className="space-y-2">
            {movers.gainers.map((m) => (
              <div
                key={m.symbol}
                className="flex items-center justify-between rounded-lg bg-surface-secondary px-3 py-2"
              >
                <span className="font-medium text-text-primary">{m.symbol}</span>
                <span className="text-sm text-text-secondary">
                  NPR {m.close.toFixed(2)}
                </span>
                <Badge
                  text={`+${m.change_percent.toFixed(2)}%`}
                  variant="success"
                />
              </div>
            ))}
            {movers.gainers.length === 0 && (
              <p className="py-4 text-center text-sm text-text-tertiary">No gainers</p>
            )}
          </div>
        </Card>

        {/* Losers */}
        <Card title="Top losers">
          <div className="space-y-2">
            {movers.losers.map((m) => (
              <div
                key={m.symbol}
                className="flex items-center justify-between rounded-lg bg-surface-secondary px-3 py-2"
              >
                <span className="font-medium text-text-primary">{m.symbol}</span>
                <span className="text-sm text-text-secondary">
                  NPR {m.close.toFixed(2)}
                </span>
                <Badge
                  text={`${m.change_percent.toFixed(2)}%`}
                  variant="danger"
                />
              </div>
            ))}
            {movers.losers.length === 0 && (
              <p className="py-4 text-center text-sm text-text-tertiary">No losers</p>
            )}
          </div>
        </Card>
      </div>

      {/* DB stats */}
      <Card title="Database health">
        <div className="grid grid-cols-2 gap-4 text-sm md:grid-cols-4">
          <StatItem label="Symbols in DB" value={stats.symbols_with_data} />
          <StatItem label="Price bars" value={stats.price_bar_rows.toLocaleString()} />
          <StatItem label="Reconciled rows" value={stats.reconciled_rows.toLocaleString()} />
          <StatItem label="Sources" value={stats.sources_with_data} />
          <StatItem label="Signals" value={stats.signal_rows.toLocaleString()} />
          <StatItem label="Signal strategies" value={stats.signal_strategies} />
          <StatItem label="Ingest logs" value={stats.ingest_log_rows.toLocaleString()} />
          <StatItem label="Paper trades" value={stats.paper_trades} />
          {stats.latest_avg_confidence !== null && (
            <StatItem
              label="Avg confidence"
              value={`${(stats.latest_avg_confidence * 100).toFixed(1)}%`}
            />
          )}
        </div>
      </Card>
    </div>
  );
}

function StatItem({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg bg-surface-secondary p-3">
      <div className="text-xs text-text-tertiary">{label}</div>
      <div className="mt-0.5 text-base font-semibold text-text-primary">{value}</div>
    </div>
  );
}
