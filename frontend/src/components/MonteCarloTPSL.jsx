import { useState } from 'react';

const TICKERS = ['URA', 'CCJ', 'UEC', 'UUUU', 'DNN', 'NXE', 'OKLO', 'LEU', 'KAP.IL', 'PDN.AX', 'U-UN.TO'];

export default function MonteCarloTPSL() {
  const [sym, setSym] = useState('URA');
  const [tp, setTp] = useState('25');
  const [sl, setSl] = useState('15');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const run = async () => {
    setLoading(true);
    try {
      const r = await fetch(`api/monte-carlo-tpsl/${sym}?tp_pct=${tp}&sl_pct=${sl}`);
      setData(await r.json());
    } catch {}
    setLoading(false);
  };

  const sigStyle = { FAVORABLE: 'bg-zinc-800/40 text-emerald-400/60', UNFAVORABLE: 'bg-zinc-800/40 text-red-400/60', NEUTRAL: 'bg-zinc-800 text-zinc-300' };

  return (
    <div className="u-card p-6">
      <h3 className="text-sm font-semibold text-zinc-200 mb-1">🎲 TP/SL Probability Engine</h3>
      <p className="text-xs text-zinc-500 mb-4">5,000 Monte Carlo simulations — what are the odds?</p>

      <div className="flex flex-wrap gap-2 mb-4">
        <select value={sym} onChange={e => setSym(e.target.value)}
          className="bg-zinc-800 text-zinc-200 text-xs rounded px-2 py-1.5">
          {TICKERS.map(t => <option key={t} value={t}>{t}</option>)}
        </select>
        <div className="flex items-center gap-1">
          <span className="text-xs text-emerald-400">TP</span>
          <input type="number" value={tp} onChange={e => setTp(e.target.value)}
            className="bg-zinc-800 text-zinc-200 text-xs rounded px-2 py-1.5 w-14" />
          <span className="text-xs text-zinc-400">%</span>
        </div>
        <div className="flex items-center gap-1">
          <span className="text-xs text-red-400">SL</span>
          <input type="number" value={sl} onChange={e => setSl(e.target.value)}
            className="bg-zinc-800 text-zinc-200 text-xs rounded px-2 py-1.5 w-14" />
          <span className="text-xs text-zinc-400">%</span>
        </div>
        <button onClick={run} disabled={loading}
          className="bg-indigo-600 text-zinc-100 text-xs px-4 py-1.5 rounded hover:bg-indigo-700 disabled:opacity-50">
          {loading ? 'Running...' : 'Simulate'}
        </button>
      </div>

      {data && (
        <>
          <div className="flex items-center justify-between mb-3">
            <span className="font-mono text-sm text-zinc-200">{data.symbol} @ ${data.current_price}</span>
            <span className={`text-xs font-mono px-2 py-1 rounded ${sigStyle[data.signal] || ''}`}>{data.signal}</span>
          </div>

          {/* TP vs SL probability bar */}
          <div className="mb-4">
            <div className="flex h-8 rounded-lg overflow-hidden">
              <div className="bg-emerald-600 flex items-center justify-center" style={{ width: `${data.tp_probability}%` }}>
                <span className="text-xs text-zinc-100 font-bold">{data.tp_probability}%</span>
              </div>
              {data.neither_pct > 5 && (
                <div className="bg-gray-700 flex items-center justify-center" style={{ width: `${data.neither_pct}%` }}>
                  <span className="text-xs text-zinc-300">{data.neither_pct}%</span>
                </div>
              )}
              <div className="bg-red-600 flex items-center justify-center" style={{ width: `${data.sl_probability}%` }}>
                <span className="text-xs text-zinc-100 font-bold">{data.sl_probability}%</span>
              </div>
            </div>
            <div className="flex justify-between text-xs mt-1">
              <span className="text-emerald-400">TP ${data.tp_price}</span>
              <span className="text-red-400">SL ${data.sl_price}</span>
            </div>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            <div className="bg-zinc-800/30 rounded-lg p-2 text-center">
              <p className="text-xs text-zinc-400">Median to TP</p>
              <p className="font-mono text-emerald-400 font-bold">{data.median_days_to_tp ?? '—'}d</p>
            </div>
            <div className="bg-zinc-800/30 rounded-lg p-2 text-center">
              <p className="text-xs text-zinc-400">Median to SL</p>
              <p className="font-mono text-red-400 font-bold">{data.median_days_to_sl ?? '—'}d</p>
            </div>
            <div className="bg-zinc-800/30 rounded-lg p-2 text-center">
              <p className="text-xs text-zinc-400">Expected P&L</p>
              <p className={`font-mono font-bold ${data.expected_pnl_pct >= 0 ? 'text-emerald-400/60' : 'text-red-400/60'}`}>
                {data.expected_pnl_pct > 0 ? '+' : ''}{data.expected_pnl_pct}%
              </p>
            </div>
            <div className="bg-zinc-800/30 rounded-lg p-2 text-center">
              <p className="text-xs text-zinc-400">Annual Vol</p>
              <p className="font-mono text-amber-400 font-bold">{data.annualized_vol}%</p>
            </div>
          </div>

          <p className="text-xs text-zinc-500 mt-3">
            "If you buy {data.symbol} at ${data.current_price} with +{data.tp_pct}% TP and -{data.sl_pct}% SL:
            {data.tp_probability}% chance of hitting TP first{data.median_days_to_tp ? ` (median ${data.median_days_to_tp} days)` : ''}.
            Expected P&L: {data.expected_pnl_pct > 0 ? '+' : ''}{data.expected_pnl_pct}%."
          </p>
        </>
      )}
    </div>
  );
}
