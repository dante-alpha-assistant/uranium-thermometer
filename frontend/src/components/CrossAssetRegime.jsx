import { useState, useEffect } from 'react';

const regimeColors = {
  'COMMODITY SUPERCYCLE': 'text-emerald-400 bg-zinc-800/40 border-emerald-500/30',
  'RISK-ON': 'text-emerald-400 bg-zinc-800/40 border-emerald-500/20',
  'RISK-OFF': 'text-red-400 bg-zinc-800/40 border-red-500/20',
  'STAGFLATION': 'text-amber-400 bg-zinc-800/40 border-amber-500/20',
  'DEFLATION': 'text-red-400 bg-zinc-800/40 border-red-500/30',
  'TRANSITIONAL': 'text-zinc-300 bg-zinc-800 border-zinc-700',
};

export default function CrossAssetRegime() {
  const [data, setData] = useState(null);

  useEffect(() => {
    fetch('api/cross-asset-regime')
      .then(r => r.json())
      .then(setData)
      .catch(() => {});
  }, []);

  if (!data?.assets?.length) return null;

  const trendIcon = (t) => t === 'UP' ? '▲' : t === 'DOWN' ? '▼' : '—';
  const trendColor = (t) => t === 'UP' ? 'text-emerald-400/60' : t === 'DOWN' ? 'text-red-400/60' : 'text-zinc-400';
  const retColor = (v) => v > 0 ? 'text-emerald-400/60' : v < 0 ? 'text-red-400/60' : 'text-zinc-300';
  const rc = regimeColors[data.regime] || regimeColors['TRANSITIONAL'];

  return (
    <div className="u-card p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-zinc-200">🌐 Cross-Asset Regime</h3>
        <span className={`text-sm font-bold px-4 py-1.5 rounded-full border ${rc}`}>
          {data.regime} ({data.confidence}%)
        </span>
      </div>
      <p className="text-sm text-zinc-300 mb-5">{data.uranium_implication}</p>

      {/* Table layout */}
      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-zinc-700/50">
              <th className="text-left text-xs text-zinc-400 uppercase tracking-wider py-2 pr-4">Asset</th>
              <th className="text-center text-xs text-zinc-400 uppercase tracking-wider py-2 px-4">Trend</th>
              <th className="text-right text-xs text-zinc-400 uppercase tracking-wider py-2 px-4">30d Return</th>
              <th className="text-right text-xs text-zinc-400 uppercase tracking-wider py-2 pl-4">90d Return</th>
            </tr>
          </thead>
          <tbody>
            {data.assets.map(a => (
              <tr key={a.symbol} className="border-b border-zinc-800/50/50 hover:bg-zinc-800/30 transition-colors">
                <td className="py-3 pr-4">
                  <div className="flex items-center gap-3">
                    <span className="font-mono text-base font-bold text-zinc-100">{a.symbol}</span>
                    <span className="text-sm text-zinc-300">{a.name}</span>
                  </div>
                </td>
                <td className="py-3 px-4 text-center">
                  <span className={`text-lg font-bold ${trendColor(a.trend)}`}>
                    {trendIcon(a.trend)}
                  </span>
                </td>
                <td className={`py-3 px-4 text-right font-mono text-base font-semibold ${retColor(a.return_30d)}`}>
                  {a.return_30d > 0 ? '+' : ''}{a.return_30d}%
                </td>
                <td className={`py-3 pl-4 text-right font-mono text-base font-semibold ${retColor(a.return_90d)}`}>
                  {a.return_90d > 0 ? '+' : ''}{a.return_90d}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
