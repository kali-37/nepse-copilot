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

export function Score({ score }: { score: EvidenceScore }) {
  return <span className="decision-score" title={score.basis}><span className="score-dot" />{score.value > 0 ? `${Math.round(score.value * 100)}% confidence` : 'Not enough data'}</span>;
}

export function IdeaCard({ idea, onBuy, rank }: { idea: BuyIdea; onBuy: (idea: BuyIdea) => void; rank: number }) {
  return <article className="idea-card">
    <div className="idea-top"><span className="idea-rank">0{rank}</span><Score score={idea.confidence} /></div>
    <div className="idea-name"><div><Link to={`/symbols/${idea.symbol}`}><h3>{idea.symbol}<ArrowUpRight size={17} /></h3></Link><p>Buy candidate · {idea.horizon_days} trading sessions</p></div><strong>{money(idea.reference_price)}<small>NPR / share</small></strong></div>
    <Sparkline points={idea.chart} symbol={idea.symbol} />
    <div className="entry-zone"><span>Look to buy around</span><strong>NPR {money(idea.entry_low)}–{money(idea.entry_high)}</strong></div>
    <div className="idea-levels"><div><span>Take profit</span><strong className="text-positive">{money(idea.target)}</strong></div><div><span>Stop loss</span><strong>{money(idea.stop)}</strong></div><div><span>Suggested size</span><strong>{idea.quantity} shares</strong></div></div>
    <p className="idea-why">{idea.rationale[0]}. {idea.rationale[2]}.</p>
    <div className="idea-return"><span>Net gain if target fills</span><strong>+ NPR {money(idea.estimated_net)}</strong></div>
    <button className="decision-secondary buy-record" onClick={() => onBuy(idea)}><Plus size={16} /> I bought this</button>
    <details className="idea-details"><summary>Why this recommendation <ChevronDown size={14} /></summary><p>{idea.confidence.basis}</p><ul>{idea.rationale.map(reason => <li key={reason}>{reason}</li>)}</ul><p>RSI {idea.metrics.rsi} · Volume {idea.metrics.volume_ratio}× recent average.</p><p>Estimated outlay NPR {money(idea.outlay)}, modeled round-trip fees NPR {money(idea.estimated_fees)}. Earliest exit after settlement: {idea.earliest_sell_date}. Targets and stops are planned levels; fills may differ.</p></details>
  </article>;
}
