import { useState, useEffect } from 'react';

export default function SupplyDemand() {
  const [data, setData] = useState(null);

  useEffect(() => {
    fetch('api/supply-demand')
      .then(r => r.json())
      .then(setData)
      .catch(() => {});
  }, []);

  if (!data) return null;

  const { demand, supply, balance, pipeline } = data;
  const deficitPct = Math.abs(balance.deficit_pct);

  return (
    <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-bold text-white">⚖️ Supply / Demand Balance</h3>
        <span className={`text-xs font-mono px-3 py-1 rounded ${
          balance.signal === 'STRUCTURAL DEFICIT' ? 'bg-emerald-900/30 text-emerald-400' :
          balance.signal === 'TIGHT' ? 'bg-amber-900/30 text-amber-400' :
          'bg-gray-800 text-gray-400'
        }`}>
          {balance.signal} ({deficitPct}%)
        </span>
      </div>

      {/* Balance bar */}
      <div className="mb-5">
        <div className="flex justify-between text-xs text-gray-500 mb-1">
          <span>Supply: {supply.total_supply_mlbs}M lbs</span>
          <span>Demand: {demand.annual_demand_mlbs}M lbs</span>
        </div>
        <div className="relative h-6 bg-gray-800 rounded-full overflow-hidden">
          <div className="absolute inset-y-0 left-0 bg-amber-600/60 rounded-l-full"
            style={{ width: `${Math.min(100, supply.total_supply_mlbs / demand.annual_demand_mlbs * 100)}%` }} />
          <div className="absolute inset-0 flex items-center justify-center text-xs font-mono text-white">
            Deficit: {Math.abs(balance.deficit_mlbs)}M lbs/yr
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Supply */}
        <div>
          <h4 className="text-xs text-gray-500 font-bold mb-2">SUPPLY (Mine Production)</h4>
          {supply.producers.map(p => (
            <div key={p.country} className="flex justify-between text-xs py-0.5">
              <span className="text-gray-400">{p.country}</span>
              <span className="font-mono text-gray-500">
                {p.mlbs}M <span className={p.trend === 'UP' ? 'text-emerald-500' : p.trend === 'DOWN' ? 'text-red-500' : 'text-gray-600'}>
                  {p.trend === 'UP' ? '↑' : p.trend === 'DOWN' ? '↓' : '→'}
                </span>
              </span>
            </div>
          ))}
          <div className="flex justify-between text-xs pt-1 border-t border-gray-800 mt-1">
            <span className="text-gray-500">+ Secondary</span>
            <span className="font-mono text-gray-600">{supply.secondary_supply_mlbs}M</span>
          </div>
        </div>

        {/* Demand */}
        <div>
          <h4 className="text-xs text-gray-500 font-bold mb-2">DEMAND (Top Consumers)</h4>
          {demand.top_consumers.slice(0, 7).map(c => (
            <div key={c.country} className="flex justify-between text-xs py-0.5">
              <span className="text-gray-400">{c.country}</span>
              <span className="font-mono text-gray-500">{c.demand_mlbs}M ({c.gwe}GWe)</span>
            </div>
          ))}
        </div>

        {/* Pipeline */}
        <div>
          <h4 className="text-xs text-gray-500 font-bold mb-2">CONSTRUCTION PIPELINE</h4>
          <div className="text-xs text-gray-400 mb-2">
            <span className="text-white font-mono">{pipeline.under_construction_units}</span> reactors ({pipeline.under_construction_gwe} GWe) building
          </div>
          {pipeline.top_construction.map(c => (
            <div key={c.country} className="flex justify-between text-xs py-0.5">
              <span className="text-gray-400">{c.country}</span>
              <span className="font-mono text-gray-500">{c.units} units ({c.gwe}GWe)</span>
            </div>
          ))}
          <div className="text-xs text-amber-400 mt-2 font-mono">
            +{pipeline.additional_demand_mlbs}M lbs/yr new demand
          </div>
        </div>
      </div>

      <p className="text-xs text-gray-600 mt-4">{data.uranium_implication}</p>
    </div>
  );
}
