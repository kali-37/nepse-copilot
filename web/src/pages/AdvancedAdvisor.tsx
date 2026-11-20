import { useEffect, useMemo, useState } from 'react';
import { BrainCircuit, CalendarClock, Play, ShieldCheck, Wifi, WifiOff } from 'lucide-react';
import { api } from '../api/client';
import type { Dose, DoseRun, JournalEntry, PlanCard, RashifalRun } from '../api/types';
import { Badge } from '../components/ui/Badge';
import { Card } from '../components/ui/Card';
import { ErrorState } from '../components/ui/ErrorState';
import { LoadingSpinner } from '../components/ui/LoadingSpinner';
import { StatCard } from '../components/ui/StatCard';

const HORIZONS = ['day', 'week', 'month', 'year'] as const;

function money(value: number | null | undefined) {
  return `NPR ${Number(value ?? 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}`;
}

function confidenceValue(value: unknown): number {
  if (typeof value === 'number') return value;
  if (value && typeof value === 'object' && 'value' in value) {
    return Number((value as { value: number }).value);
  }
  return 0;
}

function confidenceLabel(value: unknown, band?: string) {
  const score = confidenceValue(value);
  if (score >= 0.95) return 'still money in the bank';
  if (score >= 0.8) return 'strongly favoured';
  if (score >= 0.6) return 'more likely than not';
  if (score >= 0.4) return 'a coin flip - size it small';
  if (score >= 0.2) return 'unlikely - do not size up';
  return band?.toLowerCase().replaceAll('_', ' ') || 'remote';
}

function confidenceVariant(value: number) {
  if (value >= 0.8) return 'success' as const;
  if (value >= 0.6) return 'info' as const;
  if (value >= 0.4) return 'warning' as const;
  return 'danger' as const;
}

function PlanCardView({ card, journal }: { card: PlanCard; journal?: JournalEntry }) {
  const score = confidenceValue(card.confidence ?? journal?.confidence);
  const band = card.confidence?.band ?? journal?.confidence_band;
  return (
    <article className="border-l-4 border-nepse-500 bg-surface-secondary p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h3 className="text-lg font-bold text-text-primary">{card.symbol}</h3>
            <Badge
              text={card.action}
              variant={card.action === 'accumulate' ? 'success' : card.action === 'reduce' ? 'danger' : 'default'}
            />
          </div>
          <p className="mt-1 text-sm text-text-secondary">{card.rationale}</p>
        </div>
        <div className="text-right">
          <Badge text={`${score.toFixed(2)} ${band ?? ''}`.trim()} variant={confidenceVariant(score)} />
          <p className="mt-1 max-w-52 text-xs text-text-tertiary">
            {confidenceLabel(score, band)}
          </p>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 text-sm md:grid-cols-4">
        <Quote label="Entry zone" value={`${card.entry_low.toFixed(2)} - ${card.entry_high.toFixed(2)}`} />
        <Quote label="Stop" value={card.stop.toFixed(2)} tone="negative" />
        <Quote label="Targets" value={card.targets.map((target) => target.toFixed(2)).join(' / ')} tone="positive" />
        <Quote label="Quantity" value={`${card.quantity} shares`} />
        <Quote label="Expected net" value={money(card.net_pnl)} tone={card.net_pnl >= 0 ? 'positive' : 'negative'} />
        <Quote label="Fees + tax" value={money(card.entry_cost + card.exit_cost + card.capital_gains_tax)} />
        <Quote label="Review window" value={`${card.horizon_days} trading days`} />
        <Quote label="Earliest sell" value={card.earliest_sell_date} />
      </div>

      {card.note && <p className="mt-4 border-t border-border pt-3 text-sm text-text-secondary">{card.note}</p>}
    </article>
  );
}

function Quote({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: 'positive' | 'negative';
}) {
  return (
    <div>
      <div className="text-xs text-text-tertiary">{label}</div>
      <div className={`mt-0.5 font-semibold ${tone ? `text-${tone}` : 'text-text-primary'}`}>{value}</div>
    </div>
  );
}

