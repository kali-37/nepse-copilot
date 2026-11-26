import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { researchApi, type FinancialCoverage } from '../../api/research';
import { Badge } from '../ui/Badge';

const statusText = {
  matched_official_excerpt: 'Matched official evidence',
  stale: 'Stale evidence',
  conflict: 'Conflicting values',
  attested_only: 'Attested only',
  unverified: 'Unverified',
};

export function FinancialCoveragePanel() {
  const [open, setOpen] = useState(false);
  const [coverage, setCoverage] = useState<FinancialCoverage | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    const request = new AbortController();
    setError(null);
    void researchApi.financialEvidence(request.signal).then(result => {
      if (!request.signal.aborted) setCoverage(result);
    }).catch(error => {
      if (!request.signal.aborted) setError(error instanceof Error ? error.message : String(error));
    });
    return () => request.abort();
  }, [open]);

  return (
    <details className="rounded-xl border border-border bg-surface p-5" onToggle={event => setOpen(event.currentTarget.open)}>
      <summary className="cursor-pointer text-base font-semibold text-text-primary">Financial evidence coverage</summary>
      {open && (
        <div className="mt-4 space-y-4">
          {error && <p className="rounded-lg border border-negative p-3 text-sm text-negative" role="alert">{error}</p>}
          {!coverage && !error && <p className="text-sm text-text-secondary" role="status">Reading local coverage…</p>}
          {coverage && (
            <>
              <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3 sm:gap-4">
                <div className="rounded-lg bg-surface-secondary p-3">
                  <dt className="text-xs text-text-secondary">Symbols with provider snapshots</dt>
                  <dd className="mt-1 font-mono text-lg font-semibold">{coverage.provider_symbols.toLocaleString()}</dd>
                </div>
                <div className="rounded-lg bg-surface-secondary p-3">
                  <dt className="text-xs text-text-secondary">Symbols with current matched official evidence</dt>
                  <dd className="mt-1 font-mono text-lg font-semibold">{coverage.matched_symbols.toLocaleString()}</dd>
                </div>
                <div className="col-span-2 rounded-lg bg-surface-secondary p-3 sm:col-span-1">
                  <dt className="text-xs text-text-secondary">Symbols passing all required verified checks</dt>
                  <dd className="mt-1 font-mono text-lg font-semibold">{coverage.complete_symbols.toLocaleString()}</dd>
                </div>
              </dl>
              <p className="text-sm text-text-secondary">Matched coverage counts symbols with at least one confirmed issuer or regulator value. Open a symbol to see missing checks and source documents.</p>
              {coverage.symbols.length ? (
                <ul className="max-h-80 divide-y divide-border overflow-y-auto rounded-lg border border-border" tabIndex={0} aria-label="Symbols with official evidence">
                  {coverage.symbols.map(row => (
                    <li className="flex flex-wrap items-center gap-x-3 gap-y-2 p-3 text-sm" key={row.symbol}>
                      <Link className="font-mono font-semibold text-text-primary underline underline-offset-2" to={`/symbols/${encodeURIComponent(row.symbol)}`}>
                        {row.symbol}
                      </Link>
                      <span className="text-xs text-text-secondary">
                        {row.period_basis?.replaceAll('_', ' ')}
                        {row.period_end && <> <time dateTime={row.period_end}>{row.period_end}</time></>}
                      </span>
                      <Badge text={statusText[row.status]} variant={row.status === 'matched_official_excerpt' ? 'info' : 'warning'} />
                      {row.status === 'matched_official_excerpt' && <span className="text-xs text-text-secondary">{row.metrics.length} matched {row.metrics.length === 1 ? 'value' : 'values'}</span>}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="rounded-lg bg-surface-secondary p-3 text-sm text-text-secondary">No official evidence is stored yet.</p>
              )}
            </>
          )}
        </div>
      )}
    </details>
  );
}
