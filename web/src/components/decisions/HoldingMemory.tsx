import type { OwnedAdvice } from '../../api/decisions';
import { money } from './format';

export function HoldingMemory({ holding: p }: { holding: OwnedAdvice }) {
  const original = p.original_plan;
  const change = p.advice_history?.find(e => e.plan_key === p.plan_key && e.previous_action && e.previous_action !== e.action);
  return <div className="holding-memory">
    <p><strong>{p.holding_horizon ?? (p.horizon_days <= 3 ? 'Daily' : p.horizon_days <= 22 ? 'Monthly' : 'Long-term')} plan · {p.horizon_days} trading sessions</strong>{p.review_on && <span> · Review {p.review_on}</span>}</p>
    {change && <p className="advice-change">Changed {change.previous_action?.toUpperCase()} → {change.action.toUpperCase()} on {change.market_date}: {change.reason}</p>}
    <details><summary>Original buy reason & past advice</summary>
      {original ? <><p>Plan opened {original.opened_on ?? 'date unknown'} · Entry NPR {money(original.purchase_price)}{original.confidence && ` · ${Math.round(original.confidence.value * 100)}% entry confidence`}</p><p>{original.confidence?.basis}</p><ul>{original.rationale.map(reason => <li key={reason}>{reason}</li>)}</ul>{original.origin && <p>Recommendation {original.origin.requested_date} · Market quote {original.origin.market_date}</p>}<p>Original stop NPR {money(original.stop)} · Original target NPR {money(original.target)}. Current saved exits are shown in your exit plan.</p></> : <p>Your original purchase rationale was not recorded. Set an exit plan to confirm the dates and levels.</p>}
      {!!p.plan_revision && <p>You explicitly reviewed this exit plan on {p.plan_reviewed_on}.</p>}
      {!!p.advice_history?.length && <ol className="advice-timeline">{p.advice_history.map((event,i) => <li key={`${event.evaluated_at}-${i}`}><strong>{event.market_date ?? 'No quote'} · {event.previous_action ? `${event.previous_action.toUpperCase()} → ` : ''}{event.action.toUpperCase()}</strong>{event.plan_key !== p.plan_key && <span> · Previous exit plan</span>}<p>{event.reason}</p></li>)}</ol>}
    </details>
  </div>;
}
