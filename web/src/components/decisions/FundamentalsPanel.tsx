import type { FinancialCheck, FundamentalReport } from '../../api/decisions';
import { Badge } from '../ui/Badge';
import './decisions.css';
import { money } from './format';

const verdicts = {
  pass: { text: 'Pass', variant: 'success' },
  caution: { text: 'Caution', variant: 'warning' },
  fail: { text: 'Fail', variant: 'danger' },
  unknown: { text: 'Unknown', variant: 'default' },
} as const;

const verificationStatus = {
  matched_official_excerpt: { text: 'Matched official evidence', variant: 'info' },
  attested_only: { text: 'Attested only', variant: 'warning' },
  unverified: { text: 'No matched official evidence', variant: 'default' },
  stale: { text: 'Official evidence is stale', variant: 'warning' },
  conflict: { text: 'Conflicting official values', variant: 'danger' },
} as const;

const valuationLabel = {
  verified_annual_eps: 'Quote-based annual P/E',
  verified_annualized_eps: 'Quote-based annualized P/E',
  verified_ttm_eps: 'Quote-based trailing P/E',
  verified_quarterly_eps: 'Indicative price/EPS',
  reported_annualized_eps: 'P/E from reported EPS',
  reported_quarterly_eps: 'Indicative price/EPS',
  unverified_provider_basis: 'Indicative price/EPS',
};

const sourceLabels = { issuer: 'Issuer statement', regulator: 'Regulator disclosure' };

function secureSource(url: string | null | undefined) {
  if (!url) return undefined;
  try {
    const source = new URL(url);
    if (source.protocol === 'https:' && !source.username && !source.password) return source;
  } catch {
    // Show evidence metadata even when a legacy source link is malformed.
  }
  return undefined;
}

function npr(value: number | null | undefined) {
  return value == null ? '—' : `NPR ${money(value)}`;
}

function financialValue({ value, unit }: FinancialCheck) {
  if (value === null) return '—';
  if (unit === 'percent') return `${money(value)}%`;
  if (unit === 'ratio') return `${money(value)}×`;
  if (unit === 'NPR' || unit === 'NPR_per_share') return npr(value);
  return money(value);
}

function EvidenceDetails({ report }: { report: FundamentalReport }) {
  const evidence = report.verification;
  if (!evidence) return null;
  const fund = report.asset_kind === 'mutual_fund';
  const checks = (report.financial_checks ?? []).filter(check =>
    !fund || check.metric === 'nav_per_unit' || check.metric === 'expense_ratio_pct',
  );
  return (
    <section className="my-4 space-y-2 rounded-lg border border-border bg-surface-secondary p-3 sm:p-4" aria-label="Financial verification">
      <div className="flex flex-wrap items-center gap-2">
        <Badge {...verificationStatus[evidence.status]} />
        {evidence.status === 'matched_official_excerpt' && (
          <span className="text-text-secondary">
            {evidence.matched_metrics.length} matched {evidence.matched_metrics.length === 1 ? 'metric' : 'metrics'}
            {evidence.missing_metrics.length > 0 && ` · ${evidence.missing_metrics.length} required ${evidence.missing_metrics.length === 1 ? 'item' : 'items'} missing`}
          </span>
        )}
      </div>
      {evidence.period_end && (
        <p>
          {evidence.period_basis === 'as_of' ? 'As of' : `${evidence.period_basis ?? 'Reporting'} period`}
          {evidence.period_start && <> <time dateTime={evidence.period_start}>{evidence.period_start}</time> to</>}
          {' '}<time dateTime={evidence.period_end}>{evidence.period_end}</time>
          {evidence.period_label && ` · ${evidence.period_label}`}
        </p>
      )}
      {fund && report.verified_nav_per_unit != null && (
        <div className="flex flex-wrap gap-x-6 gap-y-1">
          <p>Matched NAV <strong>{npr(report.verified_nav_per_unit)} per unit</strong></p>
          {report.market_premium_discount_pct != null && (
            <p>Price versus NAV <strong>{money(report.market_premium_discount_pct)}%</strong></p>
          )}
        </div>
      )}
      <details>
        <summary className="font-semibold">Financial checks & sources</summary>
        <div className="mt-3 space-y-3">
          {checks.length > 0 && (
            <div className="divide-y divide-border">
              {checks.map(check => (
                <div className="grid gap-1 py-2 sm:grid-cols-[minmax(0,1fr)_auto] sm:gap-x-4" key={check.metric}>
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <strong className="text-text-primary">{check.label}</strong>
                    <Badge {...verdicts[check.verdict]} />
                    {check.source_kind && <span className="text-xs text-text-secondary">{sourceLabels[check.source_kind]}</span>}
                  </div>
                  <span className="font-mono text-text-primary">{financialValue(check)}</span>
                  <p className="sm:col-span-2">{check.reason}</p>
                </div>
              ))}
            </div>
          )}
          {evidence.source_documents.map(document => {
            const source = secureSource(document.source_url);
            return (
              <div className="border-t border-border pt-3" key={document.evidence_id}>
                {document.source_kind && <p className="mb-1 font-medium text-text-primary">{sourceLabels[document.source_kind]}{document.period_label && ` · ${document.period_label}`}</p>}
                {source ? (
                  <a href={source.href} target="_blank" rel="noreferrer" className="font-medium text-text-primary underline underline-offset-2">
                    Open source document on {source.hostname}
                  </a>
                ) : <strong>Stored source document</strong>}
                <p>
                  Published {document.published_on ?? 'date unavailable'}
                  {' · '}Evidence available <time dateTime={document.available_at}>{document.available_at.slice(0, 10)}</time>
                  {document.verified_at && <> · Matched <time dateTime={document.verified_at}>{document.verified_at.slice(0, 10)}</time></>}
                </p>
                {document.document_sha256 && <p className="text-xs">SHA-256 <code className="break-all">{document.document_sha256}</code></p>}
              </div>
            );
          })}
          <p>{evidence.note}</p>
        </div>
      </details>
    </section>
  );
}

