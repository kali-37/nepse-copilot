import { useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';
import { decisionApi, type BuyIdea, type DecisionBoard, type OwnedAdvice } from '../../api/decisions';

export interface RecordIntent { side: 'buy' | 'sell'; idea?: BuyIdea; holding?: OwnedAdvice }
export function TradeForm({ intent, board, onClose, onSaved }: { intent: RecordIntent; board: DecisionBoard; onClose: () => void; onSaved: (board: DecisionBoard) => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const recordId = useRef(crypto.randomUUID());
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const symbol = intent.idea?.symbol ?? intent.holding?.symbol ?? '';
  const quote = intent.idea?.reference_price ?? intent.holding?.reference_price;
  useEffect(() => {
    const dialog = ref.current;
    if (dialog?.showModal) dialog.showModal();
    else dialog?.setAttribute('open', '');
  }, []);
  return <dialog ref={ref} className="trade-dialog" aria-labelledby="trade-title" onCancel={onClose}>
    <div className="trade-title"><h2 id="trade-title">Record a {intent.side === 'buy' ? 'purchase' : 'sale'}</h2><button onClick={onClose} aria-label="Close trade form"><X size={20} /></button></div>
    <p className="trade-subtitle">Enter the trade you already made through your broker. This updates your holdings and cash.</p>
    <form onSubmit={async event => {
      event.preventDefault(); setError(''); setSaving(true);
      const data = new FormData(event.currentTarget);
      try {
        const result = await decisionApi.record({ symbol: String(data.get('symbol')), side: intent.side, record_id: recordId.current,
          quantity: Number(data.get('quantity')), price: Number(data.get('price')),
          business_date: String(data.get('date')), horizon_days: Number(data.get('horizon') ?? 22),
          ...(intent.side === 'buy' && data.get('stop') ? { stop: Number(data.get('stop')) } : {}),
          ...(intent.side === 'buy' && data.get('target') ? { target: Number(data.get('target')) } : {}),
        });
        onSaved(result.board); onClose();
      } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
      finally { setSaving(false); }
    }}>
      <label>Symbol<input name="symbol" defaultValue={symbol} required maxLength={25} readOnly={intent.side === 'sell'} autoFocus /></label>
      <div className="trade-grid"><label>Shares<input name="quantity" type="number" defaultValue={intent.idea?.quantity ?? intent.holding?.quantity ?? 10} min="1" max={intent.side === 'sell' ? intent.holding?.quantity : 100000000} required /></label><label>Actual price (NPR)<input name="price" type="number" step="0.01" defaultValue={quote != null ? quote.toFixed(2) : ''} min="0.01" required /></label></div>
      <label>Trade date<input name="date" type="date" defaultValue={board.market_date ?? board.requested_date} max={board.requested_date} required /></label>
      {intent.side === 'buy' && <><label>Planned holding period<select name="horizon" defaultValue={intent.idea?.horizon_days ?? 22}><option value="3">Daily · 3 trading sessions</option><option value="22">Monthly · 22 trading sessions</option></select></label><div className="trade-grid"><label>Saved stop loss<input name="stop" type="number" step="0.01" min="0.01" defaultValue={intent.idea?.stop ?? ''} placeholder="Automatic from entry" /></label><label>Saved take profit<input name="target" type="number" step="0.01" min="0.01" defaultValue={intent.idea?.target ?? ''} placeholder="Automatic from entry" /></label></div><p className="trade-note">These exit levels stay fixed after you record the purchase.</p></>}
      {error && <p role="alert" className="decision-error">{error}</p>}
      <button className="decision-primary" disabled={saving}>{saving ? 'Saving…' : `Save ${intent.side === 'buy' ? 'purchase' : 'sale'}`}</button>
      <p className="trade-note">No order is placed. Cash updates include modeled Nepal fees.</p>
    </form>
  </dialog>;
}
