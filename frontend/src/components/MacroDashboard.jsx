import { useState, useEffect } from 'react'
import { Globe, TrendingUp, TrendingDown, Shield, AlertTriangle, Gauge } from 'lucide-react'

export default function MacroDashboard() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/macro-dashboard')
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  if (loading) return <div className="bg-zinc-900/60 border border-zinc-800 rounded-2xl p-6 animate-pulse h-48" />
  if (!data) return null

  const c = data.components || {}

  const scoreColor = (s) => {
    if (s >= 65) return 'text-emerald-400'
    if (s >= 55) return 'text-emerald-300'
    if (s <= 35) return 'text-red-400'
    if (s <= 45) return 'text-orange-400'
    return 'text-zinc-300'
  }

  const labelColor = (l) => {
    const colors = {
      RISK_ON: 'bg-emerald-400/10 text-emerald-400',
      LEAN_RISK_ON: 'bg-emerald-400/10 text-emerald-300',
      NEUTRAL: 'bg-zinc-400/10 text-zinc-400',
      LEAN_RISK_OFF: 'bg-orange-400/10 text-orange-400',
      RISK_OFF: 'bg-red-400/10 text-red-400',
    }
    return colors[l] || 'bg-zinc-800 text-zinc-400'
  }

  const regimeColors = {
    BULL_QUIET: 'bg-emerald-400/10 text-emerald-400',
    BULL_VOLATILE: 'bg-yellow-400/10 text-yellow-400',
    SIDEWAYS: 'bg-zinc-400/10 text-zinc-400',
    BEAR_QUIET: 'bg-orange-400/10 text-orange-400',
    BEAR_VOLATILE: 'bg-red-400/10 text-red-400',
  }

  const componentLabel = (key) => {
    const labels = {
      global_liquidity: 'Liquidity',
      economic_surprise: 'Economy',
      fear_greed: 'Fear & Greed',
      volatility_regime: 'Volatility',
      currency: 'USD Strength',
    }
    return labels[key] || key
  }

  const gaugeAngle = ((data.macro_score || 50) / 100) * 180 - 90

  return (
    <div className="bg-zinc-900/60 border border-zinc-800 rounded-2xl p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Globe className="w-5 h-5 text-indigo-400" />
          <h3 className="text-base font-bold text-zinc-100">Macro Dashboard</h3>
        </div>
        <div className="flex items-center gap-2">
          <span className={`text-[10px] font-bold uppercase px-2.5 py-1 rounded-full ${labelColor(data.macro_label)}`}>
            {data.macro_label?.replace(/_/g, ' ')}
          </span>
          <span className={`text-[10px] font-bold uppercase px-2.5 py-1 rounded-full ${regimeColors[data.regime] || 'bg-zinc-800 text-zinc-400'}`}>
            {data.regime?.replace(/_/g, ' ')}
          </span>
        </div>
      </div>

      {/* Main score + sizing */}
      <div className="flex items-center gap-6">
        <div className="text-center">
          <div className={`text-4xl font-black font-mono ${scoreColor(data.macro_score)}`}>
            {data.macro_score?.toFixed(0)}
          </div>
          <div className="text-[10px] text-zinc-500 mt-1">MACRO SCORE</div>
        </div>
        <div className="flex-1 text-sm text-zinc-400">
          {data.interpretation}
        </div>
        <div className="text-center bg-zinc-800/50 rounded-xl px-4 py-3">
          <div className="text-xl font-bold text-zinc-100">{data.position_sizing_multiplier}x</div>
          <div className="text-[10px] text-zinc-500">SIZING</div>
        </div>
      </div>

      {/* Component bars */}
      <div className="space-y-2">
        {Object.entries(c).filter(([k]) => k !== 'regime').map(([key, val]) => {
          const score = val.score || 50
          const label = val.label || 'N/A'
          return (
            <div key={key} className="flex items-center gap-3">
              <span className="text-[11px] text-zinc-400 w-20 shrink-0">{componentLabel(key)}</span>
              <div className="flex-1 h-3 bg-zinc-800/50 rounded-full overflow-hidden">
                <div className={`h-full rounded-full transition-all ${
                  score >= 60 ? 'bg-emerald-400/50' : score <= 40 ? 'bg-red-400/50' : 'bg-zinc-500/50'
                }`} style={{ width: `${score}%` }} />
              </div>
              <span className={`text-[11px] font-mono w-8 text-right ${scoreColor(score)}`}>{score.toFixed(0)}</span>
              <span className={`text-[10px] w-24 text-right ${
                score >= 60 ? 'text-emerald-400/60' : score <= 40 ? 'text-red-400/60' : 'text-zinc-500'
              }`}>{label.replace(/_/g, ' ')}</span>
            </div>
          )
        })}
      </div>

      {/* Extra details */}
      <div className="flex gap-4 text-[10px] text-zinc-600">
        {c.fear_greed?.vix && <span>VIX: {c.fear_greed.vix}</span>}
        {c.volatility_regime?.vol_20d && <span>URA Vol: {c.volatility_regime.vol_20d}%</span>}
        {c.currency?.uup_20d_pct && <span>USD 20d: {c.currency.uup_20d_pct > 0 ? '+' : ''}{c.currency.uup_20d_pct}%</span>}
        {c.economic_surprise?.spy_20d && <span>SPY 20d: {c.economic_surprise.spy_20d > 0 ? '+' : ''}{c.economic_surprise.spy_20d}%</span>}
      </div>
    </div>
  )
}
