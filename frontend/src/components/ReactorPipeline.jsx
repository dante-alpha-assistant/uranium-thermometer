import { useState, useEffect } from 'react';

export default function ReactorPipeline() {
  const [data, setData] = useState(null);

  useEffect(() => {
    fetch('api/reactor-pipeline')
      .then(r => r.json())
      .then(setData)
      .catch(() => {});
  }, []);

  if (!data) return null;

  const { operational, under_construction, planned, top_builders, new_demand_tonnes_u_per_year } = data;

  return (
    <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
      <h3 className="text-lg font-bold text-white mb-1">🏗️ Nuclear Reactor Pipeline</h3>
      <p className="text-xs text-gray-500 mb-4">Global demand indicator • Source: WNA/IAEA</p>

      <div className="grid grid-cols-3 gap-4 mb-5">
        <div className="text-center p-3 bg-emerald-900/20 rounded-lg border border-emerald-800/30">
          <p className="text-2xl font-bold text-emerald-400">{operational?.count}</p>
          <p className="text-xs text-gray-400">Operational</p>
          <p className="text-xs text-emerald-600">{operational?.capacity_gwe} GWe</p>
        </div>
        <div className="text-center p-3 bg-amber-900/20 rounded-lg border border-amber-800/30">
          <p className="text-2xl font-bold text-amber-400">{under_construction?.count}</p>
          <p className="text-xs text-gray-400">Under Construction</p>
          <p className="text-xs text-amber-600">{under_construction?.capacity_gwe} GWe</p>
        </div>
        <div className="text-center p-3 bg-blue-900/20 rounded-lg border border-blue-800/30">
          <p className="text-2xl font-bold text-blue-400">{planned?.count}</p>
          <p className="text-xs text-gray-400">Planned</p>
          <p className="text-xs text-blue-600">{planned?.capacity_gwe} GWe</p>
        </div>
      </div>

      {new_demand_tonnes_u_per_year > 0 && (
        <div className="bg-gray-800/50 rounded-lg p-3 mb-4">
          <p className="text-xs text-gray-400">New uranium demand from pipeline</p>
          <p className="text-sm font-mono text-yellow-400 font-bold">
            +{new_demand_tonnes_u_per_year.toLocaleString()} tonnes U/year
          </p>
          <p className="text-xs text-gray-600">~200 tonnes U per GWe capacity</p>
        </div>
      )}

      <div>
        <p className="text-xs text-gray-500 mb-2 font-bold">Top Builders (Under Construction)</p>
        <div className="space-y-1.5">
          {top_builders?.slice(0, 6).map((b, i) => {
            const maxCount = top_builders[0]?.count || 1;
            return (
              <div key={b.country} className="flex items-center gap-2 text-xs">
                <span className="text-gray-400 w-24 truncate">{b.country}</span>
                <div className="flex-1 h-2 bg-gray-800 rounded-full overflow-hidden">
                  <div className="h-full bg-amber-500/70 rounded-full" style={{ width: `${(b.count / maxCount) * 100}%` }} />
                </div>
                <span className="text-gray-300 font-mono w-8 text-right">{b.count}</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
