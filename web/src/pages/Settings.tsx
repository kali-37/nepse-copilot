import { useEffect, useState } from 'react';
import { BrainCircuit, Database, Save, ShieldCheck, ToggleRight } from 'lucide-react';
import { api } from '../api/client';
import type { AiBudget, MeroShareSetting, MeroShareStatus, RagStats, WatchlistSettings } from '../api/types';
import { Badge } from '../components/ui/Badge';
import { Card } from '../components/ui/Card';
import { ErrorState } from '../components/ui/ErrorState';
import { LoadingSpinner } from '../components/ui/LoadingSpinner';
import { StatCard } from '../components/ui/StatCard';

export function SettingsPage() {
  const [watchlist, setWatchlist] = useState<WatchlistSettings | null>(null);
  const [budget, setBudget] = useState<AiBudget | null>(null);
  const [meroshare, setMeroshare] = useState<MeroShareStatus | null>(null);
  const [meroshareSetting, setMeroshareSetting] = useState<MeroShareSetting | null>(null);
  const [rag, setRag] = useState<RagStats | null>(null);
  const [symbols, setSymbols] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [toggleSaving, setToggleSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    Promise.all([api.watchlist(), api.aiBudget(), api.meroshareStatus(), api.meroshareSetting(), api.ragStats()])
      .then(([nextWatchlist, nextBudget, nextMeroShare, nextMeroShareSetting, nextRag]) => {
        setWatchlist(nextWatchlist);
        setBudget(nextBudget);
        setMeroshare(nextMeroShare);
        setMeroshareSetting(nextMeroShareSetting);
        setRag(nextRag);
        setSymbols(nextWatchlist.symbols.join(', '));
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  const toggleMeroshare = async (enabled: boolean) => {
    setToggleSaving(true);
    setError(null);
    setMessage(null);
    try {
      const nextSetting = await api.updateMeroShareSetting(enabled);
      setMeroshareSetting(nextSetting);
      const nextStatus = await api.meroshareStatus();
      setMeroshare(nextStatus);
      setMessage(`MeroShare integration ${nextSetting.enabled ? 'enabled' : 'disabled'}.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setToggleSaving(false);
    }
  };

  useEffect(load, []);

  const save = async () => {
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const normalized = symbols.split(',').map((item) => item.trim().toUpperCase()).filter(Boolean);
      const next = await api.updateWatchlist(normalized);
      setWatchlist(next);
      setSymbols(next.symbols.join(', '));
      setMessage(`Saved ${next.symbols.length} watchlist symbols.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <LoadingSpinner text="Loading settings..." />;
  if (error && !watchlist) return <ErrorState message={error} onRetry={load} />;

  const callPct = budget?.max_calls ? (budget.calls / budget.max_calls) * 100 : 0;
  const tokenPct = budget?.max_tokens ? (budget.tokens / budget.max_tokens) * 100 : 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Settings</h1>
        <p className="mt-1 text-sm text-text-secondary">Watchlist and local service status</p>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Watchlist" value={watchlist?.symbols.length ?? 0} icon={<Save className="h-4 w-4" />} />
        <StatCard label="AI calls left" value={budget?.calls_left ?? 0} icon={<BrainCircuit className="h-4 w-4" />} />
        <StatCard label="RAG documents" value={rag?.total ?? 0} icon={<Database className="h-4 w-4" />} />
        <StatCard label="MeroShare" value={meroshare?.enabled ? 'Enabled' : 'Disabled'} icon={<ShieldCheck className="h-4 w-4" />} />
      </div>

      {message && <div className="border-l-4 border-positive bg-green-50 p-3 text-sm text-positive dark:bg-green-900/20">{message}</div>}
      {error && <div className="border-l-4 border-negative bg-red-50 p-3 text-sm text-negative dark:bg-red-900/20">{error}</div>}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <Card title="Advisor watchlist">
          <label className="text-sm font-medium text-text-primary" htmlFor="watchlist-symbols">Symbols</label>
          <textarea
            id="watchlist-symbols"
            value={symbols}
            onChange={(e) => setSymbols(e.target.value)}
            placeholder="NABIL, NICA, HBL"
            className="mt-2 h-28 w-full rounded border border-border bg-surface-secondary p-3 text-sm uppercase text-text-primary"
          />
          <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
            <p className="text-xs text-text-tertiary">Source: {watchlist?.source ?? 'unknown'} · Maximum {watchlist?.max_symbols ?? 0} symbols per advisor run</p>
            <button
              onClick={save}
              disabled={saving}
              className="inline-flex h-9 items-center gap-2 rounded bg-nepse-600 px-4 text-sm font-semibold text-white hover:bg-nepse-700 disabled:opacity-50"
            >
              <Save className="h-4 w-4" /> {saving ? 'Saving...' : 'Save watchlist'}
            </button>
          </div>
        </Card>

        <Card title="MeroShare connection">
          <div className="flex items-center justify-between">
            <span className="text-sm text-text-secondary">Integration</span>
            <Badge text={meroshare?.enabled ? 'Enabled' : 'Disabled'} variant={meroshare?.enabled ? 'success' : 'default'} />
          </div>
          <div className="mt-3 flex items-center justify-between">
            <span className="text-sm text-text-secondary">Credentials</span>
            <Badge text={meroshare?.credentials_configured ? 'Configured' : 'Missing'} variant={meroshare?.credentials_configured ? 'success' : 'warning'} />
          </div>
          <label className="mt-5 flex cursor-pointer items-start gap-3 border-t border-border pt-4">
            <input
              type="checkbox"
              aria-label="Enable MeroShare integration"
              checked={meroshareSetting?.enabled ?? meroshare?.enabled ?? false}
              disabled={toggleSaving}
              onChange={(e) => void toggleMeroshare(e.target.checked)}
              className="mt-0.5 h-4 w-4 accent-nepse-600"
            />
            <span>
              <span className="flex items-center gap-2 text-sm font-semibold text-text-primary"><ToggleRight className="h-4 w-4 text-nepse-600" /> Allow read-only sync</span>
              <span className="mt-1 block text-xs leading-5 text-text-tertiary">Persisted override: {meroshareSetting?.source ?? 'env'}{toggleSaving ? ' · saving...' : ''}. This never enables order placement.</span>
            </span>
          </label>
          <p className="mt-4 text-xs leading-5 text-text-tertiary">Credentials are loaded from environment, optional .env or the OS keyring. They are not shown or stored in the database.</p>
        </Card>
      </div>

      <Card title="AI budget">
        <div className="grid gap-6 md:grid-cols-2">
          <BudgetBar label="Calls today" used={budget?.calls ?? 0} max={budget?.max_calls ?? 0} pct={callPct} />
          <BudgetBar label="Tokens today" used={budget?.tokens ?? 0} max={budget?.max_tokens ?? 0} pct={tokenPct} />
        </div>
        <div className="mt-5 flex flex-wrap gap-4 border-t border-border pt-4 text-sm text-text-secondary">
          <span>Deep passes left: <strong className="text-text-primary">{budget?.deep_passes_left ?? 0}</strong></span>
          <span>Cached calls: <strong className="text-text-primary">{budget?.cached_calls ?? 0}</strong></span>
          <span>Failed calls: <strong className="text-text-primary">{budget?.failed_calls ?? 0}</strong></span>
          {budget?.exhausted && <Badge text="Budget exhausted - AI falls back to Normal" variant="warning" />}
        </div>
      </Card>
    </div>
  );
}

function BudgetBar({ label, used, max, pct }: { label: string; used: number; max: number; pct: number }) {
  return (
    <div>
      <div className="flex justify-between text-sm"><span className="text-text-secondary">{label}</span><span className="font-mono text-text-primary">{used.toLocaleString()} / {max.toLocaleString()}</span></div>
      <div className="mt-2 h-2 overflow-hidden rounded bg-surface-tertiary"><div className="h-full bg-nepse-600" style={{ width: `${Math.min(100, pct)}%` }} /></div>
    </div>
  );
}
