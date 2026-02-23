import { useState, useEffect } from 'react';

export default function SwingOptimize() {
  const [data, setData] = useState(null);
  const [symbol, setSymbol] = useState('URA');
  const [loading, setLoading] = useState(false);

  const run = () => {
    setLoading(true);
    fetch(`api/swing-optimize?symbol=${symbol}&months=12`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  };

  const tickers = ['URA', 'CCJ', 'UEC', 'UUUU', 'DNN', 'NXE'];

  const cellColor = (v) => {
    if (v >= 10) return 'bg-emerald-600 text-white';
    if (v >= 5) return 'bg-emerald-800 text-emerald-200';
    if (v >= 0) return 'bg-emerald-900/40 text-emerald-400';
    if (v >= -5) return 'bg-red-900/30 text-red-400';
    return 'bg-red-900/60 text-red-300';
  };

  return (
    <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-bold text-white">🔬 Parameter Optimization</h3>
        <div className="flex gap-2 items-center">
          <div className="flex gap-1">
            {tickers.map(t => (
              <button key={t} onClick={() => setSymbol(t)}
                className={`px-2 py-0.5 rounded text-xs font-mono ${symbol === t ? 'bg-emerald-600 text-white' : 'bg-gray-800 text-gray-400'}`}>
                {t}
              </button>
            ))}
          </div>
          <button onClick={run} disabled={loading}
            className="bg-emerald-600 text-white text-xs px-3 py-1 rounded hover:bg-emerald-700 disabled:opacity-50">
            {loading ? 'Running 30 combos...' : 'Optimize'}
          </button>
        </div>
      </div>

      {!data && !loading && <p className="text-xs text-gray-600">Click Optimize to run parameter sweep (30 TP×SL combinations)</p>}

      {data && (
        <>
          <div className="flex gap-4 mb-3 text-xs">
            <span className="text-gray-500">Best: <span className="text-emerald-400 font-mono">TP +{data.best.tp}% / SL -{data.best.sl}%</span> → <span className="font-bold text-emerald-400">{data.best.pnl >= 0 ? '+' : ''}{data.best.pnl.toFixed(1)}%</span> ({data.best.win_rate}% win, {data.best.trades} trades)</span>
            <span className="text-gray-500">B&H: <span className="font-mono text-gray-400">{data.buy_and_hold_pct >= 0 ? '+' : ''}{data.buy_and_hold_pct}%</span></span>
          </div>

          <div className="overflow-x-auto">
            <table className="text-xs">
              <thead>
                <tr>
                  <th className="p-1 text-gray-500 text-left">TP↓ SL→</th>
                  {data.sl_range.map(sl => (
                    <th key={sl} className="p-1 text-gray-500 text-center font-mono">-{sl}%</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.tp_range.map(tp => (
                  <tr key={tp}>
                    <td className="p-1 text-gray-500 font-mono">+{tp}%</td>
                    {data.sl_range.map(sl => {
                      const cell = data.heatmap.find(h => h.tp === tp && h.sl === sl);
                      const v = cell?.return_pct || 0;
                      const isBest = tp === data.best.tp && sl === data.best.sl;
                      return (
                        <td key={sl} className={`p-1 text-center font-mono rounded ${cellColor(v)} ${isBest ? 'ring-2 ring-yellow-400' : ''}`}
                          title={`${cell?.trades} trades, ${cell?.win_rate}% win, DD -${cell?.max_dd}%`}>
                          {v >= 0 ? '+' : ''}{v.toFixed(1)}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-gray-600 mt-2">Return % by TP/SL combination • 12mo • Entry score ≥55 • Hover for details • 🟡 = best combo</p>
        </>
      )}
    </div>
  );
}
