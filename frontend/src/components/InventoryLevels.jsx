import { useState, useEffect } from 'react';

const signalStyle = {
  CRITICAL: 'bg-red-900/40 text-red-400',
  TIGHT: 'bg-amber-900/30 text-amber-400',
  ADEQUATE: 'bg-emerald-900/20 text-emerald-400',
  SURPLUS: 'bg-emerald-900/30 text-emerald-400',
};

export default function InventoryLevels() {
  const [data, setData] = useState(null);
  useEffect(() => {
    fetch('api/inventory-levels').then(r => r.json()).then(setData).catch(() => {});
  }, []);
  if (!data) return null;

  const { current: c, historical: h } = data;
  const maxInv = Math.max(...h.map(d => d.inventory_mlbs));

  return (
    <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-bold text-white">📦 US Uranium Inventories</h3>
        <span className={`text-xs font-mono px-2 py-1 rounded ${signalStyle[c.signal]}`}>
          {c.signal} ({c.years_of_supply}yr supply)
        </span>
      </div>

      <div className="grid grid-cols-3 gap-3 mb-4">
        <div className="bg-gray-800/40 rounded-lg p-2 text-center">
          <p className="text-xs text-gray-500">Inventory</p>
          <p className="font-mono text-white font-bold">{c.inventory_mlbs}M lbs</p>
        </div>
        <div className="bg-gray-800/40 rounded-lg p-2 text-center">
          <p className="text-xs text-gray-500">Annual Use</p>
          <p className="font-mono text-gray-300">{c.consumption_mlbs}M lbs</p>
        </div>
        <div className="bg-gray-800/40 rounded-lg p-2 text-center">
          <p className="text-xs text-gray-500">YoY Change</p>
          <p className={`font-mono font-bold ${c.yoy_change_pct < 0 ? 'text-red-400' : 'text-emerald-400'}`}>
            {c.yoy_change_pct > 0 ? '+' : ''}{c.yoy_change_pct}%
          </p>
        </div>
      </div>

      {/* Bar chart */}
      <div className="flex items-end gap-1 h-28">
        {h.map(d => {
          const pct = (d.inventory_mlbs / maxInv) * 100;
          const yrs = d.years_of_supply;
          const color = yrs < 1.5 ? 'bg-red-500' : yrs < 2.5 ? 'bg-amber-500' : 'bg-emerald-600';
          return (
            <div key={d.year} className="flex-1 flex flex-col items-center justify-end h-full">
              <span className="text-xs font-mono text-gray-500 mb-0.5">{d.inventory_mlbs}</span>
              <div className={`w-full ${color} rounded-t`} style={{ height: `${pct}%` }}
                title={`${d.year}: ${d.inventory_mlbs}M lbs (${yrs}yr supply)`} />
              <span className="text-xs text-gray-600 mt-1">{String(d.year).slice(2)}</span>
            </div>
          );
        })}
      </div>
      <div className="flex justify-between text-xs text-gray-600 mt-1">
        <span>🟢 &gt;4yr</span><span>🟡 2-4yr</span><span>🔴 &lt;1.5yr</span>
      </div>

      <p className="text-xs text-gray-600 mt-3">{data.insight}</p>
    </div>
  );
}
