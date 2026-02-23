import { useState, useEffect } from 'react';

const typeStyle = {
  bearish: 'bg-red-900/30 border-red-800/50 text-red-400',
  bullish: 'bg-emerald-900/30 border-emerald-800/50 text-emerald-400',
};
const indIcon = { RSI: '📈', MACD: '📊', Volume: '📉' };
const compStyle = {
  'BEARISH DIVERGENCE': 'text-red-400',
  'BULLISH DIVERGENCE': 'text-emerald-400',
  'MILD BEARISH': 'text-red-400/70',
  'MILD BULLISH': 'text-emerald-400/70',
  'NO DIVERGENCE': 'text-gray-500',
};

export default function Divergences() {
  const [data, setData] = useState(null);
  useEffect(() => { fetch('api/divergences').then(r => r.json()).then(setData).catch(() => {}); }, []);
  if (!data) return null;

  const active = data.tickers?.filter(t => t.has_divergence) || [];
  const inactive = data.tickers?.filter(t => !t.has_divergence) || [];

  return (
    <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-bold text-white">⚡ Divergence Scanner</h3>
        <span className={`text-sm font-mono font-bold ${compStyle[data.composite_signal] || 'text-gray-500'}`}>
          {data.composite_signal}
        </span>
      </div>
      <p className="text-xs text-gray-500 mb-4">{data.composite_detail}</p>

      {active.length > 0 && (
        <div className="space-y-2 mb-4">
          {active.map(t => t.divergences.map((d, i) => (
            <div key={`${t.symbol}-${i}`} className={`rounded-lg border p-3 ${typeStyle[d.type]}`}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span>{indIcon[d.indicator]}</span>
                  <span className="font-mono font-bold text-sm">{t.symbol}</span>
                  <span className="text-xs opacity-70">${t.price}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs uppercase font-mono">{d.type}</span>
                  {d.strength === 'strong' && <span className="text-xs">🔥</span>}
                </div>
              </div>
              <p className="text-xs mt-1 opacity-80">{d.detail}</p>
            </div>
          )))}
        </div>
      )}

      {inactive.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {inactive.map(t => (
            <span key={t.symbol} className="text-xs font-mono px-2 py-1 rounded bg-gray-800/50 text-gray-600">
              {t.symbol} ✓
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
