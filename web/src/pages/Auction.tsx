import { useEffect, useState, type FormEvent, type ReactNode } from 'react';
import { AlertTriangle, CalendarDays, Gavel, History, ShieldCheck } from 'lucide-react';
import { api } from '../api/client';
import type { AuctionAdvice, AuctionAdviceRequest } from '../api/types';
import { Badge } from '../components/ui/Badge';
import { Card } from '../components/ui/Card';
import { ErrorState } from '../components/ui/ErrorState';
import { LoadingSpinner } from '../components/ui/LoadingSpinner';
import { StatCard } from '../components/ui/StatCard';

function money(value: number | null | undefined) {
  return `NPR ${Number(value ?? 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}`;
}

function price(value: number | null | undefined) {
  return Number(value ?? 0).toFixed(2);
}

function confidenceVariant(value: number) {
  if (value >= 0.8) return 'success' as const;
  if (value >= 0.6) return 'info' as const;
  if (value >= 0.4) return 'warning' as const;
  return 'danger' as const;
}

const today = new Date().toISOString().slice(0, 10);

const initialForm: AuctionAdviceRequest = {
  symbol: '',
  auction_date: today,
  units: 10,
  min_bid_price: 100,
  market_price: 120,
  expected_exit_price: 140,
  horizon_days: 10,
  quantity: 10,
  confidence: 0.45,
  edge_buffer_pct: 0.1,
};

const inputClass = 'h-10 w-full rounded border border-border bg-surface-secondary px-3 text-sm text-text-primary';

