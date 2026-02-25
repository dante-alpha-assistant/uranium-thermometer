import { useState, useEffect } from 'react'

export default function MinePipeline() {
  const [data, setData] = useState(null)
  useEffect(() => { fetch('api/mine-pipeline').then(r => r.json()).then(setData).catch(() => {}) }, [])
  if (!data) return null

  const { projects, by_year, summary } = data
  const maxCap = Math.max(...by_year.map(y => y.capacity_mlbs), 1)

  return (
    <div className="u-card p-6">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h3 className="text-sm font-semibold text-zinc-200">Mine Development Pipeline</h3>
          <p className="text-[10px] text-zinc-400 mt-0.5">{summary.total_pipeline_mlbs}M lbs capacity · Gap 2030: {summary.supply_gap_2030_mlbs}M lbs</p>
        </div>
      </div>

      <div className="flex items-end gap-1 h-14 mb-5">
        {by_year.map(y => (
          <div key={y.year} className="flex-1 flex flex-col items-center">
            <div className="w-full rounded-t" style={{ height: `${(y.capacity_mlbs / maxCap) * 100}%`, minHeight: 3, background: 'var(--accent)', opacity: 0.3 }} />
            <span className="text-[9px] text-zinc-500 mt-1">{y.year}</span>
          </div>
        ))}
      </div>

      <div className="overflow-x-auto max-h-48 overflow-y-auto">
        <table className="w-full text-xs">
          <thead className="sticky top-0" style={{ background: 'var(--surface)' }}>
            <tr className="text-zinc-600 border-b" style={{ borderColor: 'var(--border)' }}>
              <th className="text-left p-1.5 font-medium">Project</th>
              <th className="text-left p-1.5 font-medium">Company</th>
              <th className="text-center p-1.5 font-medium">Status</th>
              <th className="text-right p-1.5 font-medium">Capacity</th>
              <th className="text-right p-1.5 font-medium">Start</th>
            </tr>
          </thead>
          <tbody>
            {projects.map((p, i) => (
              <tr key={i} className="border-b" style={{ borderColor: 'var(--border)' }}>
                <td className="p-1.5 text-zinc-300">{p.name}</td>
                <td className="p-1.5 text-zinc-500">{p.company}</td>
                <td className="p-1.5 text-center">
                  <span className="text-[10px] font-mono text-zinc-500">{p.status}</span>
                </td>
                <td className="p-1.5 text-right font-mono text-zinc-400">{p.capacity_mlbs}M</td>
                <td className="p-1.5 text-right font-mono text-zinc-400">{p.expected_start}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
