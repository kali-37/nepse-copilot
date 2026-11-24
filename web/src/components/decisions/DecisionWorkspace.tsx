import { useCallback, useEffect, useRef, useState } from 'react';
import { ArrowDownRight, ArrowUpRight, Check, ChevronDown, CircleHelp, RefreshCw, Plus, Wallet, ShieldCheck } from 'lucide-react';
import { Link } from 'react-router-dom';
import { api } from '../../api/client';
import { decisionApi, type DecisionBoard } from '../../api/decisions';
import { useJob } from '../../hooks/useJob';
import { IdeaCard, Score } from './IdeaCard';
import { money } from './format';
import { PositionPlanForm } from './PositionPlanForm';
import type { OwnedAdvice } from '../../api/decisions';
import { Capabilities } from './Capabilities';
import { HoldingMemory } from './HoldingMemory';
import { InvestmentCard } from './InvestmentCard';
import { TradeForm, type RecordIntent } from './TradeForm';
import './decisions.css';

export function DecisionWorkspace({ title = 'Your next move.', initialTab = 'day', holdingsFocus = false }: { title?: string; initialTab?: 'day' | 'month'; holdingsFocus?: boolean }) {
  const [board, setBoard] = useState<DecisionBoard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState(initialTab);
  const [intent, setIntent] = useState<RecordIntent | null>(null);
  const [planHolding, setPlanHolding] = useState<OwnedAdvice | null>(null);
  const [editingCash, setEditingCash] = useState(false);
  const [cashSaving, setCashSaving] = useState(false);
  const { job, error: jobError, starting, start, attach } = useJob();
  const loadedJob = useRef<string | null>(null);
  const loadRevision = useRef(0);
  const heldRef = useRef<HTMLElement>(null);
  const acceptBoard = useCallback((next: DecisionBoard) => {
    ++loadRevision.current;
    setBoard(next);
    setError(null);
  }, []);
  const load = useCallback(async () => {
    const revision = ++loadRevision.current;
    setError(null);
    try {
      const next = await decisionApi.board();
      if (revision === loadRevision.current) { setBoard(next); setError(null); }
    }
    catch (e) { if (revision === loadRevision.current) setError(e instanceof Error ? e.message : String(e)); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    let active = true;
    void api.jobs().then(list => { if (active && list.running) attach(list.running); }).catch(() => {});
    return () => { active = false; };
  }, [attach]);
  useEffect(() => {
    if (job?.status === 'done' && loadedJob.current !== job.id) {
      loadedJob.current = job.id;
      void load();
    }
  }, [job, load]);
  useEffect(() => { if (holdingsFocus && board) heldRef.current?.scrollIntoView?.({ block: 'start' }); }, [holdingsFocus, board]);
  const busy = starting || job?.status === 'queued' || job?.status === 'running';
  const stage = job?.stages.find(s => s.status === 'running');
  const exitCount = board?.holdings.filter(p => p.action === 'sell').length ?? 0;
  return <div className="decision-workspace">
    <div className="decision-eyebrow"><span className="eyebrow-line" /> A LITTLE CLARITY. A BETTER DECISION.</div>
    <div className="decision-hero"><div><h1>{title}</h1><p>Know what to buy, what to hold, and when to step away.</p></div><button className="decision-primary refresh-button" onClick={() => void start('refresh-today')} disabled={busy}><RefreshCw size={17} className={busy ? 'animate-spin' : ''} />{busy ? 'Refreshing…' : 'Refresh today'}</button></div>
    <div className="decision-dateline"><span className={`status-dot ${board?.stale ? 'warning' : ''}`} /><span>{board ? board.stale ? 'Market data needs a refresh' : board.session === 'closed' ? 'Market closed · using the last published session' : 'Latest published market data' : 'Reading your market evidence…'}</span>{board?.market_date && <strong>{board.market_date}</strong>}</div>
    {(error || jobError || job?.error) && <div className="decision-error" role="alert">{error || jobError || job?.error}{error && <button className="decision-secondary" onClick={() => void load()}>Retry</button>}</div>}
    {busy && <div className="refresh-progress" role="status"><RefreshCw size={16} className="animate-spin" /><div><strong>{stage?.label ?? 'Starting refresh'}</strong><p>{stage?.detail || 'Downloading public data, then updating charts and your advice.'}</p></div>{stage && stage.total > 0 && <span>{stage.current} / {stage.total}</span>}</div>}
    {!busy && job?.status === 'done' && <p className="refresh-complete" role="status"><Check size={15} /> Refresh complete. Source status and market dates are shown below.</p>}
    {!board && !error && <div className="decision-loading" role="status">Preparing your buy ideas and holdings…</div>}
    {board && <>
      <div className="decision-overview">
        <div className="cash-overview"><span className="overview-label"><Wallet size={15} /> Cash for new purchases</span><div><strong>NPR {money(board.available_cash)}</strong><button onClick={() => setEditingCash(!editingCash)} aria-expanded={editingCash}>{editingCash ? 'Cancel' : 'Edit'}</button></div>{editingCash && <form className="cash-form" onSubmit={async e => { e.preventDefault(); setCashSaving(true); try { acceptBoard(await decisionApi.cash(Number(new FormData(e.currentTarget).get('cash')))); setEditingCash(false); } catch (e) { setError(e instanceof Error ? e.message : String(e)); } finally { setCashSaving(false); } }}><label className="sr-only" htmlFor="available-cash">Available cash (NPR)</label><input id="available-cash" name="cash" type="number" min="0" step="0.01" required defaultValue={board.available_cash} /><button disabled={cashSaving}>{cashSaving ? 'Saving…' : 'Save'}</button></form>}<small>Excludes the money already invested.</small></div>
        <div><span className="overview-label">Planned purchases</span><strong>NPR {money(board.planned_outlay)}</strong><small>NPR {money(board.cash_reserved)} kept in reserve</small></div>
        <div><span className="overview-label">Your holdings</span><strong>{board.holdings.length}<span> stocks</span></strong><small>{exitCount ? `${exitCount} holding${exitCount > 1 ? 's' : ''} reached an exit condition` : 'Review your hold and exit plans below'}</small></div>
      </div>
      <section className="buy-section" aria-labelledby="buy-heading"><div className="decision-section-header"><div><span className="section-kicker">PUT YOUR CASH TO WORK</span><h2 id="buy-heading">What to buy</h2></div><div className="horizon-switch" role="tablist" aria-label="Buying horizon"><button role="tab" id="day-tab" aria-selected={tab === 'day'} aria-controls="buy-panel" onClick={() => setTab('day')}>Daily</button><button role="tab" id="month-tab" aria-selected={tab === 'month'} aria-controls="buy-panel" onClick={() => setTab('month')}>Monthly</button></div></div>
        <p className="section-subtitle">{tab === 'day' ? 'Short-term ideas for the next 3 trading sessions. Allow T+2 settlement before selling.' : 'Patient ideas for roughly one month · 22 trading sessions.'} {board.earliest_entry_date ? ` Earliest planned entry ${board.earliest_entry_date}.` : ''} Prices from {board.market_date ?? 'stored data'}.</p>
        <div id="buy-panel" role="tabpanel" aria-labelledby={`${tab}-tab`} className="idea-grid">{board.buys[tab].map((idea, i) => <IdeaCard key={idea.symbol} idea={idea} rank={i + 1} onBuy={idea => setIntent({ side: 'buy', idea })} />)}</div>
        {board.buys[tab].length === 0 && <div className="decision-empty"><ShieldCheck size={28} /><h3>{board.stale ? 'Fresh data comes first.' : 'Keeping your cash is a decision, too.'}</h3><p>{board.stale ? 'Refresh the market before considering a new purchase.' : board.available_cash === 0 ? 'Add your available cash to size new purchases.' : 'No affordable idea passes both chart/history and fundamental checks for this horizon.'}</p></div>}
      </section>
      {!!board.recent_exits?.length && <p className="section-subtitle">Recently sold: {board.recent_exits.map(p => `${p.symbol} · reconsider after ${p.reconsider_after}`).join('; ')}. New buys wait for a fresh setup.</p>}
      <section className="investments-section" aria-labelledby="investments-heading"><div className="decision-section-header"><div><span className="section-kicker">THINK IN YEARS</span><h2 id="investments-heading">Lower-risk investments</h2></div><span className="section-kicker">RESEARCH WATCHLIST</span></div><p className="section-subtitle">Profitable companies with reasonable valuations and lower historical losses. Stocks can lose capital; they have different risks from bank deposits. Historical growth is not a promised return.</p><div className="idea-grid">{board.investments?.candidates.map(idea => <InvestmentCard key={idea.symbol} idea={idea} onBuy={investment => setIntent({ side: 'buy', investment })} />)}</div>{!board.investments?.candidates.length && <div className="decision-empty"><ShieldCheck size={25} /><h3>No stock currently passes this screen.</h3><p>Recent profitability/valuation data and at least one year of usable history are required. Refresh sources to improve coverage.</p></div>}<details className="source-details"><summary>Investment criteria & data coverage</summary><p>{board.investments?.criteria}</p><p>{board.investments ? `${board.investments.checked_fundamentals} companies have stored fundamentals; ${board.investments.fundamentals_missing} have no snapshot.` : 'No fundamentals screening available yet.'} Missing or stale financial data never counts as evidence of safety.</p></details></section>
      <section ref={heldRef} className="holdings-section" aria-labelledby="holdings-heading"><div className="decision-section-header"><div><span className="section-kicker">LOOK AFTER WHAT YOU OWN</span><h2 id="holdings-heading">What to sell or hold</h2></div><button className="decision-secondary" onClick={() => setIntent({ side: 'buy' })}><Plus size={15} /> Record a purchase</button></div><p className="section-subtitle">Your original holding plan and buy reasons are kept. A new shortlist does not override your saved exits.</p>
        {board.holdings.length === 0 ? <div className="holding-empty"><Wallet size={25} /><div><h3>Your holdings start here.</h3><p>Record a purchase or <Link to="/meroshare">import from MeroShare</Link> to get a personal exit plan.</p></div></div> : <div className="holdings-list">{board.holdings.map(p => <article className={`holding-row holding-${p.action}`} key={p.symbol}>
          <div className="holding-symbol"><span className="holding-monogram">{p.symbol.slice(0, 2)}</span><div><Link to={`/symbols/${p.symbol}`}>{p.symbol}<ArrowUpRight size={13} /></Link><small>{p.quantity} shares · {p.source === 'tracked' ? 'Recorded by you' : p.source === 'paper' ? 'Paper holding' : 'MeroShare'}</small></div></div>
          <div className="holding-action"><span className={`action-pill ${p.action}`}>{p.action === 'sell' ? <ArrowDownRight size={13} /> : <ShieldCheck size={13} />}{p.action === 'sell' ? p.settled === false ? 'Exit after settlement' : 'Consider selling' : p.action === 'hold' ? 'Hold' : 'Review'}</span><p>{p.reason}</p>{p.settled === false && <small>Wait for settlement · {p.earliest_sell_date}</small>}{p.settled === null && <small>Purchase date unknown · verify settlement with your broker</small>}</div>
          <div className="holding-price"><strong>NPR {money(p.reference_price)}</strong><small className={p.unrealized_pnl != null && p.unrealized_pnl < 0 ? 'text-negative' : 'text-positive'}>{p.unrealized_pnl == null ? 'Cost basis unknown' : `${p.unrealized_pnl >= 0 ? '+' : '−'} NPR ${money(Math.abs(p.unrealized_pnl))} before sell fees`}</small></div>
          <div className="holding-controls"><Score score={p.confidence} label="holding evidence" emptyLabel={p.action === 'review' ? 'Review needed' : 'Not enough data'} /><button className="decision-secondary" onClick={() => setIntent({ side: 'sell', holding: p })}>I sold</button></div>
          <HoldingMemory holding={p} />
          <details className="holding-details"><summary>Exit plan & evidence <ChevronDown size={13} /></summary><p>Average cost NPR {money(p.average_cost)} · Saved stop NPR {money(p.stop)} · Saved target NPR {money(p.target)} · Quote {p.quote_date ?? 'unavailable'}</p><p>Estimated net PnL if sold at the reference price: NPR {money(p.net_exit_pnl)} after modeled fees and tax.</p><p>{p.confidence.basis}</p><button className="decision-secondary" onClick={() => setPlanHolding(p)}>Set exit plan</button></details>
        </article>)}</div>}
      </section>
      <Capabilities />
      <div className="decision-footnote"><CircleHelp size={17} /><p>{board.confidence_note} Scores use comparable completed historical setups, current indicators, liquidity and source agreement. Daily and monthly ideas share one cash budget. Recording trades never places an order.</p></div>
      <details className="source-details"><summary>{board.coverage.analysable} charts analysed · source & refresh details <ChevronDown size={14} /></summary><p>Requested {board.requested_date} · Published market session {board.market_date ?? 'none'} · Advice generated {new Date(board.generated_at).toLocaleString('en-NP')}</p>{board.refresh ? <><p>{Object.entries(board.refresh.sources).map(([name, count]) => `${name}: ${count} price rows`).join(' · ') || 'No sources returned prices.'}</p>{board.refresh.warnings.length > 0 && <ul>{board.refresh.warnings.map((warning, i) => <li key={`${i}-${warning}`}>{warning}</li>)}</ul>}</> : <p>Built from stored data. Refresh today downloads enabled public sources and rebuilds chart analysis, daily/monthly evidence, company context and your exit advice.</p>}<Link to="/operations">Open detailed operations <ArrowUpRight size={13} /></Link></details>
    </>}
    {planHolding && board && <PositionPlanForm holding={planHolding} board={board} onClose={() => setPlanHolding(null)} onSaved={acceptBoard} />}
    {intent && board && <TradeForm intent={intent} board={board} onClose={() => setIntent(null)} onSaved={acceptBoard} />}
  </div>;
}
