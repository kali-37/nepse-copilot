import { useCallback, useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Area,
  AreaChart,
} from 'recharts';
import { ArrowLeft } from 'lucide-react';
import { decisionApi, type FundamentalReport, type StockHistory } from '../api/decisions';
import { FundamentalsPanel } from '../components/decisions/FundamentalsPanel';
import { api } from '../api/client';
import type { Fundamentals, QuantStats, ReconciledPrice, Signal } from '../api/types';
import { Card } from '../components/ui/Card';
import { Badge } from '../components/ui/Badge';
import { LoadingSpinner } from '../components/ui/LoadingSpinner';
import { ErrorState } from '../components/ui/ErrorState';

type Range = '1M' | '3M' | '6M' | '1Y' | 'ALL';

function dateLimit(range: Range): Date | null {
  const now = new Date();
  switch (range) {
    case '1M':
      return new Date(now.getFullYear(), now.getMonth() - 1, now.getDate());
    case '3M':
      return new Date(now.getFullYear(), now.getMonth() - 3, now.getDate());
    case '6M':
      return new Date(now.getFullYear(), now.getMonth() - 6, now.getDate());
    case '1Y':
      return new Date(now.getFullYear() - 1, now.getMonth(), now.getDate());
    default:
      return null;
  }
}

export function SymbolDetailPage() {
  const { symbol } = useParams<{ symbol: string }>();
  const navigate = useNavigate();
  const sym = (symbol || '').toUpperCase();

  const [prices, setPrices] = useState<ReconciledPrice[]>([]);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [quant, setQuant] = useState<QuantStats | null>(null);
  const [history, setHistory] = useState<StockHistory | null>(null);
  const [assessment, setAssessment] = useState<FundamentalReport | null>(null);
  const [fundamentals, setFundamentals] = useState<Fundamentals | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [range, setRange] = useState<Range>('3M');

  const load = useCallback(() => {
    if (!sym) return;
    setLoading(true);
    setError(null);

    const limit = range === 'ALL' ? 2000 : 500;
    const start = dateLimit(range);

    Promise.allSettled([
      api.symbolPrices(sym, { start: start?.toISOString().slice(0, 10), limit }),
      api.symbolSignals(sym),
      api.symbolQuant(sym),
      api.symbolFundamentals(sym),
      decisionApi.fundamentals(sym),
      decisionApi.history(sym),
    ]).then(([p, s, q, f, a, h]) => {
      if (p.status === 'fulfilled') setPrices(p.value);
      else setError(p.reason?.message || 'Failed to load prices');
      if (s.status === 'fulfilled') setSignals(s.value);
      if (q.status === 'fulfilled') setQuant(q.value);
      if (f.status === 'fulfilled') setFundamentals(f.value);
      setAssessment(a.status === 'fulfilled' ? a.value : null);
      setHistory(h.status === 'fulfilled' ? h.value : null);
    }).finally(() => setLoading(false));
  }, [sym, range]);

  useEffect(() => { load(); }, [load]);

  if (error) return <ErrorState message={error} onRetry={load} />;

  const latestClose = prices.length > 0 ? prices[prices.length - 1].close : null;
  const prevClose = prices.length > 1 ? prices[prices.length - 2].close : null;
  const change = latestClose !== null && prevClose !== null
    ? ((latestClose - prevClose) / prevClose) * 100
    : null;

  const chartData = prices.map((p) => ({
    date: p.business_date.slice(5),
    close: p.close,
    volume: p.volume,
  }));
  const fund = assessment?.asset_kind === 'mutual_fund' ||
    /mutual fund/i.test(`${fundamentals?.sector ?? ''} ${fundamentals?.company_name ?? ''}`);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <button
          onClick={() => navigate('/symbols')}
          className="rounded-lg p-2 text-text-secondary hover:bg-surface-tertiary hover:text-text-primary"
        >
          <ArrowLeft className="h-5 w-5" />
        </button>
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-text-primary">{sym}</h1>
            {fundamentals?.company_name && (
              <span className="text-sm text-text-secondary">
                {fundamentals.company_name}
              </span>
            )}
          </div>
          {latestClose !== null && (
            <div className="mt-1 flex items-center gap-2">
              <span className="text-lg font-semibold text-text-primary">
                NPR {latestClose.toFixed(2)}
              </span>
              {change !== null && (
                <Badge
                  text={`${change >= 0 ? '+' : ''}${change.toFixed(2)}%`}
                  variant={change > 0 ? 'success' : change < 0 ? 'danger' : 'default'}
                />
              )}
            </div>
          )}
        </div>
      </div>

      {loading && <LoadingSpinner text={`Loading ${sym} data...`} />}

      {!loading && (
        <>
          {/* Price chart */}
          <Card
            title="Price history"
            actions={
              <div className="flex gap-1">
                {(['1M', '3M', '6M', '1Y', 'ALL'] as const).map((r) => (
                  <button
                    key={r}
                    onClick={() => setRange(r)}
                    className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                      range === r
                        ? 'bg-nepse-600 text-white'
                        : 'text-text-secondary hover:bg-surface-tertiary'
                    }`}
                  >
                    {r}
                  </button>
                ))}
              </div>
            }
          >
            {chartData.length === 0 ? (
              <p className="py-12 text-center text-sm text-text-tertiary">No price data</p>
            ) : (
              <div className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={chartData}>
                    <defs>
                      <linearGradient id="closeGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="var(--color-chart-line)" stopOpacity={0.2} />
                        <stop offset="100%" stopColor="var(--color-chart-line)" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                    <XAxis
                      dataKey="date"
                      tick={{ fontSize: 11, fill: 'var(--color-text-tertiary)' }}
                      tickLine={false}
                      axisLine={false}
                      interval="preserveStartEnd"
                    />
                    <YAxis
                      domain={['auto', 'auto']}
                      tick={{ fontSize: 11, fill: 'var(--color-text-tertiary)' }}
                      tickLine={false}
                      axisLine={false}
                      tickFormatter={(v: number) => `${v.toFixed(0)}`}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: 'var(--color-surface)',
                        border: '1px solid var(--color-border)',
                        borderRadius: '8px',
                        fontSize: '12px',
                      }}
                      labelFormatter={(d) => `Date: ${d}`}
                    />
                    <Area
                      type="monotone"
                      dataKey="close"
                      stroke="var(--color-chart-line)"
                      strokeWidth={2}
                      fill="url(#closeGrad)"
                      dot={false}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            )}
          </Card>

          <div className="grid gap-6 lg:grid-cols-2">
            {/* Signals */}
            <Card title="Signals">
              {signals.length === 0 ? (
                <p className="py-8 text-center text-sm text-text-tertiary">No signals</p>
              ) : (
                <div className="space-y-2">
                  {signals.slice(-10).reverse().map((s, i) => (
                    <div
                      key={i}
                      className="flex items-center justify-between rounded-lg bg-surface-secondary px-3 py-2 text-sm"
                    >
                      <span className="text-text-tertiary">{s.business_date}</span>
                      <Badge
                        text={s.action}
                        variant={s.action === 'BUY' ? 'success' : s.action === 'SELL' ? 'danger' : 'default'}
                      />
                      <span className="text-text-secondary">{s.strategy}</span>
                      <span className="text-text-primary font-medium">
                        {s.price ? `NPR ${s.price.toFixed(2)}` : '—'}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </Card>

            {/* Quant stats */}
            <Card title="Quantitative stats">
              {quant && <p className="mb-3 text-sm text-text-tertiary">Based on {quant.n} price observations. Annualized historical figures are not forecasts.</p>}
              {!quant ? (
                <p className="py-8 text-center text-sm text-text-tertiary">Not enough data</p>
              ) : (
                <div className="grid grid-cols-2 gap-3 text-sm">
                  <QItem label="Total Return" value={formatStat(quant.total_return_pct, 2, '%')} />
                  <QItem label="Ann. Return" value={formatStat(quant.annualized_return_pct, 2, '%')} />
                  <QItem label="Ann. Volatility" value={formatStat(quant.annualized_vol_pct, 2, '%')} />
                  <QItem label="Sharpe" value={formatStat(quant.sharpe, 3)} />
                  <QItem label="Sortino" value={formatStat(quant.sortino, 3)} />
                  <QItem label="Max Drawdown" value={formatStat(quant.max_drawdown_pct, 2, '%')} highlight={quant.max_drawdown_pct !== null && Number.isFinite(quant.max_drawdown_pct) && Math.abs(quant.max_drawdown_pct) > 20} />
                  <QItem label="VaR (95%)" value={formatStat(quant.var_95_pct, 2, '%')} />
                  <QItem label="Skewness" value={formatStat(quant.skewness, 3)} />
                </div>
              )}
            </Card>
          </div>

          {/* Fundamentals */}
          {history && (history.trades.length > 0 || history.events.length > 0) && <Card title="Your past trades & advice"><div className="text-sm space-y-3">{history.trades.map((trade,i) => <details key={`${trade.business_date}-${i}`}><summary className="cursor-pointer">{trade.business_date} · {trade.side.toUpperCase()} {trade.quantity} shares at NPR {Number(trade.price).toFixed(2)}</summary>{trade.entry_plan?.rationale.map(reason => <p key={reason} className="mt-2 text-text-secondary">{reason}</p>)}</details>)}{history.events.map((event,i) => <p key={`${event.evaluated_at}-${i}`} className="text-text-secondary">{event.market_date ?? 'No quote'} · {event.previous_action ? `${event.previous_action.toUpperCase()} → ` : ''}{event.action.toUpperCase()}: {event.reason}</p>)}</div></Card>}
          {assessment && <Card title="Fundamental assessment"><FundamentalsPanel report={assessment} /></Card>}
          {fundamentals && (
            <Card title="Provider fundamentals">
              <p className="mb-4 text-sm text-text-secondary">
                {fundamentals.source_name || 'Public provider snapshot'}
                {fundamentals.fetched_at && ` · Fetched ${fundamentals.fetched_at.slice(0, 10)}`}
                {fundamentals.reporting_period_end
                  ? ` · Period ends ${fundamentals.reporting_period_end}`
                  : fundamentals.reporting_period && ` · ${fundamentals.reporting_period}`}
              </p>
              <div className="grid grid-cols-2 gap-4 text-sm md:grid-cols-4">
                <FItem label="Sector" value={fundamentals.sector || '—'} />
                <FItem label="Market Price" value={fundamentals.market_price !== null ? `NPR ${fundamentals.market_price.toFixed(2)}` : '—'} />
                {fund ? (
                  <>
                    <FItem label="Reported NAV per unit" value={formatStat(fundamentals.nav_per_unit, 2)} />
                    <FItem label="Provider NAV date" value={fundamentals.nav_date ?? '—'} />
                  </>
                ) : (
                  <>
                    <FItem label="EPS" value={formatStat(fundamentals.eps, 2)} />
                    <FItem label="P/E" value={formatStat(fundamentals.pe_ratio, 2)} />
                    <FItem label="Book Value" value={formatStat(fundamentals.book_value, 2)} />
                    <FItem label="PBV" value={formatStat(fundamentals.pbv, 2)} />
                    {fundamentals.roe_pct != null && <FItem label="Reported ROE" value={formatStat(fundamentals.roe_pct, 2, '%')} />}
                    {fundamentals.npl_pct != null && <FItem label="Reported NPL" value={formatStat(fundamentals.npl_pct, 2, '%')} />}
                    {fundamentals.capital_adequacy_pct != null && <FItem label="Reported capital adequacy" value={formatStat(fundamentals.capital_adequacy_pct, 2, '%')} />}
                  </>
                )}
                <FItem label="Dividend" value={fundamentals.dividend_pct !== null ? `${fundamentals.dividend_pct.toFixed(2)}%` : '—'} />
                <FItem label="Market Cap" value={fundamentals.market_cap !== null ? `NPR ${(fundamentals.market_cap / 1e7).toFixed(1)}Cr` : '—'} />
                <FItem label="52W High" value={fundamentals.high_52w !== null ? `NPR ${fundamentals.high_52w.toFixed(2)}` : '—'} />
                <FItem label="52W Low" value={fundamentals.low_52w !== null ? `NPR ${fundamentals.low_52w.toFixed(2)}` : '—'} />
                <FItem label="Shares Outstanding" value={fundamentals.shares_outstanding !== null ? fundamentals.shares_outstanding.toLocaleString() : '—'} />
                <FItem label="30D Avg Volume" value={fundamentals.avg_volume_30d !== null ? fundamentals.avg_volume_30d.toLocaleString() : '—'} />
              </div>
            </Card>
          )}
        </>
      )}
    </div>
  );
}

function formatStat(value: number | null | undefined, digits: number, suffix = ''): string {
  return typeof value === 'number' && Number.isFinite(value)
    ? `${value.toFixed(digits)}${suffix}`
    : '—';
}

function QItem({
  label,
  value,
  highlight,
}: {
  label: string;
  value: string;
  highlight?: boolean;
}) {
  return (
    <div className="rounded-lg bg-surface-secondary p-3">
      <div className="text-xs text-text-tertiary">{label}</div>
      <div className={`mt-0.5 text-base font-semibold ${highlight ? 'text-negative' : 'text-text-primary'}`}>
        {value}
      </div>
    </div>
  );
}

function FItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-surface-secondary p-3">
      <div className="text-xs text-text-tertiary">{label}</div>
      <div className="mt-0.5 text-sm font-medium text-text-primary">{value}</div>
    </div>
  );
}
