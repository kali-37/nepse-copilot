import { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { HoldingComparison, PaperTradeResult, PaperTradeRow, PortfolioSummary } from '../api/types';
import { Card } from '../components/ui/Card';
import { StatCard } from '../components/ui/StatCard';
import { DataTable } from '../components/ui/DataTable';
import { ErrorState } from '../components/ui/ErrorState';
import { LoadingSpinner } from '../components/ui/LoadingSpinner';
import { Wallet, TrendingUp, TrendingDown, DollarSign, ShoppingCart } from 'lucide-react';

/** A simulated fill. Every Nepal cost is applied by the backend, and the
 *  breakdown of the last one is shown so the fees are never invisible. */
function TradeForm({ onFilled }: { onFilled: (result: PaperTradeResult) => void }) {
  const [symbol, setSymbol] = useState('');
  const [side, setSide] = useState<'buy' | 'sell'>('buy');
  const [price, setPrice] = useState('');
  const [quantity, setQuantity] = useState('');
  const [businessDate, setBusinessDate] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onFilled(
        await api.recordPaperTrade({
          symbol: symbol.trim().toUpperCase(),
          side,
          price: Number(price),
          quantity: Number(quantity),
          business_date: businessDate || undefined,
        })
      );
      setSymbol('');
      setPrice('');
      setQuantity('');
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
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          className="h-10 w-32 rounded-lg border border-border bg-surface px-3 text-sm uppercase text-text-primary"
        />
      </label>
      <label className="block text-sm">
        <span className="mb-1 block text-xs font-medium text-text-secondary">Side</span>
        <select
          value={side}
          onChange={(e) => setSide(e.target.value as 'buy' | 'sell')}
          className="h-10 rounded-lg border border-border bg-surface px-3 text-sm text-text-primary"
        >
          <option value="buy">buy</option>
          <option value="sell">sell</option>
        </select>
      </label>
      <label className="block text-sm">
        <span className="mb-1 block text-xs font-medium text-text-secondary">Price</span>
        <input
          required
          type="number"
          step="0.01"
          min="0.01"
          value={price}
          onChange={(e) => setPrice(e.target.value)}
          className="h-10 w-28 rounded-lg border border-border bg-surface px-3 text-sm text-text-primary"
        />
      </label>
      <label className="block text-sm">
        <span className="mb-1 block text-xs font-medium text-text-secondary">Quantity</span>
        <input
          required
          type="number"
          min="1"
          value={quantity}
          onChange={(e) => setQuantity(e.target.value)}
          className="h-10 w-28 rounded-lg border border-border bg-surface px-3 text-sm text-text-primary"
        />
      </label>
      <label className="block text-sm">
        <span className="mb-1 block text-xs font-medium text-text-secondary">
          Date (blank = today)
        </span>
        <input
          type="date"
          value={businessDate}
          onChange={(e) => setBusinessDate(e.target.value)}
          className="h-10 rounded-lg border border-border bg-surface px-3 text-sm text-text-primary"
        />
      </label>
      <button
        disabled={busy}
        className="inline-flex h-10 items-center gap-2 rounded-lg bg-nepse-600 px-4 text-sm font-semibold text-white hover:bg-nepse-700 disabled:opacity-50"
      >
        <ShoppingCart className="h-4 w-4" />
        {busy ? 'Recording...' : `Record ${side}`}
      </button>
      {error && <p className="w-full text-sm text-negative">{error}</p>}
    </form>
  );
}

