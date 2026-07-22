import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { PortfolioSummary } from '../api/types';
import { Card } from '../components/ui/Card';
import { StatCard } from '../components/ui/StatCard';
import { DataTable } from '../components/ui/DataTable';
import { ErrorState } from '../components/ui/ErrorState';
import { LoadingSpinner } from '../components/ui/LoadingSpinner';
import { Wallet, TrendingUp, TrendingDown, DollarSign } from 'lucide-react';

export function PortfolioPage() {
  const [data, setData] = useState<PortfolioSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.portfolio()
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (error) return <ErrorState message={error} onRetry={() => window.location.reload()} />;
  if (loading) return <LoadingSpinner text="Loading portfolio..." />;
  if (!data) return null;

  const totalEquity = data.cash + data.positions.reduce(
    (sum, p) => sum + p.market_value,
    0
  );
  const totalReturn = totalEquity - data.initial_cash;
  const totalReturnPct = data.initial_cash > 0
    ? (totalReturn / data.initial_cash) * 100
    : 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Portfolio</h1>
        <p className="mt-1 text-sm text-text-secondary">
          Paper trading account summary
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard
          label="Total Equity"
          value={`NPR ${totalEquity.toLocaleString('en-US', { minimumFractionDigits: 2 })}`}
          icon={<Wallet className="h-4 w-4" />}
        />
        <StatCard
          label="Cash"
          value={`NPR ${data.cash.toLocaleString('en-US', { minimumFractionDigits: 2 })}`}
          icon={<DollarSign className="h-4 w-4" />}
        />
        <StatCard
          label="Total Return"
          value={`NPR ${totalReturn.toLocaleString('en-US', { minimumFractionDigits: 2 })}`}
          change={`${totalReturnPct >= 0 ? '+' : ''}${totalReturnPct.toFixed(2)}%`}
          changeType={totalReturn >= 0 ? 'positive' : 'negative'}
          icon={totalReturn >= 0 ? <TrendingUp className="h-4 w-4" /> : <TrendingDown className="h-4 w-4" />}
        />
        <StatCard
          label="Realized PnL"
          value={`NPR ${data.realized_pnl.toLocaleString('en-US', { minimumFractionDigits: 2 })}`}
          changeType={data.realized_pnl >= 0 ? 'positive' : 'negative'}
          icon={<TrendingUp className="h-4 w-4" />}
        />
      </div>

      {/* Holdings */}
      <Card title="Holdings">
        {data.positions.length === 0 ? (
          <p className="py-8 text-center text-sm text-text-tertiary">No open positions</p>
        ) : (
          <DataTable
            columns={[
              { key: 'symbol', label: 'Symbol', sortable: true },
              { key: 'quantity', label: 'Qty', sortable: true },
              {
                key: 'avg_cost',
                label: 'Avg Cost',
                sortable: true,
                render: (r) => `NPR ${Number(r.avg_cost).toFixed(2)}`,
              },
              {
                key: 'market_value',
                label: 'Market Value',
                sortable: true,
                render: (r) => `NPR ${Number(r.market_value).toLocaleString('en-US', { minimumFractionDigits: 2 })}`,
              },
              {
                key: 'unrealized_pnl',
                label: 'Unrealized P&L',
                sortable: true,
                render: (r) => {
                  const v = Number(r.unrealized_pnl);
                  return (
                    <span className={v >= 0 ? 'text-positive' : 'text-negative'}>
                      {v >= 0 ? '+' : ''}
                      {v.toFixed(2)}
                    </span>
                  );
                },
              },
            ]}
            data={data.positions}
          />
        )}
      </Card>

      {/* Trade history */}
      <Card title="Trade history">
        <p className="py-4 text-sm text-text-tertiary">
          {data.trades} trade{data.trades !== 1 ? 's' : ''} recorded.
          {data.trades > 0 && ' Use the CLI (nepse-trader paper status) for detailed trade history.'}
        </p>
      </Card>
    </div>
  );
}
