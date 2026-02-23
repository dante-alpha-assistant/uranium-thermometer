import { useState, useEffect } from 'react';

export default function ShortInterest() {
  const [data, setData] = useState(null);

  useEffect(() => {
    fetch('api/short-interest')
      .then(r => r.json())
      .then(setData)
      .catch(() => {});
  }, []);

  if (!data?.tickers?.length) return null;

  const statusColor = (s) => {
    if (s === 'HEAVY') return 'text-red-400';
    if (s === 'MODERATE') return 'text-yellow-400';
    return 'text-gray-500';
  };

  const statusBg = (s) => {
    if (s === 'HEAVY') return 'bg-red-900/30';
    if (s === 'MODERATE') return 'bg-yellow-900/20';
    return '';
  };

  const fmt = (n) => {
    if (!n) return '—';
    if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
    if (n >= 1e3) return `${(n / 1e3).toFixed(0)}K`;
    return n;
  };

  return (
    <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-bold text-white">🩳 Short Interest</h3>
        {data.squeeze_risks > 0 && (
          <span className="text-xs bg-red-900/40 text-red-300 px-2 py-1 rounded font-mono">
            ⚠️ {data.squeeze_risks} squeeze risk{data.squeeze_risks > 1 ? 's' : ''}
          </span>
        )}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-gray-500 border-b border-gray-800">
              <th className="text-left p-2">Ticker</th>
              <th className="text-right p-2">Short % Float</th>
              <th className="text-right p-2">Days to Cover</th>
              <th className="text-right p-2">Shares Short</th>
              <th className="text-center p-2">Status</th>
            </tr>
          </thead>
          <tbody>
            {data.tickers.map(t => (
              <tr key={t.symbol} className={`border-b border-gray-800/50 ${statusBg(t.status)}`}>
                <td className="p-2 font-mono text-gray-300">{t.symbol}</td>
                <td className={`p-2 text-right font-mono ${statusColor(t.status)}`}>
                  {t.short_pct_float != null ? `${t.short_pct_float}%` : '—'}
                </td>
                <td className={`p-2 text-right font-mono ${(t.short_ratio || 0) > 5 ? 'text-amber-400' : 'text-gray-400'}`}>
                  {t.short_ratio ?? '—'}
                </td>
                <td className="p-2 text-right font-mono text-gray-500">{fmt(t.shares_short)}</td>
                <td className="p-2 text-center">
                  <span className={`text-xs font-mono ${statusColor(t.status)}`}>
                    {t.squeeze_risk ? '🔥 SQUEEZE' : t.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-gray-600 mt-3">Updated bi-monthly via FINRA • Cached 6h • Squeeze risk: days-to-cover &gt;5 + short% &gt;10%</p>
    </div>
  );
}