export function PortfolioPage() {
  const [data, setData] = useState<PortfolioSummary | null>(null);
  const [comparison, setComparison] = useState<HoldingComparison[]>([]);
  const [trades, setTrades] = useState<PaperTradeRow[]>([]);
  const [lastFill, setLastFill] = useState<PaperTradeResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.portfolio(),
      api.meroshareCompare().catch(() => ({ rows: [], summary: {} })),
      api.paperTrades().catch(() => []),
    ])
      .then(([portfolio, realVsPaper, paperTrades]) => {
        setData(portfolio);
        setComparison(realVsPaper.rows);
        setTrades(paperTrades);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (error) return <ErrorState message={error} onRetry={() => window.location.reload()} />;
  if (loading) return <LoadingSpinner text="Loading portfolio..." />;
  if (!data) return null;

  const totalEquity = data.cash + data.positions.reduce(
    (sum, p) => sum + (p.market_value ?? 0),
    0
  );
  const missingQuotes = data.positions.some((position) => position.market_value === null);
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
          value={missingQuotes ? 'Quote unavailable' : `NPR ${totalEquity.toLocaleString('en-US', { minimumFractionDigits: 2 })}`}
          icon={<Wallet className="h-4 w-4" />}
        />
        <StatCard
          label="Cash"
          value={`NPR ${data.cash.toLocaleString('en-US', { minimumFractionDigits: 2 })}`}
          icon={<DollarSign className="h-4 w-4" />}
        />
        <StatCard
          label="Total Return"
          value={missingQuotes ? 'Quote unavailable' : `NPR ${totalReturn.toLocaleString('en-US', { minimumFractionDigits: 2 })}`}
          change={missingQuotes ? undefined : `${totalReturnPct >= 0 ? '+' : ''}${totalReturnPct.toFixed(2)}%`}
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
            label="Holdings"
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
                render: (r) => r.market_value === null ? 'Quote unavailable' : `NPR ${Number(r.market_value).toLocaleString('en-US', { minimumFractionDigits: 2 })}`,
              },
              {
                key: 'unrealized_pnl',
                label: 'Unrealized P&L',
                sortable: true,
                render: (r) => {
                  if (r.unrealized_pnl === null) return 'Quote unavailable';
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

      <Card title="Real versus paper">
        {comparison.length === 0 ? (
          <p className="py-6 text-center text-sm text-text-tertiary">
            No MeroShare comparison data yet.
          </p>
        ) : (
          <div className="divide-y divide-border">
            {comparison.map((row) => (
              <div
                key={row.symbol}
                className="grid grid-cols-[1fr_auto_auto] items-center gap-3 py-3"
              >
                <div>
                  <div className="font-semibold text-text-primary">{row.symbol}</div>
                  <div className="text-xs text-text-secondary">
                    Real {row.real_quantity} · Paper {row.paper_quantity}
                  </div>
                </div>
                <div className="text-right text-xs text-text-secondary">
                  {row.quantity_delta === 0
                    ? 'Quantity aligned'
                    : `${row.quantity_delta > 0 ? '+' : ''}${row.quantity_delta} real`}
                </div>
                <span
                  className={row.agrees ? 'text-xs font-semibold text-positive' : 'text-xs font-semibold text-warning'}
                >
                  {row.agrees ? 'Match' : 'Review'}
                </span>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card title="Record a simulated trade">
        <p className="mb-4 text-sm text-text-secondary">
          Simulated fills only &mdash; there is no live order path in this system, by design. Broker
          commission, the SEBON fee, the DP charge and capital gains tax on a realized gain are all
          applied for you.
        </p>
        <TradeForm
          onFilled={(result) => {
            setLastFill(result);
            setData(result.portfolio);
            void api.paperTrades().then(setTrades).catch(() => undefined);
          }}
        />
        {lastFill && (
          <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-1.5 border-t border-border pt-4 text-sm sm:grid-cols-4">
            {[
              ['gross', lastFill.trade.gross_amount],
              ['commission', lastFill.trade.broker_commission],
              ['SEBON fee', lastFill.trade.sebon_fee],
              ['DP charge', lastFill.trade.dp_charge],
              ['capital gains tax', lastFill.trade.cgt],
              ['net', lastFill.trade.net_amount],
            ].map(([label, value]) => (
              <div key={String(label)} className="flex justify-between gap-2">
                <dt className="text-text-tertiary">{label}</dt>
                <dd className="font-medium text-text-primary">{Number(value).toFixed(2)}</dd>
              </div>
            ))}
          </dl>
        )}
      </Card>

      {/* Trade history */}
      <Card
        title="Trade history"
        // The replayed count and the listed rows are different facts: the list
        // is capped, so say how many exist as well as how many are shown.
        actions={
          <span className="text-xs text-text-tertiary">
            {data.trades} trade{data.trades === 1 ? '' : 's'} recorded
            {trades.length < data.trades && ` · showing the latest ${trades.length}`}
          </span>
        }
      >
        {trades.length === 0 ? (
          <p className="py-6 text-center text-sm text-text-tertiary">No trades recorded yet.</p>
        ) : (
          <DataTable
            label="Trade history"
            columns={[
              { key: 'business_date', label: 'Date', sortable: true },
              { key: 'symbol', label: 'Symbol', sortable: true },
              {
                key: 'side',
                // The API stores the side upper-cased, so compare case-insensitively.
                label: 'Side',
                render: (r) => (
                  <span
                    className={
                      String(r.side).toUpperCase() === 'BUY' ? 'text-positive' : 'text-negative'
                    }
                  >
                    {r.side}
                  </span>
                ),
              },
              { key: 'quantity', label: 'Qty', sortable: true },
              { key: 'price', label: 'Price', render: (r) => Number(r.price).toFixed(2) },
              {
                key: 'gross_amount',
                label: 'Gross',
                render: (r) => Number(r.gross_amount).toFixed(2),
              },
              {
                key: 'costs',
                label: 'Costs',
                render: (r) =>
                  (
                    Number(r.broker_commission) +
                    Number(r.sebon_fee) +
                    Number(r.dp_charge) +
                    Number(r.cgt)
                  ).toFixed(2),
              },
              { key: 'net_amount', label: 'Net', render: (r) => Number(r.net_amount).toFixed(2) },
            ]}
            data={trades}
          />
        )}
      </Card>
    </div>
  );
}
