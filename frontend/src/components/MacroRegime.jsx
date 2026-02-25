import { useState, useEffect } from 'react'

const indicatorMeta = {
  '^TNX': { label: '10Y Yield', unit: '%', context: { TAILWIND: 'falling = tailwind for risk assets', HEADWIND: 'rising = headwind for risk assets', NEUTRAL: 'stable = neutral' } },
  'DX-Y.NYB': { label: 'Dollar (DXY)', unit: '', context: { TAILWIND: 'weakening = tailwind for commodities', HEADWIND: 'strengthening = headwind for commodities', NEUTRAL: 'stable = neutral' } },
  '^GSPC': { label: 'S&P 500', unit: '', context: { TAILWIND: 'rising = risk-on tailwind', HEADWIND: 'falling = risk-off headwind', NEUTRAL: 'flat = neutral' } },
}

function fmtVal(key, val) {
  if (val == null) return '—'
  if (key === '^TNX') return `${val.toFixed(2)}%`
  if (key === 'DX-Y.NYB') return val.toFixed(1)
  if (key === '^GSPC') return val.toLocaleString(undefined, { maximumFractionDigits: 0 })
  return String(val)
}

export default function MacroRegime() {
  const [data, setData] = useState(null)
  useEffect(() => { fetch('api/macro-regime').then(r => r.json()).then(setData).catch(() => {}) }, [])
  if (!data?.indicators) return null

  const regimeColor = data.regime === 'FAVORABLE' ? 'var(--green)' : data.regime === 'HOSTILE' ? 'var(--red)' : 'var(--yellow)'

  return (
    <div className="u-card p-5 h-full">
      <div className="flex items-baseline justify-between mb-5">
        <div>
          <p className="text-xs uppercase tracking-wider text-zinc-400 mb-1">Macro Environment</p>
          <div className="flex items-baseline gap-2">
            <span className="text-xl font-black" style={{ color: regimeColor }}>{data.regime}</span>
            <span className="text-lg font-mono font-bold text-zinc-300">{data.score}<span className="text-xs text-zinc-500">/100</span></span>
          </div>
        </div>
        <div className="text-right text-xs text-zinc-400">
          <span className="text-emerald-400/70">{data.tailwinds}</span> tailwind{data.tailwinds !== 1 ? 's' : ''} · <span className="text-red-400/70">{data.headwinds}</span> headwind{data.headwinds !== 1 ? 's' : ''}
        </div>
      </div>

      <div className="space-y-4">
        {Object.entries(data.indicators).map(([key, ind]) => {
          const meta = indicatorMeta[key] || { label: key, unit: '', context: {} }
          const sigColor = ind.signal === 'TAILWIND' ? 'text-emerald-400/70' : ind.signal === 'HEADWIND' ? 'text-red-400/70' : 'text-zinc-400'
          const contextText = meta.context[ind.signal] || ''
          const pctRank = ind.percentile_rank

          return (
            <div key={key}>
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-medium text-zinc-300">{meta.label}</span>
                <span className={`text-xs font-mono font-semibold ${sigColor}`}>{ind.signal}</span>
              </div>
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-sm font-mono font-bold text-zinc-100">{fmtVal(key, ind.current)}</span>
                {pctRank != null && (
                  <span className="text-[10px] font-mono text-zinc-500">{pctRank.toFixed(0)}th percentile (6mo)</span>
                )}
              </div>
              {/* Percentile bar */}
              <div className="h-1 rounded-full overflow-hidden mb-1" style={{ background: 'rgba(255,255,255,0.04)' }}>
                <div className="h-full rounded-full transition-all" style={{ width: `${pctRank || 50}%`, background: 'var(--accent)', opacity: 0.35 }} />
              </div>
              {contextText && (
                <p className="text-[10px] text-zinc-500 italic">{contextText}</p>
              )}
            </div>
          )
        })}
      </div>

      {data.interpretation && (
        <p className="text-xs text-zinc-400 mt-4 leading-relaxed">{data.interpretation}</p>
      )}
    </div>
  )
}
