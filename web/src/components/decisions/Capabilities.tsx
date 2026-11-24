const strengths = [
  'Cross-checks public prices and preserves the source market date.',
  'Combines chart/history evidence with earnings and valuation checks.',
  'Models Nepal transaction fees and tax; sizes daily/monthly ideas within one cash budget.',
  'Keeps your original buy reasons, holding period and fixed exits, with dated advice changes.',
  'Respects settlement and requires completed-session confirmation for trend exits.',
  'Works offline after ingestion; MeroShare is read-only and orders remain manual.',
];
const limits = [
  'Confidence is evidence strength, not a calibrated probability or guaranteed return.',
  'Public data can be missing, delayed or parsed incorrectly; financial filings are not independently reconciled.',
  'ROE, cash flow, debt, bank bad loans and capital adequacy are not verified.',
  'Historical returns exclude unconfirmed cash dividends; dividend percentage is not a cash yield.',
  'Stops/targets may not fill because of gaps, liquidity, circuit limits or settlement.',
  'One aggregate holding plan per symbol; per-lot tax/settlement and mutual-fund NAV analysis remain limited.',
  'The dashboard is a personal single-user app; shared hosting needs authentication and user isolation.',
];
export function Capabilities() {
  return <details className="app-capabilities"><summary>Application strengths & limitations</summary><div><section><h3>What it does well</h3><ul>{strengths.map(text => <li key={text}>{text}</li>)}</ul></section><section><h3>What still needs care</h3><ul>{limits.map(text => <li key={text}>{text}</li>)}</ul></section></div></details>;
}
