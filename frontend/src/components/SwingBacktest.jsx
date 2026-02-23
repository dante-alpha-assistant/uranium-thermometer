import { useState, useEffect } from 'react';

export default function SwingBacktest() {
  const [data, setData] = useState(null);
  const [symbol, setSymbol] = useState('URA');
  const [months, setMonths] = useState(12);
  const [loading, setLoading] = useState(false);

  const runBacktest = () => {
    setLoading(true);
    fetch(`api/swing-backtest?symbol=${symbol}&months=${months}`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  };

  useEffect(() => { runBacktest(); }, []);

  const tickers = ['URA', 'CCJ', 'UEC', 'UUUU', 'DNN', 'NXE'];

  return (
    <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-bold text-white">📈 Swing Trading Backtest</h3>
        <div className="flex gap-2 items-center">
          <div className="flex gap-1">
            {tickers.map(t => (
              <button key={t} onClick={() => { setSymbol(t); }}
                className={`px-2 py-0.5 rounded text-xs font-mono ${symbol === t ? 'bg-emerald-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}>
                {t}
              </button>
            ))}
          </div>
          <select value={months} onChange={e => setMonths(+e.target.value)}
            className="bg-gray-800 text-gray-300 text-xs rounded px-2 py-1">
            <option value={6}>6mo</option>
            <option value={12}>12mo</option>
            <option value={18}>18mo</option>
          </select>
          <button onClick={runBacktest} disabled={loading}
            className="bg-emerald-600 text-white text-xs px-3 py-1 rounded hover:bg-emerald-700 disabled:opacity-50">
            {loading ? '...' : 'Run'}
          </button>
        </div>
      </div>

      {data?.results && (() => {
        const r = data.results;
        const alpha = r.total_return_pct - r.buy_and_hold_return_pct;
        return (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-2 mb-4">
              <div className="bg-gray-800/40 rounded-lg p-2 text-center">
                <p className="text-xs text-gray-500">P&L</p>
                <p className={`font-mono font-bold ${r.total_pnl >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  ${r.total_pnl >= 0 ? '+' : ''}{r.total_pnl.toLocaleString()}
                </p>
              </div>
              <div className="bg-gray-800/40 rounded-lg p-2 text-center">
                <p className="text-xs text-gray-500">Return</p>
                <p className={`font-mono font-bold ${r.total_return_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {r.total_return_pct >= 0 ? '+' : ''}{r.total_return_pct}%
                </p>
              </div>
              <div className="bg-gray-800/40 rounded-lg p-2 text-center">
                <p className="text-xs text-gray-500">Win Rate</p>
                <p className={`font-mono font-bold ${r.win_rate >= 50 ? 'text-emerald-400' : 'text-amber-400'}`}>
                  {r.win_rate}%
                </p>
              </div>
              <div className="bg-gray-800/40 rounded-lg p-2 text-center">
                <p className="text-xs text-gray-500">Trades</p>
                <p className="font-mono text-gray-300">{r.total_trades}</p>
              </div>
              <div className="bg-gray-800/40 rounded-lg p-2 text-center">
                <p className="text-xs text-gray-500">Max DD</p>
                <p className="font-mono text-red-400">-{r.max_drawdown_pct}%</p>
              </div>
              <div className="bg-gray-800/40 rounded-lg p-2 text-center">
                <p className="text-xs text-gray-500">vs B&H</p>
                <p className={`font-mono font-bold ${alpha >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {alpha >= 0 ? '+' : ''}{alpha.toFixed(1)}%
                </p>
              </div>
            </div>

            {/* Equity curve mini chart */}
            {data.equity_curve?.length > 2 && (() => {
              const eq = data.equity_curve;
              const vals = eq.map(e => e.equity);
              const min = Math.min(...vals) * 0.98;
              const max = Math.max(...vals) * 1.02;
              const range = max - min || 1;
              const w = 600, h = 80;
              const pts = vals.map((v, i) => `${(i / (vals.length - 1)) * w},${h - ((v - min) / range) * h}`).join(' ');
              const color = vals[vals.length - 1] >= vals[0] ? '#10b981' : '#ef4444';
              return (
                <div className="mb-3">
                  <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-20">
                    <polyline points={pts} fill="none" stroke={color} strokeWidth="2" />
                    <line x1="0" y1={h - ((r.starting_capital - min) / range) * h} x2={w} y2={h - ((r.starting_capital - min) / range) * h}
                      stroke="#374151" strokeWidth="1" strokeDasharray="4" />
                  </svg>
                  <div className="flex justify-between text-xs text-gray-600">
                    <span>{eq[0]?.date}</span>
                    <span>{eq[eq.length - 1]?.date}</span>
                  </div>
                </div>
              );
            })()}

            {/* Trade log */}
            {data.trades?.length > 0 && (
              <div className="overflow-x-auto max-h-40 overflow-y-auto">
                <table className="w-full text-xs">
                  <thead className="sticky top-0 bg-gray-900">
                    <tr className="text-gray-500 border-b border-gray-800">
                      <th className="text-left p-1">Date</th>
                      <th className="text-center p-1">Action</th>
                      <th className="text-right p-1">Price</th>
                      <th className="text-right p-1">Score</th>
                      <th className="text-right p-1">P&L</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.trades.map((t, i) => (
                      <tr key={i} className="border-b border-gray-800/50">
                        <td className="p-1 font-mono text-gray-500">{t.date}</td>
                        <td className="p-1 text-center">
                          <span className={`text-xs px-1.5 py-0.5 rounded ${
                            t.action === 'TAKE_PROFIT' ? 'bg-emerald-900/40 text-emerald-400' :
                            t.action === 'STOP_LOSS' ? 'bg-red-900/40 text-red-400' :
                            t.action === 'BUY' ? 'bg-blue-900/40 text-blue-400' :
                            'bg-gray-800 text-gray-400'
                          }`}>{t.action}</span>
                        </td>
                        <td className="p-1 text-right font-mono text-gray-400">${t.price}</td>
                        <td className="p-1 text-right font-mono text-gray-500">{t.score}</td>
                        <td className={`p-1 text-right font-mono ${(t.pnl_pct || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                          {t.pnl_pct != null ? `${t.pnl_pct >= 0 ? '+' : ''}${t.pnl_pct}%` : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <p className="text-xs text-gray-600 mt-2">
              Buy & hold: {r.buy_and_hold_return_pct >= 0 ? '+' : ''}{r.buy_and_hold_return_pct}% • 
              Entry ≥{data.rules?.entry_score} • TP +{data.rules?.take_profit_pct}% • SL -{data.rules?.stop_loss_pct}%
            </p>
          </>
        );
      })()}
    </div>
  );
}
