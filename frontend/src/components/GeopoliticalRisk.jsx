import { useState, useEffect } from 'react';

const riskColor = { LOW: 'text-emerald-400', MEDIUM: 'text-amber-400', HIGH: 'text-orange-400', CRITICAL: 'text-red-400' };
const riskBg = { LOW: 'bg-emerald-900/20', MEDIUM: 'bg-amber-900/20', HIGH: 'bg-orange-900/20', CRITICAL: 'bg-red-900/20' };

export default function GeopoliticalRisk() {
  const [data, setData] = useState(null);
  useEffect(() => { fetch('api/geopolitical-risk').then(r => r.json()).then(setData).catch(() => {}); }, []);
  if (!data) return null;

  const score = data.composite_risk_score;
  const gaugeWidth = Math.min(score, 100);

  return (
    <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-bold text-white">🌍 Geopolitical Supply Risk</h3>
        <span className="text-xs font-mono px-2 py-1 rounded bg-orange-900/30 text-orange-400">
          {data.supply_at_risk_pct}% AT RISK
        </span>
      </div>

      {/* Risk gauge */}
      <div className="mb-4">
        <div className="flex justify-between text-xs text-gray-500 mb-1">
          <span>Low Risk</span>
          <span className="font-mono font-bold text-orange-400">{score}/100</span>
          <span>Critical</span>
        </div>
        <div className="h-3 bg-gray-800 rounded-full overflow-hidden">
          <div className="h-full rounded-full transition-all" style={{
            width: `${gaugeWidth}%`,
            background: score > 60 ? 'linear-gradient(90deg, #f59e0b, #ef4444)' :
                        score > 40 ? 'linear-gradient(90deg, #10b981, #f59e0b)' :
                        '#10b981'
          }} />
        </div>
      </div>

      {/* Country profiles */}
      <div className="space-y-2 mb-3">
        {data.profiles.map(p => (
          <div key={p.country} className={`rounded-lg p-2.5 ${riskBg[p.risk]}`}>
            <div className="flex items-center justify-between mb-1">
              <div className="flex items-center gap-2">
                <span className="text-lg">{p.flag}</span>
                <span className="text-sm font-bold text-white">{p.country}</span>
                <span className="text-xs text-gray-500">{p.supply_pct}% supply</span>
              </div>
              <span className={`text-xs font-mono font-bold ${riskColor[p.risk]}`}>{p.risk}</span>
            </div>
            <p className="text-xs text-gray-400 mb-1">{p.factors[0]}</p>
            <p className="text-xs text-gray-600">📌 {p.last_event}</p>
          </div>
        ))}
      </div>

      <p className="text-xs text-gray-500">{data.signal}</p>
      <p className="text-xs text-gray-600 mt-1">{data.note}</p>
    </div>
  );
}
