import { useState, useEffect } from 'react'

export default function GeopoliticalRisk() {
  const [data, setData] = useState(null)
  useEffect(() => { fetch('api/geopolitical-risk').then(r => r.json()).then(setData).catch(() => {}) }, [])
  if (!data) return null

  const score = data.composite_risk_score

  return (
    <div className="u-card p-6">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h3 className="text-sm font-semibold text-zinc-200">Geopolitical Supply Risk</h3>
          <p className="text-[10px] text-zinc-400 mt-0.5">{data.supply_at_risk_pct}% of supply at risk</p>
        </div>
        <span className="text-lg font-bold font-mono text-zinc-300">{score}<span className="text-xs text-zinc-400">/100</span></span>
      </div>

      {/* Risk gauge */}
      <div className="mb-5">
        <div className="h-1.5 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.04)' }}>
          <div className="h-full rounded-full transition-all" style={{ width: `${Math.min(score, 100)}%`, background: 'var(--accent)', opacity: 0.4 }} />
        </div>
      </div>

      {/* Country profiles */}
      <div className="space-y-3">
        {data.profiles.map(p => (
          <div key={p.country} className="flex items-start gap-3">
            <span className="text-base mt-0.5">{p.flag}</span>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-0.5">
                <span className="text-sm font-semibold text-zinc-200">{p.country}</span>
                <span className="text-[10px] font-mono text-zinc-500">{p.supply_pct}% supply</span>
                <span className="text-[10px] font-mono text-zinc-600 ml-auto">{p.risk}</span>
              </div>
              <p className="text-xs text-zinc-500 leading-relaxed">{p.factors[0]}</p>
            </div>
          </div>
        ))}
      </div>

      {data.signal && <p className="text-xs text-zinc-500 mt-4 leading-relaxed">{data.signal}</p>}
    </div>
  )
}
