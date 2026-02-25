import { useState, useEffect } from 'react'

export default function SupplyDemand() {
  const [data, setData] = useState(null)
  useEffect(() => { fetch('api/supply-demand').then(r => r.json()).then(setData).catch(() => {}) }, [])
  if (!data) return null

  const { demand, supply, balance, pipeline } = data
  const ratio = Math.min(100, supply.total_supply_mlbs / demand.annual_demand_mlbs * 100)

  return (
    <div className="u-card p-6">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h3 className="text-sm font-semibold text-zinc-200">Supply / Demand</h3>
          <p className="text-[10px] text-zinc-400 mt-0.5">Annual balance</p>
        </div>
        <span className="text-xs font-mono text-zinc-400">{balance.signal}</span>
      </div>

      {/* Balance bar — muted */}
      <div className="mb-5">
        <div className="flex justify-between text-[10px] text-zinc-400 mb-1.5">
          <span>Supply {supply.total_supply_mlbs}M lbs</span>
          <span>Demand {demand.annual_demand_mlbs}M lbs</span>
        </div>
        <div className="relative h-2 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.04)' }}>
          <div className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${ratio}%`, background: 'var(--accent)', opacity: 0.4 }} />
        </div>
        <p className="text-xs font-mono text-zinc-400 mt-1.5 text-center">
          Deficit: {Math.abs(balance.deficit_mlbs)}M lbs/yr ({Math.abs(balance.deficit_pct)}%)
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div>
          <p className="text-xs uppercase tracking-wider text-zinc-400 mb-2">Supply</p>
          {supply.producers.map(p => (
            <div key={p.country} className="flex justify-between text-xs py-0.5">
              <span className="text-zinc-400">{p.country}</span>
              <span className="font-mono text-zinc-500">{p.mlbs}M</span>
            </div>
          ))}
        </div>
        <div>
          <p className="text-xs uppercase tracking-wider text-zinc-400 mb-2">Demand</p>
          {demand.top_consumers.slice(0, 7).map(c => (
            <div key={c.country} className="flex justify-between text-xs py-0.5">
              <span className="text-zinc-400">{c.country}</span>
              <span className="font-mono text-zinc-500">{c.demand_mlbs}M</span>
            </div>
          ))}
        </div>
        <div>
          <p className="text-xs uppercase tracking-wider text-zinc-400 mb-2">Pipeline</p>
          <p className="text-xs text-zinc-400 mb-1">
            <span className="font-mono text-zinc-200">{pipeline.under_construction_units}</span> reactors building
          </p>
          {pipeline.top_construction.map(c => (
            <div key={c.country} className="flex justify-between text-xs py-0.5">
              <span className="text-zinc-400">{c.country}</span>
              <span className="font-mono text-zinc-500">{c.units} units</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
