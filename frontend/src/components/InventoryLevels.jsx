import { useState, useEffect } from 'react'

export default function InventoryLevels() {
  const [data, setData] = useState(null)
  useEffect(() => { fetch('api/inventory-levels').then(r => r.json()).then(setData).catch(() => {}) }, [])
  if (!data) return null

  const { current: c, historical: h } = data
  const maxInv = Math.max(...h.map(d => d.inventory_mlbs))

  return (
    <div className="u-card p-6">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h3 className="text-sm font-semibold text-zinc-200">US Uranium Inventories</h3>
          <p className="text-[10px] text-zinc-400 mt-0.5">EIA data</p>
        </div>
        <span className="text-xs font-mono text-zinc-400">{c.signal} · {c.years_of_supply}yr</span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-5">
        {[
          { label: 'Inventory', value: `${c.inventory_mlbs}M lbs` },
          { label: 'Annual Use', value: `${c.consumption_mlbs}M lbs` },
          { label: 'YoY', value: `${c.yoy_change_pct > 0 ? '+' : ''}${c.yoy_change_pct}%` },
        ].map(s => (
          <div key={s.label} className="text-center p-2.5 rounded-xl" className="u-stat" >
            <p className="text-[10px] text-zinc-400">{s.label}</p>
            <p className="font-mono text-sm font-bold text-zinc-200">{s.value}</p>
          </div>
        ))}
      </div>

      <div className="flex items-end gap-1 h-24">
        {h.map(d => {
          const pct = (d.inventory_mlbs / maxInv) * 100
          return (
            <div key={d.year} className="flex-1 flex flex-col items-center justify-end h-full">
              <span className="text-[9px] font-mono text-zinc-400 mb-0.5">{d.inventory_mlbs}</span>
              <div className="w-full rounded-t transition-all" style={{ height: `${pct}%`, background: 'var(--accent)', opacity: 0.3 }} />
              <span className="text-[9px] text-zinc-500 mt-1">{String(d.year).slice(2)}</span>
            </div>
          )
        })}
      </div>

      {data.insight && <p className="text-xs text-zinc-400 mt-4 leading-relaxed">{data.insight}</p>}
    </div>
  )
}
