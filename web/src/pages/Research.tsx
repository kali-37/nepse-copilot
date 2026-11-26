import { useEffect, useState } from 'react';
import { BookOpen, Database, Search } from 'lucide-react';
import { api } from '../api/client';
import type { NewsItem, RagSearchResponse, RagStats } from '../api/types';
import { Badge } from '../components/ui/Badge';
import { Card } from '../components/ui/Card';
import { ErrorState } from '../components/ui/ErrorState';
import { LoadingSpinner } from '../components/ui/LoadingSpinner';
import { StatCard } from '../components/ui/StatCard';
import { FinancialCoveragePanel } from '../components/research/FinancialCoveragePanel';
import { ModelValidationPanel } from '../components/research/ModelValidationPanel';

export function ResearchPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Research</h1>
        <p className="mt-1 text-sm text-text-secondary">Inspect financial evidence, test model estimates and search the local evidence library</p>
      </div>
      <FinancialCoveragePanel />
      <ModelValidationPanel />
      <EvidenceLibrary />
    </div>
  );
}

function EvidenceLibrary() {
  const [query, setQuery] = useState('');
  const [symbol, setSymbol] = useState('');
  const [stats, setStats] = useState<RagStats | null>(null);
  const [news, setNews] = useState<NewsItem[]>([]);
  const [results, setResults] = useState<RagSearchResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.ragStats(), api.news(10)])
      .then(([nextStats, nextNews]) => { setStats(nextStats); setNews(nextNews); })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const search = async () => {
    setSearching(true);
    setError(null);
    try {
      setResults(await api.ragSearch(query, { symbol: symbol.trim().toUpperCase() || undefined }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSearching(false);
    }
  };

  if (loading) return <LoadingSpinner text="Loading research library..." />;
  if (error && !stats) return <ErrorState message={error} />;

  return (
    <>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Indexed documents" value={stats?.total ?? 0} icon={<Database className="h-4 w-4" />} />
        <StatCard label="Search engine" value={stats?.uses_fts ? 'FTS5 / BM25' : 'LIKE fallback'} icon={<Search className="h-4 w-4" />} />
        <StatCard label="Document kinds" value={Object.keys(stats?.per_kind ?? {}).length} icon={<BookOpen className="h-4 w-4" />} />
        <StatCard label="Recent news" value={news.length} />
      </div>

      <Card>
        <form
          onSubmit={(e) => { e.preventDefault(); void search(); }}
          className="flex flex-col gap-3 md:flex-row"
        >
          <input
            aria-label="Research query"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="What changed for commercial banks?"
            className="h-11 min-w-0 flex-1 rounded border border-border bg-surface-secondary px-3 text-sm text-text-primary"
          />
          <input
            aria-label="Symbol filter"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            placeholder="Symbol (optional)"
            className="h-11 rounded border border-border bg-surface-secondary px-3 text-sm uppercase text-text-primary md:w-44"
          />
          <button disabled={searching} className="inline-flex h-11 items-center justify-center gap-2 rounded bg-nepse-600 px-5 text-sm font-semibold text-white hover:bg-nepse-700 disabled:opacity-50">
            <Search className="h-4 w-4" /> {searching ? 'Searching...' : 'Search evidence'}
          </button>
        </form>
      </Card>

      {error && <div className="border-l-4 border-negative bg-red-50 p-3 text-sm text-negative dark:bg-red-900/20">{error}</div>}

      {results && (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-text-primary">Evidence</h2>
              <span className="text-xs text-text-tertiary">{results.count} result{results.count === 1 ? '' : 's'}</span>
            </div>
            {results.hits.map((hit, index) => (
              <article key={hit.doc_id} className="border-b border-border bg-surface px-1 py-4 first:pt-0">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs font-bold text-nepse-600">[{index + 1}]</span>
                      <h3 className="font-semibold text-text-primary">{hit.title}</h3>
                    </div>
                    <div className="mt-1 flex flex-wrap gap-2">
                      <Badge text={hit.kind} />
                      {hit.symbol && <Badge text={hit.symbol} variant="info" />}
                    </div>
                  </div>
                  <span className="font-mono text-xs text-text-tertiary">score {hit.score.toFixed(3)}</span>
                </div>
                <p className="mt-3 text-sm leading-6 text-text-secondary">{hit.body}</p>
                <div className="mt-3 text-xs text-text-tertiary">{hit.source}{hit.business_date ? ` · ${hit.business_date}` : ''}</div>
              </article>
            ))}
            {!results.hits.length && <Card><p className="py-6 text-center text-sm text-text-tertiary">No local evidence matched this query.</p></Card>}
          </section>

          <Card title="Citation pack" className="h-fit xl:sticky xl:top-24">
            <pre className="max-h-[36rem] overflow-auto whitespace-pre-wrap font-mono text-xs leading-5 text-text-secondary">{results.evidence.rendered || 'No citation pack was produced.'}</pre>
          </Card>
        </div>
      )}

      {!results && (
        <div className="grid gap-6 lg:grid-cols-[1fr_20rem]">
          <Card title="Recent indexed news">
            <div className="space-y-4">
              {news.map((item) => (
                <article key={item.doc_id} className="border-b border-border pb-4 last:border-0 last:pb-0">
                  <div className="flex items-center gap-2">
                    {item.symbol && <Badge text={item.symbol} variant="info" />}
                    <h3 className="font-semibold text-text-primary">{item.title}</h3>
                  </div>
                  <p className="mt-2 line-clamp-3 text-sm leading-6 text-text-secondary">{item.body}</p>
                </article>
              ))}
              {!news.length && <p className="py-6 text-center text-sm text-text-tertiary">No news has been indexed yet.</p>}
            </div>
          </Card>
          <Card title="Library coverage">
            <div className="space-y-3">
              {Object.entries(stats?.per_kind ?? {}).sort((a, b) => b[1] - a[1]).map(([kind, count]) => (
                <div key={kind} className="flex items-center justify-between border-b border-border pb-2 text-sm last:border-0">
                  <span className="text-text-secondary">{kind}</span>
                  <span className="font-mono font-semibold text-text-primary">{count}</span>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}
    </>
  );
}
