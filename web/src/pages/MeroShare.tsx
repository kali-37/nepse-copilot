import { useEffect, useState } from 'react';
import { FileUp, Link2, LockKeyhole, RefreshCw, ShieldCheck } from 'lucide-react';
import { api } from '../api/client';
import type { HoldingComparison, MeroShareHolding, MeroShareStatus } from '../api/types';
import { Badge } from '../components/ui/Badge';
import { Card } from '../components/ui/Card';
import { DataTable } from '../components/ui/DataTable';
import { ErrorState } from '../components/ui/ErrorState';
import { LoadingSpinner } from '../components/ui/LoadingSpinner';
import { StatCard } from '../components/ui/StatCard';

function money(value: number | null | undefined) {
  return value == null ? '—' : `NPR ${value.toLocaleString('en-US', { minimumFractionDigits: 2 })}`;
}

export function MeroSharePage() {
  const [status, setStatus] = useState<MeroShareStatus | null>(null);
  const [holdings, setHoldings] = useState<MeroShareHolding[]>([]);
  const [comparison, setComparison] = useState<HoldingComparison[]>([]);
  const [csvText, setCsvText] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    Promise.all([
      api.meroshareStatus(),
      api.meroshareHoldings(),
      api.meroshareCompare().catch(() => ({ rows: [], summary: {} })),
    ])
      .then(([nextStatus, nextHoldings, nextComparison]) => {
        setStatus(nextStatus);
        setHoldings(nextHoldings);
        setComparison(nextComparison.rows);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const sync = async () => {
    setBusy(true);
    setMessage(null);
    setError(null);
    try {
      const result = await api.meroshareSync(true);
      setMessage(result.ok ? `Synced ${result.holdings} holdings and ${result.transactions} transactions.` : result.error);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const importCsv = async () => {
    if (!csvText.trim()) return;
    setBusy(true);
    setMessage(null);
    setError(null);
    try {
      const result = await api.meroshareImport(csvText);
      setMessage(result.ok ? `Imported ${result.holdings} holdings.` : result.error);
      if (result.ok) setCsvText('');
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <LoadingSpinner text="Loading MeroShare mirror..." />;
  if (error && !status) return <ErrorState message={error} onRetry={load} />;
  if (!status) return null;

  const totalMarket = holdings.reduce((sum, item) => sum + (item.market_value ?? 0), 0);
  const totalCost = holdings.reduce((sum, item) => sum + (item.cost_basis ?? 0), 0);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">MeroShare</h1>
          <p className="mt-1 text-sm text-text-secondary">Read-only mirror of your demat holdings</p>
        </div>
        <button
          onClick={sync}
          disabled={!status.enabled || busy}
          className="inline-flex h-10 items-center gap-2 self-start rounded bg-nepse-600 px-4 text-sm font-semibold text-white hover:bg-nepse-700 disabled:cursor-not-allowed disabled:opacity-50 md:self-auto"
        >
          <RefreshCw className={`h-4 w-4 ${busy ? 'animate-spin' : ''}`} /> Sync read-only
        </button>
      </div>

      <div className="border-l-4 border-positive bg-green-50 p-4 dark:bg-green-900/20">
        <div className="flex items-center gap-2 font-semibold text-positive"><ShieldCheck className="h-4 w-4" /> Read-only boundary</div>
        <p className="mt-1 text-sm text-text-secondary">This connection reads portfolio data. It cannot apply for IPOs, place orders or submit auction bids.</p>
      </div>

      {message && <div className="border-l-4 border-nepse-500 bg-nepse-50 p-3 text-sm text-nepse-700 dark:bg-nepse-900/20 dark:text-nepse-300">{message}</div>}
      {error && <div className="border-l-4 border-negative bg-red-50 p-3 text-sm text-negative dark:bg-red-900/20">{error}</div>}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Connection" value={status.enabled ? 'Enabled' : 'Disabled'} icon={<Link2 className="h-4 w-4" />} />
        <StatCard label="Credentials" value={status.credentials_configured ? 'Ready' : 'Missing'} icon={<LockKeyhole className="h-4 w-4" />} />
        <StatCard label="Cost basis" value={money(totalCost)} />
        <StatCard label="Previous-close value" value={money(totalMarket)} change={totalMarket && totalCost ? `${(((totalMarket - totalCost) / totalCost) * 100).toFixed(2)}%` : null} changeType={totalMarket >= totalCost ? 'positive' : 'negative'} />
      </div>

      <Card title="Connection status">
        <div className="grid gap-4 text-sm sm:grid-cols-2 lg:grid-cols-4">
          <StatusItem label="Last status" value={status.last_status ?? 'Never synced'} />
          <StatusItem label="Last success" value={status.last_success_at ? new Date(status.last_success_at).toLocaleString() : '—'} />
          <StatusItem label="Credential source" value={status.credential_source || 'none'} />
          <StatusItem label="Stored holdings" value={String(status.holdings)} />
        </div>
        {!status.enabled && <p className="mt-4 text-sm text-warning">Enable MeroShare in settings or use the CSV import below.</p>}
        {status.last_error && <p className="mt-4 text-sm text-negative">Last sync: {status.last_error}</p>}
      </Card>

      <Card title="Holdings">
        <DataTable
          columns={[
            { key: 'symbol', label: 'Symbol' },
            { key: 'current_balance', label: 'Qty' },
            { key: 'pledged_balance', label: 'Pledged' },
            { key: 'wacc', label: 'WACC', render: (row) => money(row.wacc) },
            { key: 'previous_closing_price', label: 'Previous close', render: (row) => money(row.previous_closing_price) },
            { key: 'market_value', label: 'Market value', render: (row) => money(row.market_value) },
          ]}
          data={holdings}
        />
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Import portfolio CSV">
          <textarea
            aria-label="Portfolio CSV"
            value={csvText}
            onChange={(e) => setCsvText(e.target.value)}
            placeholder="Paste the exported CSV here"
            className="h-44 w-full resize-y rounded border border-border bg-surface-secondary p-3 font-mono text-xs text-text-primary"
          />
          <button
            onClick={importCsv}
            disabled={busy || !csvText.trim()}
            className="mt-3 inline-flex h-9 items-center gap-2 rounded border border-nepse-600 px-3 text-sm font-semibold text-nepse-600 hover:bg-nepse-50 disabled:opacity-50 dark:hover:bg-nepse-900/20"
          >
            <FileUp className="h-4 w-4" /> Import CSV
          </button>
        </Card>

        <Card title="Real versus paper">
          <div className="space-y-2">
            {comparison.map((row) => (
              <div key={row.symbol} className="grid grid-cols-[1fr_auto_auto] items-center gap-3 border-b border-border py-2 last:border-0">
                <div className="font-semibold text-text-primary">{row.symbol}</div>
                <div className="text-right text-xs text-text-secondary">Real {row.real_quantity}<br />Paper {row.paper_quantity}</div>
                <Badge text={row.agrees ? 'Match' : `${row.quantity_delta > 0 ? '+' : ''}${row.quantity_delta}`} variant={row.agrees ? 'success' : 'warning'} />
              </div>
            ))}
            {!comparison.length && <p className="py-6 text-center text-sm text-text-tertiary">No comparison data yet.</p>}
          </div>
        </Card>
      </div>
    </div>
  );
}

function StatusItem({ label, value }: { label: string; value: string }) {
  return <div><div className="text-xs text-text-tertiary">{label}</div><div className="mt-1 font-medium text-text-primary">{value}</div></div>;
}
