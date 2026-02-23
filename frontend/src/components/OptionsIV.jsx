import { useState, useEffect } from 'react';

const signalStyle = {
  'HIGH FEAR': 'bg-red-900/30 text-red-400',
  'ELEVATED': 'bg-amber-900/30 text-amber-400',
  'NORMAL': 'bg-gray-800 text-gray-400',
  'COMPLACENT': 'bg-emerald-900/30 text-emerald-400',
};

export default function OptionsIV() {
  const [data, setData] = useState(null);

  useEffect(() => {
    fetch('api/options-iv-summary')
      .then(r => r.json())
      .then(setData)
      .catch(() => {});
  }, []);

  if (!data?.tickers?.length) return null;

  const pct = (v) => `${(v * 100).toFixed(1)}%`;

  return (
    <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-bold text-white">📊 Options Implied Volatility</h3>
        <div className="flex gap-2">
          <span className={`text-xs font-mono px-2 py-1 rounded ${signalStyle[data.sector_signal] || ''}`}>
            Sector: {data.sector_signal} ({pct(data.avg_sector_iv)})
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-3">
        {data.tickers.map(t => {
          const spread = t.iv_rv_spread;
          const overpriced = spread && spread > 0.1;
          return (
            <div key={t.symbol} className="bg-gray-800/40 rounded-lg p-3">
              <div className="flex items-center justify-between mb-1">
                <span className="font-mono text-sm text-gray-300">{t.symbol}</span>
                <span className={`text-xs px-1.5 py-0.5 rounded ${signalStyle[t.signal]}`}>{t.signal}</span>
              </div>
              <div className="space-y-1">
                <div className="flex justify-between text-xs">
                  <span className="text-gray-500">IV</span>
                  <span className="font-mono text-white font-bold">{pct(t.front_iv)}</span>
                </div>
                {t.realized_vol_30d && (
                  <div className="flex justify-between text-xs">
                    <span className="text-gray-500">RV 30d</span>
                    <span className="font-mono text-gray-400">{pct(t.realized_vol_30d)}</span>
                  </div>
                )}
                {spread !== null && (
                  <div className="flex justify-between text-xs">
                    <span className="text-gray-500">IV-RV</span>
                    <span className={`font-mono ${overpriced ? 'text-red-400' : 'text-emerald-400'}`}>
                      {spread > 0 ? '+' : ''}{pct(spread)}
                    </span>
                  </div>
                )}
                {t.expiries?.[0]?.put_call_ratio && (
                  <div className="flex justify-between text-xs">
                    <span className="text-gray-500">P/C</span>
                    <span className={`font-mono ${t.expiries[0].put_call_ratio > 1 ? 'text-red-400' : 'text-gray-400'}`}>
                      {t.expiries[0].put_call_ratio.toFixed(2)}
                    </span>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
      <p className="text-xs text-gray-600 mt-3">IV {'>'} RV = options overpriced (fear). P/C {'>'} 1.0 = bearish positioning.</p>
    </div>
  );
}
