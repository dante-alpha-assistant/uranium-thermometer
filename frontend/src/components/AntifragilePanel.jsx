import { useState, useEffect } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'

const contextMap = {
  real_yield: { name: 'Real Yield', goodWhen: 'Low real rates favor hard assets like uranium', badWhen: 'High real rates pull money into bonds' },
  dollar: { name: 'Dollar Weakness', goodWhen: 'Weak dollar boosts commodity prices globally', badWhen: 'Strong dollar is headwind for commodities' },
  supply_deficit: { name: 'Supply Deficit', goodWhen: 'More demand than supply = price pressure up', badWhen: 'Surplus would cap price gains' },
  divergence: { name: 'Spot-Equity Gap', goodWhen: 'Equities lagging spot = catch-up potential', badWhen: 'Equities ahead of spot = correction risk' },
  flow_positioning: { name: 'Flow Positioning', goodWhen: 'Low flows = contrarian buy signal', badWhen: 'Crowded positioning = fragile' },
  geopolitical_optionality: { name: 'Geopolitical', goodWhen: 'Supply disruption risk = price optionality', badWhen: 'Stable supply = less upside catalyst' },
}

function ScoreRing({ score, size = 72 }) {
  const pct = Math.min(100, Math.max(0, score))
  const color = score >= 65 ? 'var(--green)' : score >= 45 ? 'var(--yellow)' : 'var(--red)'
  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg className="w-full h-full -rotate-90" viewBox="0 0 36 36">
        <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
          fill="none" stroke="rgba(255,255,255,0.04)" strokeWidth="3" />
        <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
          fill="none" stroke={color} strokeWidth="3" strokeDasharray={`${pct}, 100`} opacity="0.7" />
      </svg>
      <span className="absolute inset-0 flex items-center justify-center text-xl font-bold" style={{ color }}>{score}</span>
    </div>
  )
}

function StatusDot({ score }) {
  if (score >= 65) return <span className="text-emerald-400/80">✓</span>
  if (score >= 45) return <span className="text-zinc-500">○</span>
  return <span className="text-red-400/80">✗</span>
}

