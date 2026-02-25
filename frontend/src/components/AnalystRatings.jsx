import { useState, useEffect } from 'react';

export default function AnalystRatings() {
  const [data, setData] = useState(null);

  useEffect(() => {
    fetch('api/analyst-ratings')
      .then(r => r.json())
      .then(setData)
      .catch(() => {});
  }, []);

  if (!data?.ratings?.length) return null;

  const consensusColor = (c) => {
    if (c === 'STRONG BUY') return 'bg-emerald-700 text-emerald-100';
    if (c === 'BUY') return 'bg-emerald-800/60 text-emerald-300';
    if (c === 'HOLD') return 'bg-yellow-800/50 text-yellow-300';
    return 'bg-red-800/50 text-red-300';
  };

  const net = (data.upgrades_30d || 0) - (data.downgrades_30d || 0);

  return (
    <div className="u-card p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-zinc-200">📊 Analyst Consensus</h3>
        {(data.upgrades_30d > 0 || data.downgrades_30d > 0) && (
          <span className={`text-xs font-mono px-2 py-1 rounded ${net > 0 ? 'bg-zinc-800/40 text-emerald-400/60' : net < 0 ? 'bg-zinc-800/40 text-red-400/60' : 'bg-zinc-800 text-zinc-300'}`}>
            ↑{data.upgrades_30d} ↓{data.downgrades_30d} this month
          </span>
        )}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-zinc-400 border-b border-zinc-800/50">
              <th className="text-left p-2">Ticker</th>
              <th className="text-center p-2">Consensus</th>
              <th className="text-center p-2">Analysts</th>
              <th className="text-right p-2">Target</th>
              <th className="text-right p-2">Upside</th>
              <th className="text-center p-2">Momentum</th>
            </tr>
          </thead>
          <tbody>
            {data.ratings.map(r => (
              <tr key={r.symbol} className="border-b border-zinc-800/50/50">
                <td className="p-2 font-mono text-zinc-200">{r.symbol}</td>
                <td className="p-2 text-center">
                  <span className={`text-xs px-2 py-0.5 rounded font-mono ${consensusColor(r.consensus)}`}>
                    {r.consensus}
                  </span>
                </td>
                <td className="p-2 text-center text-zinc-400">
                  <span className="text-emerald-600">{r.strong_buy + r.buy}</span>
                  /{r.hold}/
                  <span className="text-red-600">{r.sell + r.strong_sell}</span>
                </td>
                <td className="p-2 text-right font-mono text-zinc-300">
                  {r.target_mean ? `$${r.target_mean}` : '—'}
                </td>
                <td className={`p-2 text-right font-mono ${(r.upside_pct || 0) >= 0 ? 'text-emerald-400/60' : 'text-red-400/60'}`}>
                  {r.upside_pct != null ? `${r.upside_pct > 0 ? '+' : ''}${r.upside_pct}%` : '—'}
                </td>
                <td className="p-2 text-center">
                  {r.momentum != null ? (
                    <span className={`font-mono text-xs ${r.momentum > 0 ? 'text-emerald-400/60' : r.momentum < 0 ? 'text-red-400/60' : 'text-zinc-500'}`}>
                      {r.momentum > 0 ? '↑' : r.momentum < 0 ? '↓' : '—'}{Math.abs(r.momentum) > 0 ? ` ${Math.abs(r.momentum)}%` : ''}
                    </span>
                  ) : <span className="text-zinc-500">—</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-zinc-500 mt-3">Buy/Hold/Sell counts • Target = mean analyst price target • Momentum = buy% change vs last month</p>
    </div>
  );
}