export function AuctionPage() {
  const [form, setForm] = useState<AuctionAdviceRequest>(initialForm);
  const [advice, setAdvice] = useState<AuctionAdvice | null>(null);
  const [history, setHistory] = useState<AuctionAdvice[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    api.auctionHistory({ limit: 20 })
      .then((rows) => {
        setHistory(rows);
        if (rows[0]) setAdvice(rows[0]);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const setNumber = (key: keyof AuctionAdviceRequest, raw: string) => {
    const value = Number(raw);
    setForm((current) => ({ ...current, [key]: Number.isFinite(value) ? value : 0 }));
  };

  const run = async (event: FormEvent) => {
    event.preventDefault();
    if (!form.symbol.trim()) {
      setError('Enter the auction symbol first.');
      return;
    }
    setRunning(true);
    setError(null);
    try {
      const next = await api.auctionAdvice({
        ...form,
        symbol: form.symbol.trim().toUpperCase(),
        auction_date: form.auction_date || undefined,
        expected_exit_price: form.expected_exit_price || undefined,
        quantity: form.quantity || undefined,
        confidence: form.confidence == null ? undefined : form.confidence,
      });
      setAdvice(next);
      setHistory((current) => [next, ...current.filter((row) => row.advice_id !== next.advice_id)]);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  };

  if (loading) return <LoadingSpinner text="Loading auction advice..." />;
  if (error && !advice && !history.length) return <ErrorState message={error} onRetry={load} />;

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">Auction advice</h1>
          <p className="mt-1 text-sm text-text-secondary">Price a manual auction bid against the full Nepal fee stack.</p>
        </div>
        <div className="inline-flex items-center gap-2 border-l-4 border-warning bg-amber-50 px-3 py-2 text-xs text-warning dark:bg-amber-900/20">
          <AlertTriangle className="h-4 w-4" /> Advice only. No bid is submitted.
        </div>
      </div>

      {error && <div className="border-l-4 border-negative bg-red-50 p-3 text-sm text-negative dark:bg-red-900/20">{error}</div>}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <Card title="Auction assumptions">
          <form onSubmit={run} className="grid gap-4 sm:grid-cols-2">
            <Field label="Symbol" name="auction-symbol">
              <input id="auction-symbol" aria-label="Auction symbol" required value={form.symbol} onChange={(e) => setForm({ ...form, symbol: e.target.value.toUpperCase() })} placeholder="NABIL" className={inputClass} />
            </Field>
            <Field label="Auction date" name="auction-date">
              <input id="auction-date" aria-label="Auction date" type="date" value={form.auction_date ?? ''} onChange={(e) => setForm({ ...form, auction_date: e.target.value })} className={inputClass} />
            </Field>
            <Field label="Units offered" name="auction-units">
              <input id="auction-units" aria-label="Units offered" type="number" min={1} value={form.units} onChange={(e) => setNumber('units', e.target.value)} className={inputClass} />
            </Field>
            <Field label="Units you would assess" name="auction-quantity">
              <input id="auction-quantity" aria-label="Units you would assess" type="number" min={1} max={form.units} value={form.quantity ?? ''} onChange={(e) => setNumber('quantity', e.target.value)} className={inputClass} />
            </Field>
            <Field label="Minimum bid (NPR)" name="min-bid">
              <input id="min-bid" aria-label="Minimum bid" type="number" min={0.01} step="0.01" value={form.min_bid_price} onChange={(e) => setNumber('min_bid_price', e.target.value)} className={inputClass} />
            </Field>
            <Field label="Market price (NPR)" name="market-price">
              <input id="market-price" aria-label="Market price" type="number" min={0.01} step="0.01" value={form.market_price} onChange={(e) => setNumber('market_price', e.target.value)} className={inputClass} />
            </Field>
            <Field label="Expected exit (NPR)" name="expected-exit">
              <input id="expected-exit" aria-label="Expected exit price" type="number" min={0.01} step="0.01" value={form.expected_exit_price ?? ''} onChange={(e) => setNumber('expected_exit_price', e.target.value)} className={inputClass} />
            </Field>
            <Field label="Holding horizon (trading days)" name="horizon-days">
              <input id="horizon-days" aria-label="Holding horizon" type="number" min={0} value={form.horizon_days} onChange={(e) => setNumber('horizon_days', e.target.value)} className={inputClass} />
            </Field>
            <Field label="Market confidence (0–1)" name="auction-confidence">
              <input id="auction-confidence" aria-label="Market confidence" type="number" min={0} max={1} step="0.01" value={form.confidence ?? ''} onChange={(e) => setNumber('confidence', e.target.value)} className={inputClass} />
            </Field>
            <Field label="Margin under break-even" name="edge-buffer">
              <input id="edge-buffer" aria-label="Margin under break-even" type="number" min={0} max={0.99} step="0.01" value={form.edge_buffer_pct} onChange={(e) => setNumber('edge_buffer_pct', e.target.value)} className={inputClass} />
            </Field>
            <div className="sm:col-span-2 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4">
              <p className="max-w-xl text-xs leading-5 text-text-tertiary">The exit price is your explicit assumption. Fees, settlement timing, and the conservative bid ceiling are calculated by the engine.</p>
              <button type="submit" disabled={running} className="inline-flex h-10 items-center gap-2 rounded bg-nepse-600 px-4 text-sm font-semibold text-white hover:bg-nepse-700 disabled:opacity-50">
                <Gavel className="h-4 w-4" /> {running ? 'Calculating...' : 'Calculate advice'}
              </button>
            </div>
          </form>
        </Card>

        <Card title="How to read the ladder">
          <div className="space-y-4 text-sm">
            <LadderLegend color="bg-nepse-500" label="Minimum" text="The auction's stated starting price." />
            <LadderLegend color="bg-positive" label="Conservative ceiling" text="The highest bid that preserves the requested margin after fees." />
            <LadderLegend color="bg-warning" label="Walk-away" text="Fee-neutral break-even. Bids above this lose the edge under the stated exit." />
          </div>
        </Card>
      </div>

      {advice && <AdviceResult advice={advice} />}

      <Card title="Saved advice" actions={<History className="h-4 w-4 text-text-tertiary" />}>
        {history.length ? (
          <div className="divide-y divide-border">
            {history.map((row) => (
              <button key={row.advice_id} type="button" onClick={() => setAdvice(row)} className="grid w-full grid-cols-[1fr_auto_auto] items-center gap-3 py-3 text-left hover:bg-surface-tertiary">
                <span><strong className="text-text-primary">{row.symbol}</strong><span className="ml-2 text-xs text-text-tertiary">{row.auction_date}</span></span>
                <span className="font-mono text-xs text-text-secondary">{price(row.recommended_bid)} → {price(row.max_sensible_bid)}</span>
                <Badge text={row.verdict.toUpperCase()} variant={row.verdict === 'bid' ? 'success' : 'warning'} />
              </button>
            ))}
          </div>
        ) : <p className="py-6 text-center text-sm text-text-tertiary">No auction advice saved yet.</p>}
      </Card>
    </div>
  );
}

function Field({ label, name, children }: { label: string; name: string; children: ReactNode }) {
  return <label htmlFor={name} className="block text-sm font-medium text-text-primary"><span className="mb-1 block text-xs text-text-tertiary">{label}</span>{children}</label>;
}

function LadderLegend({ color, label, text }: { color: string; label: string; text: string }) {
  return <div className="flex gap-3"><span className={`mt-1 h-3 w-3 shrink-0 ${color}`} /><div><div className="font-semibold text-text-primary">{label}</div><p className="mt-1 text-xs leading-5 text-text-secondary">{text}</p></div></div>;
}

function AdviceResult({ advice }: { advice: AuctionAdvice }) {
  const score = Number(advice.confidence ?? 0);
  return (
    <Card title={`${advice.symbol} · ${advice.auction_date}`}>
      <div className="flex flex-col gap-4 border-b border-border pb-4 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2"><Badge text={advice.verdict.toUpperCase()} variant={advice.verdict === 'bid' ? 'success' : 'warning'} /><span className="text-sm text-text-secondary">{advice.rationale}</span></div>
          <div className="mt-3 flex items-center gap-2 text-xs text-text-tertiary"><ShieldCheck className="h-4 w-4" /> Manual advice only · no order was placed</div>
        </div>
        <Badge text={`${score.toFixed(2)} ${advice.confidence_band}`} variant={confidenceVariant(score)} />
      </div>
      <div className="mt-5 grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard label="Recommended bid" value={money(advice.recommended_bid)} />
        <StatCard label="Conservative ceiling" value={money(advice.max_sensible_bid)} />
        <StatCard label="Walk-away" value={money(advice.walk_away_price)} />
        <StatCard label="Break-even exit" value={money(advice.breakeven_price)} />
      </div>
      <div className="mt-5 grid grid-cols-2 gap-x-4 gap-y-3 border-t border-border pt-4 text-sm md:grid-cols-4">
        <Metric label="Outlay" value={money(advice.outlay)} />
        <Metric label="Expected net" value={money(advice.expected_net_pnl)} tone={advice.expected_net_pnl >= 0 ? 'positive' : 'negative'} />
        <Metric label="Expected return" value={`${advice.expected_return_pct.toFixed(2)}%`} tone={advice.expected_return_pct >= 0 ? 'positive' : 'negative'} />
        <Metric label="Earliest sell" value={advice.earliest_sell_date} />
      </div>
      <p className="mt-4 flex items-center gap-2 text-xs text-text-tertiary"><CalendarDays className="h-4 w-4" /> {advice.horizon_days} trading days · {advice.quantity} shares assessed · {advice.confidence_basis}</p>
    </Card>
  );
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: 'positive' | 'negative' }) {
  return <div><div className="text-xs text-text-tertiary">{label}</div><div className={`mt-1 font-semibold ${tone === 'positive' ? 'text-positive' : tone === 'negative' ? 'text-negative' : 'text-text-primary'}`}>{value}</div></div>;
}
