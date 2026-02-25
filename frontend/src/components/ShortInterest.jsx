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
    if (s === 'HEAVY') return 'text-red-400/60';
    if (s === 'MODERATE') return 'text-yellow-400';
    return 'text-zinc-400';
  };

  const statusBg = (s) => {
    if (s === 'HEAVY') return 'bg-zinc-800/40';
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
    <div className="u-card p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-zinc-200">🩳 Short Interest</h3>
        {data.squeeze_risks > 0 && (
          <span className="text-xs bg-zinc-800/40 text-red-300 px-2 py-1 rounded font-mono">
            ⚠️ {data.squeeze_risks} squeeze risk{data.squeeze_risks > 1 ? 's' : ''}
          </span>
        )}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-zinc-400 border-b border-zinc-800/50">
              <th className="text-left p-2">Ticker</th>
              <th className="text-right p-2">Short % Float</th>
              <th className="text-right p-2">Days to Cover</th>
              <th className="text-right p-2">Shares Short</th>
              <th className="text-center p-2">Status</th>
            </tr>
          </thead>
          <tbody>
            {data.tickers.map(t => (
              <tr key={t.symbol} className={`border-b border-zinc-800/50/50 ${statusBg(t.status)}`}>
                <td className="p-2 font-mono text-zinc-200">{t.symbol}</td>
                <td className={`p-2 text-right font-mono ${statusColor(t.status)}`}>
                  {t.short_pct_float != null ? `${t.short_pct_float}%` : '—'}
                </td>
                <td className={`p-2 text-right font-mono ${(t.short_ratio || 0) > 5 ? 'text-amber-400/60' : 'text-zinc-300'}`}>
                  {t.short_ratio ?? '—'}
                </td>
                <td className="p-2 text-right font-mono text-zinc-400">{fmt(t.shares_short)}</td>
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
      <p className="text-xs text-zinc-500 mt-3">Updated bi-monthly via FINRA • Cached 6h • Squeeze risk: days-to-cover &gt;5 + short% &gt;10%</p>
    </div>
  );
}
