import { useState, useEffect } from 'react';

const signalStyle = {
  'STRONG INFLOW': 'bg-zinc-800/40 text-emerald-400/60',
  'INFLOW': 'bg-zinc-800/40 text-emerald-400/60',
  'NEUTRAL': 'bg-zinc-800 text-zinc-300',
  'OUTFLOW': 'bg-zinc-800/40 text-red-400/60',
  'STRONG OUTFLOW': 'bg-zinc-800/40 text-red-400/60',
};

export default function EtfFlows() {
  const [data, setData] = useState(null);
  useEffect(() => {
    fetch('api/etf-flows').then(r => r.json()).then(setData).catch(() => {});
  }, []);
  if (!data?.etfs?.length) return null;

  return (
    <div className="u-card p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-zinc-200">💸 ETF Fund Flows</h3>
        <span className={`text-xs font-mono px-2 py-1 rounded ${signalStyle[data.sector_signal] || ''}`}>
          {data.sector_signal}
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {data.etfs.map(etf => {
          const wk = etf.weekly_volumes || [];
          const maxVol = Math.max(...wk.map(w => w.dollar_volume), 1);
          return (
            <div key={etf.symbol} className="bg-zinc-800/30 rounded-lg p-3">
              <div className="flex items-center justify-between mb-2">
                <div>
                  <span className="font-mono text-sm text-zinc-200">{etf.symbol}</span>
                  <span className="text-xs text-zinc-500 ml-2">{etf.name}</span>
                </div>
                <span className={`text-xs font-mono px-1.5 py-0.5 rounded ${signalStyle[etf.signal]}`}>
                  {etf.flow_trend_pct > 0 ? '+' : ''}{etf.flow_trend_pct}%
                </span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mb-2">
                <div className="text-center">
                  <p className="text-xs text-zinc-500">5d avg</p>
                  <p className="font-mono text-xs text-zinc-200">${etf.avg_dollar_vol_5d}M</p>
                </div>
                <div className="text-center">
                  <p className="text-xs text-zinc-500">22d avg</p>
                  <p className="font-mono text-xs text-zinc-300">${etf.avg_dollar_vol_22d}M</p>
                </div>
                <div className="text-center">
                  <p className="text-xs text-zinc-500">63d avg</p>
                  <p className="font-mono text-xs text-zinc-400">${etf.avg_dollar_vol_63d}M</p>
                </div>
              </div>
              {wk.length > 2 && (
                <div className="flex items-end gap-0.5 h-12">
                  {wk.map((w, i) => (
                    <div key={i} className="flex-1 flex flex-col items-center justify-end h-full">
                      <div className={`w-full rounded-t ${i >= wk.length - 2 ? 'bg-emerald-600/50' : 'bg-gray-700/50'}`}
                        style={{ height: `${(w.dollar_volume / maxVol) * 100}%`, minHeight: 2 }} />
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
      <p className="text-xs text-zinc-500 mt-2">Dollar volume trend: 5d vs 22d avg. Falling volume = money exiting sector.</p>
    </div>
  );
}
