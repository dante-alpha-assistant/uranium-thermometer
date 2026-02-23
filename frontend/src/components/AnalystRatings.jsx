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
    <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-bold text-white">📊 Analyst Consensus</h3>
        {(data.upgrades_30d > 0 || data.downgrades_30d > 0) && (
          <span className={`text-xs font-mono px-2 py-1 rounded ${net > 0 ? 'bg-emerald-900/40 text-emerald-400' : net < 0 ? 'bg-red-900/40 text-red-400' : 'bg-gray-800 text-gray-400'}`}>
            ↑{data.upgrades_30d} ↓{data.downgrades_30d} this month
          </span>
        )}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-gray-500 border-b border-gray-800">
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
              <tr key={r.symbol} className="border-b border-gray-800/50">
                <td className="p-2 font-mono text-gray-300">{r.symbol}</td>
                <td className="p-2 text-center">
                  <span className={`text-xs px-2 py-0.5 rounded font-mono ${consensusColor(r.consensus)}`}>
                    {r.consensus}
                  </span>
                </td>
                <td className="p-2 text-center text-gray-500">
                  <span className="text-emerald-600">{r.strong_buy + r.buy}</span>
                  /{r.hold}/
                  <span className="text-red-600">{r.sell + r.strong_sell}</span>
                </td>
                <td className="p-2 text-right font-mono text-gray-400">
                  {r.target_mean ? `$${r.target_mean}` : '—'}
                </td>
                <td className={`p-2 text-right font-mono ${(r.upside_pct || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {r.upside_pct != null ? `${r.upside_pct > 0 ? '+' : ''}${r.upside_pct}%` : '—'}
                </td>
                <td className="p-2 text-center">
                  {r.momentum != null ? (
                    <span className={`font-mono text-xs ${r.momentum > 0 ? 'text-emerald-400' : r.momentum < 0 ? 'text-red-400' : 'text-gray-600'}`}>
                      {r.momentum > 0 ? '↑' : r.momentum < 0 ? '↓' : '—'}{Math.abs(r.momentum) > 0 ? ` ${Math.abs(r.momentum)}%` : ''}
                    </span>
                  ) : <span className="text-gray-600">—</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-gray-600 mt-3">Buy/Hold/Sell counts • Target = mean analyst price target • Momentum = buy% change vs last month</p>
    </div>
  );
}
