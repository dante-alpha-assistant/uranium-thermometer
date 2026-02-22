import { useState, useEffect } from 'react';

const regimeColors = {
  FAVORABLE: { bg: 'bg-emerald-900/30', border: 'border-emerald-500', text: 'text-emerald-400', label: '🟢 FAVORABLE' },
  NEUTRAL: { bg: 'bg-yellow-900/30', border: 'border-yellow-500', text: 'text-yellow-400', label: '🟡 NEUTRAL' },
  HOSTILE: { bg: 'bg-red-900/30', border: 'border-red-500', text: 'text-red-400', label: '🔴 HOSTILE' },
};

const signalColors = {
  TAILWIND: 'text-emerald-400',
  NEUTRAL: 'text-yellow-400',
  HEADWIND: 'text-red-400',
};

const indicatorLabels = {
  '^TNX': { icon: '📊', short: '10Y Yield' },
  'DX-Y.NYB': { icon: '💵', short: 'Dollar (DXY)' },
  '^GSPC': { icon: '📈', short: 'S&P 500' },
};

export default function MacroRegime() {
  const [data, setData] = useState(null);

  useEffect(() => {
    fetch('api/macro-regime')
      .then(r => r.json())
      .then(setData)
      .catch(() => {});
  }, []);

  if (!data || !data.indicators) return null;

  const style = regimeColors[data.regime] || regimeColors.NEUTRAL;

  return (
    <div className={`${style.bg} ${style.border} border rounded-xl p-5`}>
      <div className="flex items-center justify-between mb-4">
        <div>
          <p className="text-xs text-gray-400 uppercase tracking-widest font-mono">Macro Environment</p>
          <p className={`text-2xl font-black ${style.text}`}>{style.label}</p>
        </div>
        <div className="text-right">
          <p className="text-xs text-gray-400">Regime Score</p>
          <p className={`text-2xl font-mono font-bold ${style.text}`}>{data.score}</p>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3 mb-4">
        {Object.entries(data.indicators).map(([key, ind]) => {
          const label = indicatorLabels[key] || { icon: '📌', short: key };
          return (
            <div key={key} className="bg-gray-800/50 rounded-lg p-3">
              <p className="text-xs text-gray-500">{label.icon} {label.short}</p>
              <p className="text-lg font-mono font-bold text-white">
                {key === '^TNX' ? `${ind.current}%` : key === '^GSPC' ? ind.current.toLocaleString() : ind.current}
              </p>
              <p className={`text-xs font-mono ${signalColors[ind.signal]}`}>{ind.signal}</p>
              <div className="mt-1 h-1 bg-gray-700 rounded-full overflow-hidden">
                <div className="h-full bg-blue-500 rounded-full" style={{ width: `${ind.percentile_rank}%` }} />
              </div>
              <p className="text-[10px] text-gray-600 mt-0.5">P{Math.round(ind.percentile_rank)} of 6mo range</p>
            </div>
          );
        })}
      </div>

      <p className="text-sm text-gray-400">{data.interpretation}</p>
      <div className="mt-2 flex gap-3 text-xs text-gray-500">
        <span>Tailwinds: <span className="text-emerald-400 font-mono">{data.tailwinds}</span></span>
        <span>Headwinds: <span className="text-red-400 font-mono">{data.headwinds}</span></span>
      </div>
    </div>
  );
}
