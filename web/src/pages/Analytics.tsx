import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { BacktestRun } from '../api/types';
import { researchApi, type MarketResearch, type WalkForwardResult } from '../api/research';
import { Card } from '../components/ui/Card';
import { DataTable } from '../components/ui/DataTable';
import { StatCard } from '../components/ui/StatCard';

const inputClass = 'mt-1 block w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text-primary focus:outline-2 focus:outline-nepse-500';
const buttonClass = 'min-h-11 rounded-lg bg-nepse-600 px-5 py-2 text-sm font-semibold text-white hover:bg-nepse-700 focus:outline-2 focus:outline-offset-2 focus:outline-nepse-500 disabled:opacity-50';
const strategies = ['sma_cross', 'rsi', 'macd', 'bollinger', 'supertrend', 'ichimoku', 'donchian', 'mean_reversion'];
const percent = (value: number | null) => value === null ? '—' : `${value.toFixed(2)}%`;

export function AnalyticsPage() {
  const [symbols, setSymbols] = useState('NABIL,EBL,NTC');
  const [strategy, setStrategy] = useState('sma_cross');
  const [cash, setCash] = useState(1000000);
  const [mode, setMode] = useState<'shared' | 'equal'>('shared');
  const [rebalance, setRebalance] = useState(0);
  const [rolling, setRolling] = useState(false);
  const [portfolio, setPortfolio] = useState<BacktestRun | null>(null);
  const [walkForward, setWalkForward] = useState<WalkForwardResult | null>(null);
  const [market, setMarket] = useState<MarketResearch | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [marketError, setMarketError] = useState('');

  useEffect(() => { researchApi.market().then(setMarket).catch((e: Error) => setMarketError(e.message)); }, []);

  const run = async (kind: 'portfolio' | 'walk-forward') => {
    setBusy(true);
    setError('');
    try {
      if (kind === 'portfolio') setPortfolio(await researchApi.portfolio(symbols, strategy, cash, mode, rebalance));
      else setWalkForward(await researchApi.walkForward(symbols.split(',')[0].trim(), strategy, rolling));
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Analytics</h1>
        <p className="mt-1 text-sm text-text-secondary">Portfolio research, validation folds, and sector and broker activity from stored data.</p>
      </div>
      <Card title="Portfolio research">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <label className="text-sm text-text-secondary">Symbols<input className={inputClass} value={symbols} onChange={(e) => setSymbols(e.target.value)} /></label>
          <label className="text-sm text-text-secondary">Strategy<select className={inputClass} value={strategy} onChange={(e) => setStrategy(e.target.value)}>{strategies.map((name) => <option key={name} value={name}>{name.replaceAll('_', ' ')}</option>)}</select></label>
          <label className="text-sm text-text-secondary">Starting cash (NPR)<input type="number" min="1" className={inputClass} value={cash} onChange={(e) => setCash(Number(e.target.value))} /></label>
          <label className="text-sm text-text-secondary">Capital allocation<select className={inputClass} value={mode} onChange={(e) => setMode(e.target.value as 'shared' | 'equal')}><option value="shared">One shared cash account</option><option value="equal">Separate equal allocations</option></select></label>
          {mode === 'shared' && <label className="text-sm text-text-secondary">Rebalance<select className={inputClass} value={rebalance} onChange={(e) => setRebalance(Number(e.target.value))}><option value={0}>On signals only</option><option value={20}>Every 20 sessions</option><option value={60}>Every 60 sessions</option></select></label>}
          <label className="flex items-center gap-2 text-sm text-text-secondary"><input type="checkbox" checked={rolling} onChange={(e) => setRolling(e.target.checked)} />Rolling training window</label>
        </div>
        <p className="mt-4 text-sm text-text-secondary">Nepal fees apply to simulated fills. Walk-forward trains on earlier prices and tests later prices for the first symbol above. <Link className="font-medium text-nepse-600 underline" to="/operations">Download history</Link> if a symbol has too few sessions.</p>
        <div className="mt-4 flex flex-wrap gap-3">
          <button className={buttonClass} disabled={busy} onClick={() => void run('portfolio')}>Run portfolio backtest</button>
          <button className={buttonClass} disabled={busy} onClick={() => void run('walk-forward')}>Run walk-forward</button>
        </div>
        {busy && <p role="status" className="mt-3 text-sm text-text-secondary">Running research…</p>}
        {error && <p role="alert" className="mt-3 text-sm text-negative">{error}</p>}
      </Card>
      {portfolio && <>
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <StatCard label="Final equity" value={`NPR ${portfolio.summary.final_equity.toLocaleString()}`} />
          <StatCard label="Net return" value={percent(portfolio.summary.total_return_pct)} />
          <StatCard label="Sharpe" value={portfolio.summary.sharpe.toFixed(2)} />
          <StatCard label="Max drawdown" value={percent(portfolio.summary.max_drawdown_pct)} />
        </div>
        <Card title="Portfolio equity">
          <div className="h-72 min-w-0" role="img" aria-label="Portfolio equity over the backtest period">
            <ResponsiveContainer width="100%" height="100%"><LineChart data={portfolio.equity_curve.map(([day, equity]) => ({ day, equity }))}>
              <CartesianGrid strokeDasharray="3 3" /><XAxis dataKey="day" minTickGap={50} /><YAxis width={80} tickFormatter={(value: number) => `${(value / 1000).toFixed(0)}k`} /><Tooltip formatter={(value) => [`NPR ${Number(value).toLocaleString()}`, 'Equity']} /><Line dataKey="equity" name="Equity" stroke="var(--color-nepse-600)" strokeWidth={2} dot={false} isAnimationActive={false} />
            </LineChart></ResponsiveContainer>
          </div>
        </Card>
      </>}
      {walkForward && <Card title={`Walk-forward: ${walkForward.symbol}`}>
        <p className="mb-4 text-sm text-text-secondary">Mean training return: {percent(walkForward.avg_is_return_pct)} · Mean validation return: {percent(walkForward.avg_oos_return_pct)}</p>
        <DataTable label="Validation folds" data={walkForward.folds} columns={[
          { key: 'train_start', label: 'Train from' }, { key: 'train_end', label: 'Train through' },
          { key: 'val_start', label: 'Validate from' }, { key: 'val_end', label: 'Validate through' },
          { key: 'best_params', label: 'Selected settings', render: (row) => JSON.stringify(row.best_params) },
          { key: 'in_sample_return_pct', label: 'Training return', render: (row) => percent(row.in_sample_return_pct) },
          { key: 'out_of_sample_return_pct', label: 'Validation return', render: (row) => percent(row.out_of_sample_return_pct) },
        ]} />
      </Card>}
      {marketError && <p role="alert" className="text-negative">{marketError}</p>}
      {market && <>
        <Card title={`Sector breadth · ${market.business_date}`}>
          <p className="mb-3 text-sm text-text-secondary">Sector labels come from dated fundamentals. Missing classifications appear as Unclassified.</p>
          <DataTable label="Sector breadth" data={market.sectors} columns={[
            { key: 'sector', label: 'Sector' }, { key: 'symbols', label: 'Symbols' }, { key: 'advancers', label: 'Up' },
            { key: 'decliners', label: 'Down' }, { key: 'mean_change_pct', label: 'Mean change', render: (row) => percent(row.mean_change_pct) },
            { key: 'turnover', label: 'Turnover (NPR)', render: (row) => row.turnover.toLocaleString() },
          ]} />
        </Card>
        <Card title={`Broker flow · ${market.business_date}`}>
          {market.broker_rows > market.broker_flows.length && <p className="mb-3 text-sm text-text-secondary">Showing the strongest net buying and selling flows: {market.broker_flows.length} of {market.broker_rows} symbol/broker pairs.</p>}
          {!market.broker_flows.length && <p className="mb-3 text-sm text-text-secondary">Download broker trades in Operations to see matched-contract buy and sell pressure.</p>}
          <DataTable label="Broker flow" data={market.broker_flows} columns={[
            { key: 'symbol', label: 'Symbol' }, { key: 'broker', label: 'Broker' }, { key: 'buy_quantity', label: 'Bought shares' },
            { key: 'sell_quantity', label: 'Sold shares' }, { key: 'net_quantity', label: 'Net shares' },
            { key: 'net_amount', label: 'Net amount (NPR)', render: (row) => row.net_amount.toLocaleString() },
          ]} />
        </Card>
      </>}
    </div>
  );
}
