import { useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';
import { decisionApi, type DecisionBoard, type OwnedAdvice } from '../../api/decisions';

export function PositionPlanForm({ holding, board, onClose, onSaved }: { holding: OwnedAdvice; board: DecisionBoard; onClose: () => void; onSaved: (board: DecisionBoard) => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => { if (ref.current?.showModal) ref.current.showModal(); else ref.current?.setAttribute('open', ''); }, []);
  return <dialog ref={ref} className="trade-dialog" aria-labelledby="plan-title" onCancel={onClose}>
    <div className="trade-title"><h2 id="plan-title">{holding.symbol} · Exit plan</h2><button aria-label="Close exit plan" onClick={onClose}><X size={20} /></button></div>
    <p className="trade-subtitle">Confirm the shares you already own and choose fixed exit levels. This updates your plan without adding a purchase or changing cash.</p>
    <form onSubmit={async event => {
      event.preventDefault(); const data = new FormData(event.currentTarget); setSaving(true); setError('');
      try {
        onSaved(await decisionApi.plan(holding.symbol, { quantity: Number(data.get('quantity')), stop: Number(data.get('stop')), target: Number(data.get('target')),
          ...(data.get('cost') ? { average_cost: Number(data.get('cost')) } : {}), ...(data.get('date') ? { bought_on: String(data.get('date')) } : {}),
        })); onClose();
      } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
      finally { setSaving(false); }
    }}>
      <label>Current shares<input name="quantity" type="number" min="1" defaultValue={holding.quantity} required autoFocus /></label>
      <label>Average cost per share, including buy fees (optional)<input name="cost" type="number" min="0.01" step="any" defaultValue={holding.average_cost ?? ''} placeholder="Your broker's WACC" /></label>
      <label>Purchase date (optional)<input name="date" type="date" max={board.requested_date} defaultValue={holding.bought_on ?? ''} /></label>
      <div className="trade-grid"><label>Stop loss<input name="stop" type="number" step="0.01" min="0.01" defaultValue={holding.stop ?? (holding.reference_price ? (holding.reference_price * .95).toFixed(2) : '')} required /></label><label>Take profit<input name="target" type="number" step="0.01" min="0.01" defaultValue={holding.target ?? (holding.reference_price ? (holding.reference_price * 1.1).toFixed(2) : '')} required /></label></div>
      <p className="trade-note">Suggested starting levels use the current quote. Change them to your plan. Unknown cost stays unknown until you enter your WACC.</p>
      {error && <p role="alert" className="decision-error">{error}</p>}
      <button className="decision-primary" disabled={saving}>{saving ? 'Saving…' : 'Save exit plan'}</button>
    </form>
  </dialog>;
}
