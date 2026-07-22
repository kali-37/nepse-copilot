import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search } from 'lucide-react';
import { api } from '../api/client';
import { Card } from '../components/ui/Card';
import { ErrorState } from '../components/ui/ErrorState';
import { LoadingSpinner } from '../components/ui/LoadingSpinner';

export function SymbolsPage() {
  const navigate = useNavigate();
  const [symbols, setSymbols] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(0);

  const PAGE_SIZE = 50;

  useEffect(() => {
    api.symbols()
      .then(setSymbols)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const filtered = useMemo(
    () =>
      symbols.filter((s) =>
        s.toLowerCase().includes(search.toLowerCase())
      ),
    [symbols, search]
  );

  const paginated = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));

  if (error) return <ErrorState message={error} onRetry={() => window.location.reload()} />;
  if (loading) return <LoadingSpinner text="Loading symbols..." />;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">Symbols</h1>
          <p className="mt-1 text-sm text-text-secondary">
            {filtered.length} of {symbols.length} symbols
          </p>
        </div>
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-tertiary" />
          <input
            type="text"
            placeholder="Search symbols..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(0);
            }}
            className="w-60 rounded-lg border border-border bg-surface py-2 pl-10 pr-4 text-sm text-text-primary placeholder-text-tertiary focus:border-nepse-500 focus:outline-none"
          />
        </div>
      </div>

      <Card>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
          {paginated.map((sym) => (
            <button
              key={sym}
              onClick={() => navigate(`/symbols/${sym}`)}
              className="rounded-lg border border-border bg-surface-secondary px-3 py-3 text-left text-sm font-medium text-text-primary transition-all hover:border-nepse-300 hover:bg-nepse-50 dark:hover:border-nepse-700 dark:hover:bg-nepse-900/20"
            >
              {sym}
            </button>
          ))}
        </div>

        {paginated.length === 0 && (
          <p className="py-12 text-center text-sm text-text-tertiary">
            {search ? 'No symbols match your search' : 'No symbols in database'}
          </p>
        )}

        {totalPages > 1 && (
          <div className="mt-4 flex items-center justify-center gap-2 border-t border-border pt-4">
            <button
              disabled={page === 0}
              onClick={() => setPage(page - 1)}
              className="rounded-lg px-3 py-1.5 text-sm font-medium text-text-secondary transition-colors hover:bg-surface-tertiary disabled:opacity-40"
            >
              Previous
            </button>
            <span className="text-sm text-text-tertiary">
              Page {page + 1} of {totalPages}
            </span>
            <button
              disabled={page >= totalPages - 1}
              onClick={() => setPage(page + 1)}
              className="rounded-lg px-3 py-1.5 text-sm font-medium text-text-secondary transition-colors hover:bg-surface-tertiary disabled:opacity-40"
            >
              Next
            </button>
          </div>
        )}
      </Card>
    </div>
  );
}