export default function AntifragilePanel() {
  const [af, setAf] = useState(null)
  const [ry, setRy] = useState(null)
  const [sed, setSed] = useState(null)
  const [fm, setFm] = useState(null)
  const [loading, setLoading] = useState(true)
  const [expanded, setExpanded] = useState(false)

  useEffect(() => {
    Promise.all([
      fetch('api/antifragile-score').then(r => r.json()).catch(() => null),
      fetch('api/real-yield').then(r => r.json()).catch(() => null),
      fetch('api/spot-equity-divergence').then(r => r.json()).catch(() => null),
      fetch('api/flow-momentum').then(r => r.json()).catch(() => null),
    ]).then(([a, r, s, f]) => { setAf(a); setRy(r); setSed(s); setFm(f); setLoading(false) })
  }, [])

  if (loading) return <div className="u-card p-6 animate-pulse"><div className="w-16 h-16 rounded-full bg-zinc-800/50 mx-auto" /></div>
  if (!af) return null

  const regime = (af.regime || 'NEUTRAL').replace(/_/g, ' ')
  const regimeExplain = af.composite_score >= 75 ? 'Excellent entry conditions across all factors'
    : af.composite_score >= 60 ? 'Good entry conditions — most factors favor buying'
    : af.composite_score >= 45 ? 'Mixed conditions — some factors favorable, some not'
    : 'Poor entry conditions — wait for better setup'

  return (
    <div className="space-y-3">
      {/* Hero bar */}
      <div className="u-card p-5">
        <div className="flex items-center gap-5 flex-wrap">
          <ScoreRing score={af.composite_score} />
          <div className="flex-1 min-w-0">
            <p className="text-base font-semibold text-zinc-100">Anti-Fragile Score: {af.composite_score}/100</p>
            <p className="text-sm text-zinc-400 mt-0.5">{regime} — {regimeExplain}</p>
            <p className="text-xs text-zinc-500 mt-1">Measures how favorable conditions are for entering uranium positions</p>
          </div>
          <button onClick={() => setExpanded(!expanded)}
            className="p-2 rounded-lg hover:bg-zinc-800/60 text-zinc-400 hover:text-zinc-200 transition-colors">
            {expanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
          </button>
        </div>

        {/* Component scores with explanations */}
        <div className="mt-5 pt-4 border-t space-y-2" style={{ borderColor: 'var(--border)' }}>
          {Object.entries(af.components || {}).map(([k, v]) => {
            const ctx = contextMap[k] || { name: k, goodWhen: '', badWhen: '' }
            const explain = v.score >= 65 ? ctx.goodWhen : v.score < 45 ? ctx.badWhen : 'Neutral — neither helping nor hurting'
            return (
              <div key={k} className="flex flex-wrap items-center gap-x-3 gap-y-0.5">
                <StatusDot score={v.score} />
                <span className="text-sm font-mono font-bold text-zinc-200 w-8">{v.score}</span>
                <span className="text-sm font-medium text-zinc-300 w-32">{ctx.name}</span>
                <span className="text-xs text-zinc-500 flex-1">{explain}</span>
              </div>
            )
          })}
        </div>
      </div>

      {/* Expanded: detailed data with human-readable context */}
      {expanded && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 animate-fade-in">
          {/* Real Yield */}
          {ry && !ry.error && (
            <div className="u-card p-5">
              <p className="text-sm font-semibold text-zinc-200 mb-3">Real Yield Environment</p>
              <div className="space-y-3">
                <div>
                  <div className="flex justify-between text-sm mb-0.5">
                    <span className="text-zinc-400">Real yield</span>
                    <span className="font-mono font-bold text-zinc-100">{ry.real_yield_pct}%</span>
                  </div>
                  <p className="text-xs text-zinc-500">
                    {parseFloat(ry.real_yield_pct) <= 0.5
                      ? 'Near zero = cheap money = bullish for commodities'
                      : parseFloat(ry.real_yield_pct) <= 1.5
                      ? 'Moderate — some competition from bonds'
                      : 'High real rates pulling money into bonds — headwind'}
                  </p>
                </div>
                <div>
                  <div className="flex justify-between text-sm mb-0.5">
                    <span className="text-zinc-400">Dollar (DXY)</span>
                    <span className="font-mono font-bold text-zinc-100">{ry.dxy_current || '—'}</span>
                  </div>
                  <p className="text-xs text-zinc-500">
                    {ry.dxy_current < 100
                      ? 'Below 100 = weak dollar = tailwind for commodities'
                      : ry.dxy_current < 105
                      ? 'Moderate dollar strength — neutral'
                      : 'Strong dollar = headwind for commodity prices'}
                  </p>
                </div>
                <div className="pt-2 border-t" style={{ borderColor: 'var(--border)' }}>
                  <p className="text-sm text-zinc-300">
                    Signal: <span className="font-mono font-bold">{ry.all_weather_signal}</span>
                  </p>
                  <p className="text-xs text-zinc-500 mt-0.5">{ry.all_weather_detail}</p>
                </div>
              </div>
            </div>
          )}

          {/* Spot-Equity Divergence */}
          {sed && !sed.error && (
            <div className="u-card p-5">
              <p className="text-sm font-semibold text-zinc-200 mb-3">Spot vs Equity Divergence</p>
              <div className="space-y-3">
                <div>
                  <div className="flex justify-between text-sm mb-0.5">
                    <span className="text-zinc-400">Z-Score</span>
                    <span className="font-mono font-bold text-zinc-100">{sed.divergence_z_score}</span>
                  </div>
                  <p className="text-xs text-zinc-500">
                    {parseFloat(sed.divergence_z_score) > 1
                      ? 'Spot price significantly ahead of equities — equities may catch up'
                      : parseFloat(sed.divergence_z_score) < -1
                      ? 'Equities ahead of spot — potential correction risk'
                      : 'Spot and equities roughly aligned — no unusual gap'}
                  </p>
                </div>
                <div>
                  <div className="flex justify-between text-sm mb-0.5">
                    <span className="text-zinc-400">Current gap</span>
                    <span className="font-mono font-bold text-zinc-100">{sed.current_divergence_pct}%</span>
                  </div>
                  <p className="text-xs text-zinc-500">
                    Difference between uranium spot price movement and URA ETF returns
                  </p>
                </div>
                {sed.rolling_returns && Object.entries(sed.rolling_returns).map(([period, d]) => (
                  <div key={period} className="flex items-center justify-between text-xs pt-1 border-t" style={{ borderColor: 'var(--border)' }}>
                    <span className="text-zinc-500">{period}</span>
                    <span className="text-zinc-300">Spot {d.spot_proxy_return_pct > 0 ? '+' : ''}{d.spot_proxy_return_pct}%</span>
                    <span className="text-zinc-300">URA {d.ura_return_pct > 0 ? '+' : ''}{d.ura_return_pct}%</span>
                  </div>
                ))}
                <div className="pt-2 border-t" style={{ borderColor: 'var(--border)' }}>
                  <p className="text-sm text-zinc-300">
                    Signal: <span className="font-mono font-bold">{sed.signal?.replace(/_/g, ' ')}</span>
                  </p>
                  <p className="text-xs text-zinc-500 mt-0.5">{sed.detail}</p>
                </div>
              </div>
            </div>
          )}

          {/* Flow Momentum */}
          {fm && !fm.error && (
            <div className="u-card p-5">
              <p className="text-sm font-semibold text-zinc-200 mb-3">Money Flow Positioning</p>
              <p className="text-xs text-zinc-500 mb-3">Dollar trading volume trends — shows if money is flowing in or out of uranium</p>
              <div className="space-y-3">
                {Object.entries(fm.etfs || {}).map(([sym, d]) => (
                  <div key={sym}>
                    <div className="flex items-center justify-between text-sm mb-0.5">
                      <span className="font-mono font-bold text-zinc-200">{sym}</span>
                      <span className="text-xs font-mono text-zinc-400">{d.signal?.replace(/_/g, ' ')}</span>
                    </div>
                    <p className="text-xs text-zinc-500">
                      5d: ${d.dollar_volume_5d}M · 22d: ${d.dollar_volume_22d}M · Trend: {d.flow_trend_short_pct > 0 ? '+' : ''}{d.flow_trend_short_pct}%
                    </p>
                  </div>
                ))}
                <div className="pt-2 border-t" style={{ borderColor: 'var(--border)' }}>
                  <p className="text-sm text-zinc-300">
                    Overall: <span className="font-mono font-bold">{fm.aggregate_signal?.replace(/_/g, ' ')}</span>
                  </p>
                  <p className="text-xs text-zinc-500 mt-0.5">{fm.aggregate_detail}</p>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