function DoseStrip({ dose }: { dose: Dose }) {
  const score = confidenceValue(dose.confidence);
  return (
    <div className="min-w-0 border-t-2 border-nepse-400 pt-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-xs font-semibold uppercase text-text-tertiary">{dose.horizon} dose</div>
          <div className="mt-1 text-lg font-bold text-text-primary">{Math.round(dose.allocation_pct * 100)}%</div>
        </div>
        <Badge text={score.toFixed(2)} variant={confidenceVariant(score)} />
      </div>
      <div className="mt-3 space-y-1 text-xs text-text-secondary">
        <div>{dose.horizon_days} trading days</div>
        <div>{money(dose.allocated_capital)} allocated</div>
        <div className={dose.expected_net_pnl >= 0 ? 'text-positive' : 'text-negative'}>
          {money(dose.expected_net_pnl)} expected net
        </div>
        <div>{dose.symbols.length ? dose.symbols.join(', ') : 'No card assigned'}</div>
      </div>
    </div>
  );
}

function outcomeVariant(entry: JournalEntry) {
  if (entry.outcome === 'TARGET_HIT') return 'success' as const;
  if (entry.outcome === 'STOP_HIT') return 'danger' as const;
  if (entry.status === 'open') return 'info' as const;
  return 'warning' as const;
}

function PastCall({ entry }: { entry: JournalEntry }) {
  const outcome = entry.outcome?.replaceAll('_', ' ') ?? 'Awaiting outcome';
  return (
    <article className="border-l-2 border-border py-1 pl-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-semibold text-text-primary">{entry.symbol}</h3>
            <Badge text={entry.status.toUpperCase()} variant={entry.status === 'open' ? 'info' : 'default'} />
            <Badge text={outcome} variant={outcomeVariant(entry)} />
          </div>
          <p className="mt-1 text-xs text-text-tertiary">Called {entry.made_on} · {entry.horizon || `${entry.horizon_days} days`} · review by {entry.deadline}</p>
        </div>
        <Badge text={`${Number(entry.confidence).toFixed(2)} ${entry.confidence_band}`} variant={confidenceVariant(Number(entry.confidence))} />
      </div>
      <div className="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        <Quote label="Expected net" value={money(entry.expected_net_pnl)} tone={(entry.expected_net_pnl ?? 0) >= 0 ? 'positive' : 'negative'} />
        <Quote label="Realized net" value={entry.realized_net_pnl == null ? 'Pending' : money(entry.realized_net_pnl)} tone={entry.realized_net_pnl == null ? undefined : entry.realized_net_pnl >= 0 ? 'positive' : 'negative'} />
        <Quote label="Entry zone" value={entry.entry_low == null ? '—' : `${entry.entry_low.toFixed(2)} - ${Number(entry.entry_high ?? entry.entry_low).toFixed(2)}`} />
        <Quote label="Target / stop" value={`${entry.target_1?.toFixed(2) ?? '—'} / ${entry.stop?.toFixed(2) ?? '—'}`} />
      </div>
      {entry.review && <p className="mt-3 text-sm leading-6 text-text-secondary"><strong className="text-text-primary">Review:</strong> {entry.review}</p>}
      {entry.lesson && <p className="mt-2 border-l-2 border-nepse-400 pl-3 text-sm leading-6 text-text-secondary"><strong className="text-text-primary">Lesson:</strong> {entry.lesson}</p>}
    </article>
  );
}

