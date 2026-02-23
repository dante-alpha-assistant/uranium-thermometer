import { useState, useEffect } from 'react';

export default function VolumeAnomalies() {
  const [data, setData] = useState(null);

  useEffect(() => {
    fetch('api/volume-anomalies')
      .then(r => r.json())
      .then(setData)
      .catch(() => {});
  }, []);

  if (!data?.anomalies?.length) return null;

  const fmt = (n) => {
    if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
    if (n >= 1e3) return `${(n / 1e3).toFixed(0)}K`;
    return n;
  };

  return (
    <div className="bg-gray-900 rounded-xl p-4 border border-gray-800 mt-4">
      <h3 className="text-sm font-bold text-white mb-3">📊 Volume Watch</h3>
      <div className="space-y-2">
        {data.anomalies.map(a => (
          <div key={a.symbol} className="flex items-center justify-between text-xs">
            <span className="text-gray-300 font-mono w-16">{a.symbol}</span>
            <div className="flex-1 mx-2">
              <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full ${a.anomaly ? 'bg-amber-500' : 'bg-gray-600'}`}
                  style={{ width: `${Math.min(100, (a.ratio / 3) * 100)}%` }}
                />
              </div>
            </div>
            <span className={`font-mono w-12 text-right ${a.anomaly ? 'text-amber-400 font-bold' : 'text-gray-500'}`}>
              {a.ratio}x
            </span>
          </div>
        ))}
      </div>
      {data.flagged > 0 && (
        <p className="text-amber-400 text-xs mt-2">⚠️ {data.flagged} ticker{data.flagged > 1 ? 's' : ''} with unusual volume</p>
      )}
    </div>
  );
}
