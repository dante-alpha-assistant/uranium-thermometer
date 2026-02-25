import { useState, useEffect } from 'react'

export default function EnrichmentCapacity() {
  const [data, setData] = useState(null)
  useEffect(() => { fetch('api/enrichment-capacity').then(r => r.json()).then(setData).catch(() => {}) }, [])
  if (!data) return null

  const { enrichment: e, conversion: c, geopolitical_risk: g } = data

  const Bar = ({ used, total, label }) => {
    const pct = (used / total * 100).toFixed(0)
    return (
      <div className="mb-2">
        <div className="flex justify-between text-[10px] text-zinc-400 mb-1">
          <span>{label}</span><span>{pct}%</span>
        </div>
        <div className="h-1.5 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.04)' }}>
          <div className="h-full rounded-full" style={{ width: `${pct}%`, background: 'var(--accent)', opacity: 0.4 }} />
        </div>
      </div>
    )
  }

  return (
    <div className="u-card p-6">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h3 className="text-sm font-semibold text-zinc-200">Enrichment & Conversion</h3>
          <p className="text-[10px] text-zinc-400 mt-0.5">Fuel cycle capacity</p>
        </div>
        <span className="text-xs font-mono text-zinc-400">{g.signal}</span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div>
          <p className="text-xs uppercase tracking-wider text-zinc-400 mb-2">Enrichment (SWU)</p>
          <Bar used={e.global_demand_tSWU} total={e.global_capacity_tSWU}
            label={`${(e.global_demand_tSWU/1000).toFixed(0)}k / ${(e.global_capacity_tSWU/1000).toFixed(0)}k tSWU`} />
          <div className="space-y-0.5 mt-2">
            {e.providers.map(p => (
              <div key={p.name} className="flex justify-between text-xs">
                <span className="text-zinc-400">{p.name} <span className="text-zinc-400">({p.country})</span></span>
                <span className="font-mono text-zinc-500">{p.share_pct}%</span>
              </div>
            ))}
          </div>
        </div>

        <div>
          <p className="text-xs uppercase tracking-wider text-zinc-400 mb-2">Conversion (UF₆)</p>
          <Bar used={c.global_demand_tU} total={c.global_capacity_tU}
            label={`${(c.global_demand_tU/1000).toFixed(0)}k / ${(c.global_capacity_tU/1000).toFixed(0)}k tU`} />
          <div className="space-y-0.5 mt-2">
            {c.providers.map(p => (
              <div key={p.name} className="flex justify-between text-xs">
                <span className="text-zinc-400">{p.name} <span className="text-zinc-400">({p.country})</span></span>
                <span className="font-mono text-zinc-500">{p.share_pct}%</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {g.insight && <p className="text-xs text-zinc-500 mt-4 leading-relaxed">{g.insight}</p>}
    </div>
  )
}
