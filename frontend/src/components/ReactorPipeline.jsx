import { useState, useEffect } from 'react'

export default function ReactorPipeline() {
  const [data, setData] = useState(null)

  useEffect(() => {
    fetch('api/reactor-pipeline').then(r => r.json()).then(setData).catch(() => {})
  }, [])

  if (!data) return null

  const { operational, under_construction, planned, top_builders, new_demand_tonnes_u_per_year } = data

  return (
    <div className="u-card p-6">
      <h3 className="text-sm font-semibold text-zinc-200 mb-1">Nuclear Reactor Pipeline</h3>
      <p className="text-[10px] text-zinc-400 mb-5">Global demand indicator · WNA/IAEA</p>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-5">
        {[
          { label: 'Operational', count: operational?.count, cap: operational?.capacity_gwe },
          { label: 'Under Construction', count: under_construction?.count, cap: under_construction?.capacity_gwe },
          { label: 'Planned', count: planned?.count, cap: planned?.capacity_gwe },
        ].map(item => (
          <div key={item.label} className="text-center p-3 rounded-xl" className="u-stat" >
            <p className="text-2xl font-bold text-zinc-100">{item.count}</p>
            <p className="text-[10px] text-zinc-500 mt-0.5">{item.label}</p>
            <p className="text-[10px] text-zinc-400">{item.cap} GWe</p>
          </div>
        ))}
      </div>

      {new_demand_tonnes_u_per_year > 0 && (
        <div className="rounded-xl p-3 mb-5" className="u-stat" >
          <p className="text-[10px] text-zinc-500">New demand from pipeline</p>
          <p className="text-sm font-mono font-bold text-zinc-200">+{new_demand_tonnes_u_per_year.toLocaleString()} tonnes U/yr</p>
        </div>
      )}

      {top_builders?.length > 0 && (
        <div>
          <p className="text-xs uppercase tracking-wider text-zinc-400 mb-2">Top Builders</p>
          <div className="space-y-1.5">
            {top_builders.slice(0, 6).map(b => {
              const maxCount = top_builders[0]?.count || 1
              return (
                <div key={b.country} className="flex items-center gap-2 text-xs">
                  <span className="text-zinc-400 w-24 truncate">{b.country}</span>
                  <div className="flex-1 h-1.5 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.04)' }}>
                    <div className="h-full rounded-full transition-all" style={{ width: `${(b.count / maxCount) * 100}%`, background: 'var(--accent)', opacity: 0.5 }} />
                  </div>
                  <span className="text-zinc-500 font-mono w-8 text-right">{b.count}</span>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
