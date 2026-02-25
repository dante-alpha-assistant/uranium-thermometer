import { useState, useEffect } from 'react'

export default function VolumeAnomalies() {
  const [data, setData] = useState(null)
  useEffect(() => { fetch('api/volume-anomalies').then(r => r.json()).then(setData).catch(() => {}) }, [])
  if (!data?.anomalies?.length) return null

  const fmt = (n) => {
    if (n >= 1e9) return `$${(n / 1e9).toFixed(1)}B`
    if (n >= 1e6) return `$${(n / 1e6).toFixed(0)}M`
    if (n >= 1e3) return `$${(n / 1e3).toFixed(0)}K`
    return `$${n}`
  }

  return (
    <div className="u-card p-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-sm font-semibold text-zinc-200">Volume Watch</h3>
          <p className="text-xs text-zinc-400 mt-0.5">Dollar volume · today vs 20-day average</p>
        </div>
        {data.flagged > 0 && (
          <span className="text-xs font-mono text-amber-400/70">{data.flagged} anomal{data.flagged > 1 ? 'ies' : 'y'}</span>
        )}
      </div>

      <div className="space-y-3">
        <div className="flex items-center text-[10px] uppercase tracking-wider text-zinc-500 px-1">
          <span className="w-14">Ticker</span>
          <span className="flex-1">Today / Avg (20d)</span>
          <span className="w-14 text-right">Ratio</span>
        </div>

        {data.anomalies.map(a => (
          <div key={a.symbol} className="flex items-center text-xs px-1">
            <span className="text-zinc-200 font-mono font-semibold w-14">{a.symbol}</span>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <span className="font-mono text-zinc-300">{fmt(a.dollar_volume)}</span>
                <span className="text-zinc-500">/</span>
                <span className="font-mono text-zinc-400">{fmt(a.dollar_avg_20d)} avg</span>
              </div>
              <div className="h-1 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.04)' }}>
                <div className="h-full rounded-full transition-all"
                  style={{
                    width: `${Math.min(100, (a.ratio / 2.5) * 100)}%`,
                    background: a.anomaly ? 'var(--yellow)' : 'var(--accent)',
                    opacity: a.anomaly ? 0.6 : 0.3,
                  }} />
              </div>
            </div>
            <span className={`font-mono w-14 text-right font-semibold ${a.anomaly ? 'text-amber-400/80' : 'text-zinc-400'}`}>
              {a.ratio}x
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
