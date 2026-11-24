import { ArrowUpRight, Plus } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { InvestmentIdea } from '../../api/decisions';
import { money } from './format';
import { Score, Sparkline } from './IdeaCard';

export function InvestmentCard({ idea, onBuy }: { idea: InvestmentIdea; onBuy: (idea: InvestmentIdea) => void }) {
  return <article className="idea-card investment-card">
    <div className="idea-top"><span className="idea-rank">LONG-TERM WATCHLIST</span><Score score={idea.confidence} label="screen score" /></div>
    <div className="idea-name"><div><Link to={`/symbols/${idea.symbol}`}><h3>{idea.symbol}<ArrowUpRight size={17} /></h3></Link><p>{idea.sector || 'Sector unknown'}</p></div><strong>{money(idea.reference_price)}<small>NPR / share</small></strong></div>
    <Sparkline points={idea.chart} symbol={idea.symbol} />
    <div className="investment-performance"><div><span>Historical price CAGR, net of modeled fees</span><strong>+{idea.historical_net_annual_return.toFixed(2)}% / year</strong></div><div><span>Largest historical decline</span><strong>{idea.max_drawdown.toFixed(1)}%</strong></div></div>
    <p className="investment-date">Measured {idea.history_from}–{idea.history_to}. Future returns can be negative.</p>
    <div className="visible-buy-reasons"><strong>Why it passed the lower-risk screen</strong><ul>{idea.rationale.map(reason => <li key={reason}>{reason}</li>)}</ul></div>
    {idea.declared_dividend_pct != null && <p className="investment-date">Reported dividend: {idea.declared_dividend_pct}% of face value. Cash/bonus split and market cash yield are unverified.</p>}
    {idea.owned ? <a href="#holdings-heading" className="decision-secondary buy-record">Already owned · view your holding plan</a> : idea.reconsider_after ? <p className="investment-date">Recently sold · reconsider after {idea.reconsider_after}. <Link to={`/symbols/${idea.symbol}`}>View past advice</Link></p> : <button className="decision-secondary buy-record" onClick={() => onBuy(idea)}><Plus size={16} /> I bought this investment</button>}
    <details className="idea-details"><summary>Screen limits & caveats</summary><p>{idea.limitations}</p><p>12+ month research horizon. No quantity or purchase budget is reserved by this watchlist. Set your actual cost, quantity and risk levels if you buy.</p></details>
  </article>;
}
