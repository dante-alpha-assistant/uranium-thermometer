import { useState, useEffect } from 'react';

export default function InsiderTrades() {
  const [data, setData] = useState(null);

  useEffect(() => {
    fetch('api/insider-trades')
      .then(r => r.json())
      .then(setData)
      .catch(() => {});
  }, []);

  if (!data?.trades?.length) return null;

  const { trades, summary } = data;
  const fmt = (n) => {
    if (!n) return '—';
    if (n >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
    if (n >= 1e3) return `$${(n / 1e3).toFixed(0)}K`;
    return `$${n}`;
  };

  const netPositive = summary.net_insider_value > 0;

  return (
    <div className="u-card p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-zinc-200">🕵️ Insider Activity</h3>
        <div className="flex gap-2">
          <span className="text-xs font-mono px-2 py-1 rounded bg-zinc-800/40 text-emerald-400">
            {summary.total_buys} buys
          </span>
          <span className="text-xs font-mono px-2 py-1 rounded bg-zinc-800/40 text-red-400">
            {summary.total_sells} sells
          </span>
          <span className={`text-xs font-mono px-2 py-1 rounded ${netPositive ? 'bg-zinc-800/40 text-emerald-400/60' : 'bg-zinc-800/40 text-red-400/60'}`}>
            Net: {fmt(Math.abs(summary.net_insider_value))} {netPositive ? '↑' : '↓'}
          </span>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-zinc-400 border-b border-zinc-800/50">
              <th className="text-left p-2">Date</th>
              <th className="text-left p-2">Ticker</th>
              <th className="text-left p-2">Insider</th>
              <th className="text-left p-2">Title</th>
              <th className="text-center p-2">Type</th>
              <th className="text-right p-2">Value</th>
            </tr>
          </thead>
          <tbody>
            {trades.slice(0, 15).map((t, i) => {
              const isBigBuy = t.type === 'BUY' && (t.value || 0) >= 100000;
              return (
                <tr key={i} className={`border-b border-zinc-800/50/50 ${isBigBuy ? 'bg-zinc-800/40' : ''}`}>
                  <td className="p-2 text-zinc-400 font-mono">{t.date?.slice(0, 10)}</td>
                  <td className="p-2 font-mono text-zinc-200">{t.symbol}</td>
                  <td className="p-2 text-zinc-300 truncate max-w-32">{t.insider}</td>
                  <td className="p-2 text-zinc-400 truncate max-w-24">{t.position}</td>
                  <td className="p-2 text-center">
                    <span className={`text-xs font-mono px-1.5 py-0.5 rounded ${t.type === 'BUY' ? 'bg-zinc-800/40 text-emerald-400/60' : 'bg-zinc-800/40 text-red-400/60'}`}>
                      {t.type}
                    </span>
                  </td>
                  <td className={`p-2 text-right font-mono ${isBigBuy ? 'text-emerald-400 font-bold' : 'text-zinc-300'}`}>
                    {fmt(t.value)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
