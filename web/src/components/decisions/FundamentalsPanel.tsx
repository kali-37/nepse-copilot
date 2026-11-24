import type { FundamentalReport } from '../../api/decisions';
import './decisions.css';
import { money } from './format';

export function FundamentalsPanel({ report }: { report: FundamentalReport }) {
  return <div className="fundamentals-panel"><p><strong>Fundamental support: {report.rating}</strong> · Snapshot {report.snapshot_date ?? 'missing'}</p><div className="fundamental-metrics"><div><span>Reported EPS</span><strong>NPR {money(report.eps)}</strong></div><div><span>Book value per share</span><strong>NPR {money(report.book_value)}</strong></div><div><span>Quote-based P/E</span><strong>{money(report.current_pe)}</strong></div><div><span>Quote-based price/book</span><strong>{money(report.current_pbv)}</strong></div></div><ul>{report.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul><p>Effect on new buys: {report.multiplier === 0 ? 'Excluded until financial support is established.' : `${Math.round(report.multiplier * 100)}% of technical/historical evidence retained after valuation checks.`}</p><details><summary>Financial data limits</summary><ul>{report.limitations.map(limit => <li key={limit}>{limit}</li>)}</ul><p>Source: {report.source}</p></details></div>;
}