export function FundamentalsPanel({ report }: { report: FundamentalReport }) {
  const fund = report.asset_kind === 'mutual_fund';
  const indicative = report.valuation_basis === 'unverified_provider_basis' ||
    report.valuation_basis === 'reported_quarterly_eps' || report.valuation_basis === 'verified_quarterly_eps';
  const providerSource = secureSource(report.source_url);
  return (
    <div className="fundamentals-panel">
      {fund ? (
        <p><strong>Mutual fund · valuation review needed</strong></p>
      ) : (
        <>
          <p><strong className="capitalize">{report.rating} fundamentals</strong> · Provider snapshot {report.snapshot_date ?? 'unavailable'}</p>
          <div className="fundamental-metrics">
            <div><span>Reported EPS</span><strong>{npr(report.eps)}</strong></div>
            <div><span>Book value per share</span><strong>{npr(report.book_value)}</strong></div>
            <div>
              <span>{report.valuation_basis ? valuationLabel[report.valuation_basis] : 'Quote-based P/E'}</span>
              <strong>{money(indicative ? report.indicative_price_eps : report.current_pe)}</strong>
            </div>
            <div><span>Quote-based price/book</span><strong>{money(report.current_pbv)}</strong></div>
          </div>
        </>
      )}
      <EvidenceDetails report={report} />
      {report.reasons.length > 0 && <ul>{report.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul>}
      {fund ? <p>The stock buying screens exclude this fund.</p> : (
        <p>{report.multiplier === 0
          ? 'The financial assessment currently excludes this stock from new buys.'
          : `The financial assessment retains ${Math.round(report.multiplier * 100)}% of the technical and historical evidence for new buys.`}</p>
      )}
      <details>
        <summary>{fund ? 'Fund data limits' : 'Financial data limits'}</summary>
        <ul>{report.limitations.map(limit => <li key={limit}>{limit}</li>)}</ul>
        <p>
          {report.source} · Snapshot {report.snapshot_date ?? 'unavailable'}
          {report.reporting_period_end && ` · Period ends ${report.reporting_period_end}`}
          {providerSource && <> · <a href={providerSource.href} target="_blank" rel="noreferrer" className="underline underline-offset-2">Provider page</a></>}
        </p>
      </details>
    </div>
  );
}
