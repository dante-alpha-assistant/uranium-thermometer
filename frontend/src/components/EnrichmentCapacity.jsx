import { useState, useEffect } from 'react';

export default function EnrichmentCapacity() {
  const [data, setData] = useState(null);
  useEffect(() => {
    fetch('api/enrichment-capacity').then(r => r.json()).then(setData).catch(() => {});
  }, []);

  if (!data) return null;

  const { enrichment: e, conversion: c, geopolitical_risk: g } = data;

  const Bar = ({ used, total, label }) => {
    const pct = (used / total * 100).toFixed(0);
    return (
      <div className="mb-1">
        <div className="flex justify-between text-xs text-gray-500 mb-0.5">
          <span>{label}</span><span>{pct}% utilized</span>
        </div>
        <div className="h-3 bg-gray-800 rounded-full overflow-hidden">
          <div className={`h-full rounded-full ${+pct > 85 ? 'bg-red-500' : +pct > 70 ? 'bg-amber-500' : 'bg-emerald-500'}`}
            style={{ width: `${pct}%` }} />
        </div>
      </div>
    );
  };

  return (
    <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-bold text-white">🏭 Enrichment & Conversion</h3>
        <span className="text-xs font-mono px-2 py-1 rounded bg-red-900/30 text-red-400">
          ⚠️ {g.signal}
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Enrichment */}
        <div>
          <h4 className="text-xs text-gray-500 font-bold mb-2">ENRICHMENT (SWU)</h4>
          <Bar used={e.global_demand_tSWU} total={e.global_capacity_tSWU} label={`${(e.global_demand_tSWU/1000).toFixed(0)}k / ${(e.global_capacity_tSWU/1000).toFixed(0)}k tSWU`} />
          <div className="space-y-0.5 mt-2">
            {e.providers.map(p => (
              <div key={p.name} className="flex justify-between text-xs">
                <span className={`${p.country === 'Russia' ? 'text-red-400' : 'text-gray-400'}`}>
                  {p.name} <span className="text-gray-600">({p.country})</span>
                </span>
                <span className="font-mono text-gray-500">{p.share_pct}%</span>
              </div>
            ))}
          </div>
        </div>

        {/* Conversion */}
        <div>
          <h4 className="text-xs text-gray-500 font-bold mb-2">CONVERSION (UF₆)</h4>
          <Bar used={c.global_demand_tU} total={c.global_capacity_tU} label={`${(c.global_demand_tU/1000).toFixed(0)}k / ${(c.global_capacity_tU/1000).toFixed(0)}k tU`} />
          <div className="space-y-0.5 mt-2">
            {c.providers.map(p => (
              <div key={p.name} className="flex justify-between text-xs">
                <span className={`${p.country === 'Russia' ? 'text-red-400' : 'text-gray-400'}`}>
                  {p.name} <span className="text-gray-600">({p.country})</span>
                </span>
                <span className="font-mono text-gray-500">{p.share_pct}%</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <p className="text-xs text-red-400/70 mt-3">⚠️ {g.insight}</p>
    </div>
  );
}
