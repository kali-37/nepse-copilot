import { ArrowUpRight, ChevronDown, Plus } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { BuyIdea, EvidenceScore, PricePoint } from '../../api/decisions';

import { money } from './format';

export function Sparkline({ points, symbol }: { points: PricePoint[]; symbol: string }) {
  if (points.length < 2) return <div className="sparkline-empty">Chart history unavailable</div>;
  const prices = points.map(p => p.close);
  const low = Math.min(...prices), range = Math.max(...prices) - low || 1;
  const path = prices.map((p, i) => `${i ? 'L' : 'M'}${(i / (prices.length - 1) * 300).toFixed(2)},${(65 - (p - low) / range * 55).toFixed(2)}`).join(' ');
  return <svg className="decision-sparkline" viewBox="0 0 300 80" role="img" aria-label={`${symbol} closing prices from ${points[0].date} to ${points[points.length - 1].date}`}>
    <path d={`${path} L300,80 L0,80 Z`} fill="currentColor" opacity="0.06" />
    <path d={path} fill="none" stroke="currentColor" strokeWidth="2" vectorEffect="non-scaling-stroke" />
  </svg>;
}

export function Score({ score, label = 'evidence score', emptyLabel = 'Not enough data' }: { score: EvidenceScore; label?: string; emptyLabel?: string }) {
  return <span className="decision-score" title={score.basis}><span className="score-dot" />{score.value > 0 ? `${Math.round(score.value * 100)}% ${label}` : emptyLabel}</span>;
}

export function IdeaCard({ idea, onBuy, rank }: { idea: BuyIdea; onBuy: (idea: BuyIdea) => void; rank: number }) {
  const model = idea.model_estimate;
  const fundamentals = idea.fundamental_report;
  const statementStatus = fundamentals?.verification?.status;
  const support = statementStatus === 'matched_official_excerpt'
    ? fundamentals?.verified_eligibility ? 'Verified checks pass' : 'Official evidence available'
    : statementStatus === 'stale' ? 'Official evidence is stale' : statementStatus ? 'No current matched evidence' : null;
  const estimate = model?.eligible_for_advisory &&
    model.event === 'net_profitable_modeled_trade_given_entry' &&
    model.horizon_days === idea.horizon_days &&
    Number.isFinite(model.probability) && model.probability >= 0 && model.probability <= 1
    ? model
    : null;
  return <article className="idea-card">
    <div className="idea-top"><span className="idea-rank">0{rank}</span><Score score={idea.confidence} /></div>
    <div className="idea-name"><div><Link to={`/symbols/${idea.symbol}`}><h3>{idea.symbol}<ArrowUpRight size={17} /></h3></Link><p>Buy candidate · {idea.horizon_days} trading sessions</p></div><strong>{money(idea.reference_price)}<small>NPR / share</small></strong></div>
    <Sparkline points={idea.chart} symbol={idea.symbol} />
    <div className="entry-zone"><span>Look to buy around</span><strong>NPR {money(idea.entry_low)}–{money(idea.entry_high)}</strong></div>
    <div className="idea-levels"><div><span>Take profit</span><strong className="text-positive">{money(idea.target)}</strong></div><div><span>Stop loss</span><strong>{money(idea.stop)}</strong></div><div><span>Suggested size</span><strong>{idea.quantity} shares</strong></div></div>
    {estimate && (
      <aside className="mt-3 rounded-lg border border-border bg-surface-secondary p-3 text-xs leading-relaxed" aria-label="Trained model estimate">
        <p className="text-text-primary"><strong className="tabular-nums">{(estimate.probability * 100).toFixed(1)}%</strong> estimated chance of a net profit</p>
        <p className="mt-1 text-text-secondary">Model assumes an entry fill on a 100-share trade over {estimate.horizon_days} sessions and includes fees and tax.</p>
      </aside>
    )}
    <p className="fundamental-rating">Fundamentals · {fundamentals?.rating ?? 'unassessed'}{support && ` · ${support}`}</p><div className="visible-buy-reasons"><strong>Why buy {idea.symbol}?</strong><ul>{idea.rationale.map(reason => <li key={reason}>{reason}</li>)}</ul>{idea.confidence.historical_samples != null && <p>{idea.confidence.historical_hits}/{idea.confidence.historical_samples} comparable completed setups were profitable after modeled fees (100-share benchmark).</p>}</div>
    <div className="idea-return"><span>Net gain if target fills</span><strong>+ NPR {money(idea.estimated_net)}</strong></div>
    <button className="decision-secondary buy-record" onClick={() => onBuy(idea)}><Plus size={16} /> I bought this</button>
    <details className="idea-details"><summary>Why this recommendation <ChevronDown size={14} /></summary><p>{idea.confidence.basis}</p><p>RSI {idea.metrics.rsi} · Volume {idea.metrics.volume_ratio}× recent average.</p><p>Estimated outlay NPR {money(idea.outlay)}, modeled round-trip fees NPR {money(idea.estimated_fees)}. Earliest exit after settlement: {idea.earliest_sell_date}. Targets and stops are planned levels; fills may differ.</p>
      {estimate && (
        <div className="mt-3 border-t border-border pt-2">
          <p>Model estimate as of <time dateTime={estimate.as_of}>{estimate.as_of}</time></p>
          <p className="break-all font-mono">Version {estimate.model_id}</p>
          <ul className="list-disc space-y-1 pl-4">{estimate.limitations.map(limit => <li key={limit}>{limit}</li>)}</ul>
          <Link className="mt-2 inline-block underline underline-offset-2" to="/research">See held-out model results</Link>
        </div>
      )}
    </details>
  </article>;
}