export function AdvancedAdvisorPage() {
  const [mode, setMode] = useState<'normal' | 'ai'>('normal');
  const [online, setOnline] = useState(false);
  const [horizon, setHorizon] = useState<(typeof HORIZONS)[number]>('week');
  const [equity, setEquity] = useState(100_000);
  const [symbols, setSymbols] = useState('');
  const [result, setResult] = useState<RashifalRun | null>(null);
  const [doses, setDoses] = useState<DoseRun | null>(null);
  const [journal, setJournal] = useState<JournalEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    Promise.all([
      api.advisorLatest().catch(() => null),
      api.doseLatest().catch(() => null),
      api.journalHistory({ limit: 50 }).catch(() => []),
    ])
      .then(([latest, doseRun, entries]) => {
        setResult(latest);
        setDoses(latest?.doses ?? doseRun);
        setJournal(entries);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const journalBySymbol = useMemo(() => {
    const latest = new Map<string, JournalEntry>();
    for (const entry of journal) {
      if (!latest.has(entry.symbol)) latest.set(entry.symbol, entry);
    }
    return latest;
  }, [journal]);

  const run = async () => {
    setRunning(true);
    setError(null);
    try {
      const next = await api.runAdvisor({
        mode,
        horizon,
        online,
        equity,
        symbols: symbols.split(',').map((item) => item.trim().toUpperCase()).filter(Boolean),
      });
      setResult(next);
      setDoses(next.doses ?? (await api.doseLatest().catch(() => null)));
      setJournal(await api.journalHistory({ limit: 50 }).catch(() => []));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  };

  if (loading) return <LoadingSpinner text="Loading advisor..." />;
  if (error && !result) return <ErrorState message={error} onRetry={load} />;

  const headlineConfidence = confidenceValue(doses?.confidence);
  const openPredictions = journal.filter((entry) => entry.status === 'open').length;

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">Rashifal</h1>
          <p className="mt-1 text-sm text-text-secondary">Daily prescription from price, risk, costs and recorded outcomes</p>
        </div>

        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="mb-1 block text-xs text-text-tertiary">Capital</label>
            <input
              aria-label="Capital"
              type="number"
              min={1}
              value={equity}
              onChange={(e) => setEquity(Number(e.target.value))}
              className="h-10 w-36 rounded border border-border bg-surface px-3 text-sm text-text-primary"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-text-tertiary">Symbols</label>
            <input
              aria-label="Symbols"
              value={symbols}
              onChange={(e) => setSymbols(e.target.value)}
              placeholder="Watchlist or NABIL,NICA"
              className="h-10 w-52 rounded border border-border bg-surface px-3 text-sm text-text-primary"
            />
          </div>
          <button
            onClick={run}
            disabled={running || equity <= 0}
            className="inline-flex h-10 items-center gap-2 rounded bg-nepse-600 px-4 text-sm font-semibold text-white hover:bg-nepse-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Play className="h-4 w-4" /> {running ? 'Calculating...' : 'Run prescription'}
          </button>
        </div>
      </div>

      <div className="flex flex-wrap gap-3 border-y border-border py-3">
        <Segmented
          label="Analysis mode"
          options={[['normal', 'Normal'], ['ai', 'AI']]}
          value={mode}
          onChange={(value) => setMode(value as 'normal' | 'ai')}
        />
        <Segmented
          label="Horizon"
          options={HORIZONS.map((item) => [item, item[0].toUpperCase() + item.slice(1)])}
          value={horizon}
          onChange={(value) => setHorizon(value as (typeof HORIZONS)[number])}
        />
        <button
          type="button"
          onClick={() => setOnline((value) => !value)}
          aria-pressed={online}
          className={`inline-flex h-9 items-center gap-2 rounded border px-3 text-sm font-medium ${
            online ? 'border-positive bg-green-50 text-positive dark:bg-green-900/20' : 'border-border bg-surface text-text-secondary'
          }`}
        >
          {online ? <Wifi className="h-4 w-4" /> : <WifiOff className="h-4 w-4" />}
          {online ? 'Online evidence' : 'Offline only'}
        </button>
      </div>

      {error && <div className="border-l-4 border-negative bg-red-50 p-3 text-sm text-negative dark:bg-red-900/20">{error}</div>}
      {result?.banner && <div className="border-l-4 border-warning bg-amber-50 p-3 text-sm text-warning dark:bg-amber-900/20">{result.banner}</div>}

      {result ? (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard label="Market regime" value={result.regime || 'mixed'} icon={<BrainCircuit className="h-4 w-4" />} />
            <StatCard label="Plan cards" value={result.cards.length} icon={<ShieldCheck className="h-4 w-4" />} />
            <StatCard label="Open predictions" value={openPredictions} icon={<CalendarClock className="h-4 w-4" />} />
            <StatCard
              label="Weakest confidence"
              value={headlineConfidence.toFixed(2)}
              change={confidenceLabel(headlineConfidence)}
              changeType={headlineConfidence >= 0.6 ? 'positive' : 'neutral'}
            />
          </div>

          {doses && (
            <Card title="Four doses">
              <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
                {doses.doses.map((dose) => <DoseStrip key={dose.horizon} dose={dose} />)}
              </div>
              <div className="mt-5 flex flex-wrap gap-x-6 gap-y-2 border-t border-border pt-4 text-sm text-text-secondary">
                <span>Deployed: <strong className="text-text-primary">{money(doses.deployed_capital)}</strong></span>
                <span>Estimated net: <strong className={doses.expected_net_pnl >= 0 ? 'text-positive' : 'text-negative'}>{money(doses.expected_net_pnl)}</strong></span>
                <span>Cash untouched: <strong className="text-text-primary">{money(Math.max(0, doses.capital - doses.deployed_capital))}</strong></span>
              </div>
            </Card>
          )}

          {result.thesis && <Card title="Market reading"><p className="max-w-4xl text-sm leading-6 text-text-secondary">{result.thesis}</p></Card>}

          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-text-primary">Action cards</h2>
              <span className="text-xs text-text-tertiary">Generated {result.generated_at ? new Date(result.generated_at).toLocaleString() : result.run_date}</span>
            </div>
            {result.cards.length ? result.cards.map((card) => (
              <PlanCardView key={card.symbol} card={card} journal={journalBySymbol.get(card.symbol)} />
            )) : <Card><p className="py-6 text-center text-sm text-text-tertiary">No complete plan cards could be built from the stored history.</p></Card>}
          </section>

          <Card title="Past calls & outcomes">
            {journal.length ? (
              <div className="space-y-5">
                {journal.map((entry) => <PastCall key={entry.prediction_id} entry={entry} />)}
              </div>
            ) : (
              <p className="py-6 text-center text-sm text-text-tertiary">No prediction journal entries yet. Run a prescription to start the audit trail.</p>
            )}
          </Card>

          {(result.sell_queue.length > 0 || result.do_not_touch.length > 0) && (
            <div className="grid gap-6 lg:grid-cols-2">
              <Card title="Sell queue">
                <div className="space-y-3">
                  {result.sell_queue.map((item) => (
                    <div key={item.symbol} className="border-b border-border pb-3 last:border-0 last:pb-0">
                      <div className="font-semibold text-text-primary">{item.symbol} · {item.quantity} shares</div>
                      <p className="mt-1 text-sm text-text-secondary">{item.reason}</p>
                      <p className="mt-1 text-xs text-text-tertiary">Earliest sell {item.earliest_sell_date}</p>
                    </div>
                  ))}
                  {!result.sell_queue.length && <p className="text-sm text-text-tertiary">Nothing to exit.</p>}
                </div>
              </Card>
              <Card title="Do not touch">
                <div className="space-y-3">
                  {result.do_not_touch.map((item) => (
                    <div key={item.symbol} className="border-b border-border pb-3 last:border-0 last:pb-0">
                      <div className="font-semibold text-text-primary">{item.symbol}</div>
                      <p className="mt-1 text-sm text-text-secondary">{item.reason}</p>
                    </div>
                  ))}
                  {!result.do_not_touch.length && <p className="text-sm text-text-tertiary">No exclusions.</p>}
                </div>
              </Card>
            </div>
          )}
        </>
      ) : (
        <Card>
          <div className="py-10 text-center">
            <CalendarClock className="mx-auto h-8 w-8 text-text-tertiary" />
            <p className="mt-3 text-sm text-text-secondary">No prescription has been generated yet.</p>
          </div>
        </Card>
      )}
    </div>
  );
}

function Segmented({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: readonly (readonly [string, string])[];
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div className="flex h-9 items-center rounded border border-border bg-surface p-0.5" aria-label={label}>
      {options.map(([key, text]) => (
        <button
          key={key}
          type="button"
          onClick={() => onChange(key)}
          className={`h-8 rounded px-3 text-xs font-semibold ${value === key ? 'bg-nepse-600 text-white' : 'text-text-secondary hover:text-text-primary'}`}
        >
          {text}
        </button>
      ))}
    </div>
  );
}
