import { useState, useEffect } from 'react';

const signalStyles = {
  ACCUMULATION: 'bg-emerald-900/30 text-emerald-400',
  DISTRIBUTION: 'bg-red-900/30 text-red-400',
  NEUTRAL: 'bg-gray-800 text-gray-400',
};
const signalEmoji = { ACCUMULATION: '🟢', DISTRIBUTION: '🔴', NEUTRAL: '⚪' };

export default function InstitutionalOwnership({ symbol = 'URA' }) {
  const [data, setData] = useState(null);
  const [selected, setSelected] = useState(symbol);

  useEffect(() => {
    fetch(`api/institutional-ownership/${selected}`)
      .then(r => r.json())
      .then(setData)
      .catch(() => {});
  }, [selected]);

  if (!data?.holders?.length) return null;

  const tickers = ['URA','CCJ','UEC','UUUU','DNN','NXE'];
  const sc = signalStyles[data.signal] || signalStyles.NEUTRAL;
  const fmt = (n) => {
    if (n >= 1e9) return `$${(n/1e9).toFixed(1)}B`;
    if (n >= 1e6) return `$${(n/1e6).toFixed(0)}M`;
    if (n >= 1e3) return `$${(n/1e3).toFixed(0)}K`;
    return `$${n}`;
  };

  return (
    <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
      <div className="flex items-center justify-between mb-1">
        <h3 className="text-lg font-bold text-white">🏛️ Institutional Ownership</h3>
        <span className={`text-xs font-mono px-2 py-1 rounded ${sc}`}>
          {signalEmoji[data.signal]} {data.signal} ({data.increasing_count}↑ {data.decreasing_count}↓)
        </span>
      </div>
      <div className="flex gap-1 mb-3">
        {tickers.map(t => (
          <button key={t} onClick={() => setSelected(t)}
            className={`px-2 py-0.5 rounded text-xs font-mono ${selected === t ? 'bg-emerald-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}>
            {t}
          </button>
        ))}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-gray-500 border-b border-gray-800">
              <th className="text-left p-1.5">Holder</th>
              <th className="text-right p-1.5">Value</th>
              <th className="text-right p-1.5">% Float</th>
              <th className="text-right p-1.5">Change</th>
            </tr>
          </thead>
          <tbody>
            {data.holders.filter(h => h.type === 'institution').map((h, i) => (
              <tr key={i} className="border-b border-gray-800/50">
                <td className="p-1.5 text-gray-300 truncate max-w-40">{h.name}</td>
                <td className="p-1.5 text-right font-mono text-gray-400">{fmt(h.value)}</td>
                <td className="p-1.5 text-right font-mono text-gray-500">{h.pct_held}%</td>
                <td className={`p-1.5 text-right font-mono ${h.pct_change > 0 ? 'text-emerald-400' : h.pct_change < 0 ? 'text-red-400' : 'text-gray-600'}`}>
                  {h.pct_change > 0 ? '+' : ''}{h.pct_change}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-gray-600 mt-2">Total institutional: {data.institutional_pct}% of float • Q4 2025 13F filings</p>
    </div>
  );
}
