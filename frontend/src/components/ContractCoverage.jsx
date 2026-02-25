import { useState, useEffect } from 'react'

export default function ContractCoverage() {
  const [data, setData] = useState(null)
  useEffect(() => { fetch('api/contract-coverage').then(r => r.json()).then(setData).catch(() => {}) }, [])
  if (!data) return null

  const us = data.us_utilities.coverage
  const eu = data.eu_utilities.coverage
  const maxUncov = Math.max(...us.map(c => c.uncovered_mlbs), ...eu.map(c => c.uncovered_mlbs), 1)

  return (
    <div className="u-card p-6">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h3 className="text-sm font-semibold text-zinc-200">Contract Coverage Gap</h3>
          <p className="text-[10px] text-zinc-400 mt-0.5">US + EU utilities</p>
        </div>
        <span className="text-xs font-mono text-zinc-400">{data.signal}</span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-5">
        {[
          { label: 'Uncovered 2028', value: `${data.total_uncovered_2028_mlbs}M lbs` },
          { label: 'Uncovered 2030', value: `${data.total_uncovered_2030_mlbs}M lbs` },
          { label: 'Total Demand', value: `${data.us_utilities.annual_requirement_mlbs + data.eu_utilities.annual_requirement_mlbs}M/yr` },
        ].map(s => (
          <div key={s.label} className="text-center p-2.5 rounded-xl" className="u-stat" >
            <p className="text-[10px] text-zinc-400">{s.label}</p>
            <p className="font-mono text-sm font-bold text-zinc-200">{s.value}</p>
          </div>
        ))}
      </div>

      {/* Stacked bars */}
      <div className="flex items-end gap-1 h-20 mb-1">
        {us.map((c, i) => {
          const euMatch = eu[i] || { uncovered_mlbs: 0 }
          const usPct = (c.uncovered_mlbs / maxUncov) * 80
          const euPct = (euMatch.uncovered_mlbs / maxUncov) * 80
          return (
            <div key={c.year} className="flex-1 flex flex-col items-center justify-end h-full">
              <div className="w-full flex flex-col justify-end" style={{ height: '80%' }}>
                <div className="rounded-t" style={{ height: `${euPct}%`, minHeight: euPct > 0 ? 2 : 0, background: 'var(--accent)', opacity: 0.2 }} />
                <div style={{ height: `${usPct}%`, minHeight: 2, background: 'var(--accent)', opacity: 0.35 }} />
              </div>
              <span className="text-[9px] text-zinc-500 mt-1">{c.year}</span>
            </div>
          )
        })}
      </div>

      {/* Coverage % row */}
      <div className="flex gap-1 mt-3">
        {us.map(c => (
          <div key={c.year} className="flex-1 text-center">
            <span className="text-[10px] font-mono text-zinc-500">{c.contracted_pct}%</span>
          </div>
        ))}
      </div>
      <p className="text-[10px] text-zinc-600 text-center mt-0.5">US contracted %</p>

      {data.insight && <p className="text-xs text-zinc-400 mt-4 leading-relaxed">{data.insight}</p>}
    </div>
  )
}
