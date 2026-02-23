import { useState, useEffect } from 'react';

const sigStyle = {
  'STRONG CONTANGO': 'bg-emerald-900/30 text-emerald-400',
  'CONTANGO': 'bg-emerald-900/20 text-emerald-400',
  'CONVERGING': 'bg-gray-800 text-gray-400',
  'BACKWARDATION': 'bg-red-900/30 text-red-400',
};

export default function TermSpread() {
  const [data, setData] = useState(null);
  useEffect(() => { fetch('api/term-spread').then(r => r.json()).then(setData).catch(() => {}); }, []);
  if (!data) return null;

  const hist = data.historical || [];
  const maxPrice = Math.max(...hist.map(h => Math.max(h.spot, h.lt)));

  return (
    <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-bold text-white">📑 Term vs Spot Spread</h3>
        <span className={`text-xs font-mono px-2 py-1 rounded ${sigStyle[data.signal] || ''}`}>{data.signal}</span>
      </div>

      {/* Price comparison */}
      <div className="grid grid-cols-3 gap-3 mb-4">
        <div className="bg-gray-800/40 rounded-lg p-3 text-center">
          <p className="text-xs text-gray-500">Spot</p>
          <p className="font-mono text-xl font-bold text-amber-400">${data.spot_price}</p>
        </div>
        <div className="bg-gray-800/40 rounded-lg p-3 text-center">
          <p className="text-xs text-gray-500">Mid-Term (3-5yr)</p>
          <p className="font-mono text-xl font-bold text-indigo-400">${data.mid_term_price}</p>
          <p className="text-xs text-gray-600">{data.mt_spread_pct > 0 ? '+' : ''}{data.mt_spread_pct}%</p>
        </div>
        <div className="bg-gray-800/40 rounded-lg p-3 text-center">
          <p className="text-xs text-gray-500">Long-Term (7-10yr)</p>
          <p className="font-mono text-xl font-bold text-emerald-400">${data.long_term_price}</p>
          <p className="text-xs text-gray-600">{data.lt_spread_pct > 0 ? '+' : ''}{data.lt_spread_pct}%</p>
        </div>
      </div>

      {/* Historical spread chart */}
      {hist.length > 2 && (
        <div className="mb-3">
          <p className="text-xs text-gray-600 mb-1">Historical spot vs long-term</p>
          <div className="flex items-end gap-1 h-20">
            {hist.map((h, i) => (
              <div key={i} className="flex-1 flex flex-col items-center justify-end h-full gap-0.5">
                <div className="w-full flex flex-col justify-end" style={{ height: '80%' }}>
                  <div className="bg-emerald-600/40 rounded-t" style={{ height: `${(h.lt / maxPrice) * 100}%`, minHeight: 2 }}
                    title={`LT: $${h.lt}`} />
                </div>
                <div className="w-full flex flex-col justify-end" style={{ height: '80%', marginTop: '-80%' }}>
                  <div className="bg-amber-500/40 rounded-t" style={{ height: `${(h.spot / maxPrice) * 100}%`, minHeight: 2 }}
                    title={`Spot: $${h.spot}`} />
                </div>
                <span className="text-xs text-gray-700" style={{ fontSize: '7px' }}>{h.period.split('-')[1]}</span>
              </div>
            ))}
          </div>
          <div className="flex gap-3 text-xs text-gray-600 mt-1">
            <span><span className="inline-block w-2 h-2 rounded bg-amber-500/40 mr-1" />Spot</span>
            <span><span className="inline-block w-2 h-2 rounded bg-emerald-600/40 mr-1" />Long-term</span>
          </div>
        </div>
      )}

      <p className="text-xs text-gray-500">{data.detail}</p>
      <p className="text-xs text-gray-600 mt-1">{data.insight}</p>
      <p className="text-xs text-gray-700 mt-1">Source: {data.source} ({data.last_updated})</p>
    </div>
  );
}
