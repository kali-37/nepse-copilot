import { useEffect, useState } from 'react';
import { Bot, CircleDollarSign, Database, Layers, Send } from 'lucide-react';
import { api } from '../api/client';
import type { AiBudget, AiModelsResponse, AiTestResult } from '../api/types';
import { Badge } from '../components/ui/Badge';
import { Card } from '../components/ui/Card';
import { DataTable } from '../components/ui/DataTable';
import { ErrorState } from '../components/ui/ErrorState';
import { LoadingSpinner } from '../components/ui/LoadingSpinner';
import { StatCard } from '../components/ui/StatCard';

export function AiPage() {
  const [models, setModels] = useState<AiModelsResponse | null>(null);
  const [budget, setBudget] = useState<AiBudget | null>(null);
  const [test, setTest] = useState<AiTestResult | null>(null);
  const [tier, setTier] = useState<'bulk' | 'synthesis'>('synthesis');
  const [testing, setTesting] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.aiModels(), api.aiBudget()])
      .then(([nextModels, nextBudget]) => {
        setModels(nextModels);
        setBudget(nextBudget);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
  }, []);

  const runTest = async () => {
    setTesting(true);
    setError(null);
    try {
      setTest(await api.aiTest(tier));
      setBudget(await api.aiBudget());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setTesting(false);
    }
  };

  if (loading) return <LoadingSpinner text="Reading provider configuration..." />;
  if (error && !models) return <ErrorState message={error} />;
  if (!models) return null;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">AI</h1>
        <p className="mt-1 text-sm text-text-secondary">
          Which providers are configured, what today&apos;s spend looks like, and whether a chain
          actually answers. AI writes the prose; every number comes from the deterministic engine.
        </p>
      </div>

      {models.banner && (
        <div className="border-l-4 border-warning bg-amber-50 p-3 text-sm text-amber-800 dark:bg-amber-900/20 dark:text-amber-400">
          {models.banner}
        </div>
      )}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard
          label="Usable legs"
          value={models.usable_legs}
          change={models.online ? 'online' : 'offline'}
          changeType={models.usable_legs > 0 ? 'positive' : 'negative'}
          icon={<Layers className="h-4 w-4" />}
        />
        <StatCard
          label="Calls today"
          value={`${budget?.calls ?? 0} / ${budget?.max_calls ?? 0}`}
          change={budget?.exhausted ? 'budget spent' : `${budget?.calls_left ?? 0} left`}
          changeType={budget?.exhausted ? 'negative' : 'neutral'}
          icon={<CircleDollarSign className="h-4 w-4" />}
        />
        <StatCard
          label="Tokens today"
          value={(budget?.tokens ?? 0).toLocaleString()}
          change={`${(budget?.tokens_left ?? 0).toLocaleString()} left`}
          changeType="neutral"
        />
        <StatCard
          label="Cached answers"
          value={models.cache.entries}
          change={models.cache.enabled ? `${models.cache.ttl_hours}h TTL` : 'cache off'}
          changeType="neutral"
          icon={<Database className="h-4 w-4" />}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Provider chains">
          <p className="mb-3 text-sm text-text-secondary">
            Each tier tries its legs in order and stops at the first one that answers. Read from
            configuration only &mdash; opening this page calls nobody.
          </p>
          <div className="space-y-4">
            {Object.entries(models.tiers).map(([tierName, legs]) => (
              <div key={tierName}>
                <h4 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-text-secondary">
                  {tierName}
                </h4>
                <ol className="space-y-1.5">
                  {legs.map((leg, index) => (
                    <li
                      key={`${tierName}-${leg.name}`}
                      className="flex flex-wrap items-center gap-2 text-sm"
                    >
                      <span className="font-mono text-xs text-text-tertiary">{index + 1}.</span>
                      <span className="font-medium text-text-primary">{leg.name}</span>
                      <Badge
                        text={leg.available ? 'ready' : leg.known ? 'no key' : 'unknown provider'}
                        variant={leg.available ? 'success' : leg.known ? 'warning' : 'danger'}
                      />
                      {leg.model && (
                        <span className="font-mono text-xs text-text-tertiary">{leg.model}</span>
                      )}
                    </li>
                  ))}
                  {legs.length === 0 && (
                    <li className="text-sm text-text-tertiary">No legs configured for this tier.</li>
                  )}
                </ol>
              </div>
            ))}
          </div>
        </Card>

        <Card title="Send one test prompt">
          <p className="text-sm text-text-secondary">
            The only honest way to know a provider works is to use it. This sends one tiny prompt,
            skips the cache, and spends real budget &mdash; so it never runs on page load.
          </p>
          <div className="mt-4 flex flex-wrap items-end gap-3">
            <label className="block text-sm">
              <span className="mb-1 block text-xs font-medium text-text-secondary">Tier</span>
              <select
                value={tier}
                onChange={(e) => setTier(e.target.value as 'bulk' | 'synthesis')}
                className="h-10 rounded-lg border border-border bg-surface px-3 text-sm text-text-primary"
              >
                <option value="synthesis">synthesis</option>
                <option value="bulk">bulk</option>
              </select>
            </label>
            <button
              onClick={() => void runTest()}
              disabled={testing}
              className="inline-flex h-10 items-center gap-2 rounded-lg bg-nepse-600 px-4 text-sm font-semibold text-white hover:bg-nepse-700 disabled:opacity-50"
            >
              <Send className="h-4 w-4" />
              {testing ? 'Waiting for an answer...' : 'Test this chain'}
            </button>
          </div>

          {error && <p className="mt-3 text-sm text-negative">{error}</p>}

          {test && (
            <div className="mt-4 border-t border-border pt-4">
              <div className="flex flex-wrap items-center gap-2">
                <Badge text={test.ok ? 'answered' : 'no answer'} variant={test.ok ? 'success' : 'danger'} />
                {test.provider && <Badge text={test.provider} variant="info" />}
                {test.model && (
                  <span className="font-mono text-xs text-text-tertiary">{test.model}</span>
                )}
                <span className="text-xs text-text-tertiary">{test.total_tokens} tokens</span>
              </div>
              {test.ok ? (
                <pre className="mt-3 max-h-40 overflow-auto whitespace-pre-wrap rounded bg-surface-tertiary p-3 text-xs leading-relaxed text-text-secondary">
                  {test.text || '(the provider answered with nothing)'}
                </pre>
              ) : (
                <p className="mt-3 text-sm text-negative">
                  {test.error || 'Nobody in the chain answered.'}
                </p>
              )}
            </div>
          )}

          {!test && (
            <div className="mt-6 flex flex-col items-center gap-2 py-6 text-text-tertiary">
              <Bot className="h-8 w-8" />
              <p className="text-sm">No test has been run this session.</p>
            </div>
          )}
        </Card>
      </div>

      <Card title="Recent spend">
        {!budget?.history.length ? (
          <p className="py-6 text-center text-sm text-text-tertiary">
            The ledger is empty &mdash; no AI call has been made yet.
          </p>
        ) : (
          <DataTable
            columns={Object.keys(budget.history[0]).map((key) => ({
              key,
              label: key.replace(/_/g, ' '),
              render: (row: Record<string, unknown>) => {
                const value = row[key];
                if (value === null || value === undefined) return '—';
                if (typeof value === 'number') return Number(value.toFixed(4)).toString();
                return String(value);
              },
            }))}
            data={budget.history}
          />
        )}
        <p className="mt-3 border-t border-border pt-3 text-xs text-text-tertiary">
          Caps reset daily ({budget?.day}) and weekly ({budget?.week}). Deep passes:{' '}
          {budget?.deep_passes ?? 0} of {budget?.max_deep_passes ?? 0} used.
        </p>
      </Card>
    </div>
  );
}
