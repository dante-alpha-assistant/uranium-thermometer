import { useState, useEffect } from 'react'
import { TrendingUp, TrendingDown } from 'lucide-react'

export default function Thermometer({ ura }) {
  const [composite, setComposite] = useState(null)

  useEffect(() => {
    if (!ura) return
    fetch('api/score-decomposition?symbol=URA')
      .then(r => r.json())
      .then(d => { if (d.total_score != null) setComposite(d) })
      .catch(() => {})
  }, [ura])

  if (!ura) return null

  const pct = ura.zone_pct || 50
  const zone = ura.zone || 'YELLOW'
  const zoneColor = zone === 'GREEN' ? 'var(--green)' : zone === 'RED' ? 'var(--red)' : 'var(--yellow)'

  return (
    <div className="u-card p-6">
      {/* Price header */}
      <div className="flex items-end justify-between mb-8">
        <div>
          <p className="text-xs uppercase tracking-wider text-zinc-400 mb-1">URA ETF</p>
          <p className="text-4xl font-bold font-mono tracking-tight" style={{ color: zoneColor }}>
            ${ura.current_price}
          </p>
        </div>
        <div className="text-right">
          <div className="flex items-center gap-1.5 justify-end" style={{ color: ura.change_pct >= 0 ? 'var(--green)' : 'var(--red)' }}>
            {ura.change_pct >= 0 ? <TrendingUp className="w-3.5 h-3.5" /> : <TrendingDown className="w-3.5 h-3.5" />}
            <span className="text-sm font-mono font-semibold">{ura.change_pct >= 0 ? '+' : ''}{ura.change_pct}%</span>
          </div>
          <p className="text-xs text-zinc-400 mt-0.5 font-mono">${ura.range_low} – ${ura.range_high}</p>
        </div>
      </div>

      {/* Minimal gauge */}
      <div className="mb-6">
        <div className="relative h-2 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.04)' }}>
          {/* Zone gradient background */}
          <div className="absolute inset-0 rounded-full" style={{
            background: `linear-gradient(to right, var(--green) 0%, var(--green) 20%, var(--yellow) 30%, var(--yellow) 70%, var(--red) 80%, var(--red) 100%)`,
            opacity: 0.15,
          }} />
          {/* Active fill */}
          <div className="absolute inset-y-0 left-0 rounded-full transition-all duration-700"
            style={{ width: `${pct}%`, backgroundColor: zoneColor, opacity: 0.7 }} />
        </div>
        {/* Position dot */}
        <div className="relative" style={{ marginTop: '-10px' }}>
          <div className="absolute transition-all duration-700"
            style={{
              left: `${pct}%`,
              transform: 'translateX(-50%)',
            }}>
            <div className="w-4 h-4 rounded-full border-2 border-zinc-900"
              style={{ backgroundColor: zoneColor, boxShadow: `0 0 12px ${zoneColor}40` }} />
          </div>
        </div>
        {/* Zone labels */}
        <div className="flex justify-between mt-4 text-xs uppercase tracking-wider font-mono">
          <span className="text-emerald-400/40">Buy</span>
          <span className="text-zinc-400">Hold</span>
          <span className="text-red-400/40">Sell</span>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: 'Zone', value: zone, color: zoneColor },
          { label: 'Composite', value: `${composite?.total_score ?? ura.signal_score}/100`, sub: composite?.label || ura.signal_label, color: (composite?.total_score ?? ura.signal_score) >= 55 ? 'var(--green)' : (composite?.total_score ?? ura.signal_score) <= 45 ? 'var(--red)' : 'var(--yellow)' },
          { label: 'RSI (14)', value: ura.rsi || '—', color: ura.rsi < 30 ? 'var(--green)' : ura.rsi > 70 ? 'var(--red)' : 'var(--text)' },
          { label: 'Range', value: `$${ura.range_low}–$${ura.range_high}` },
        ].map((s, i) => (
          <div key={i} className="rounded-xl p-3" className="u-stat" >
            <p className="text-xs uppercase tracking-wider text-zinc-400 mb-1">{s.label}</p>
            <p className="font-mono font-bold text-sm" style={{ color: s.color || 'var(--text)' }}>{s.value}</p>
            {s.sub && <p className="text-[10px] text-zinc-400 mt-0.5">{s.sub}</p>}
          </div>
        ))}
      </div>
    </div>
  )
}
