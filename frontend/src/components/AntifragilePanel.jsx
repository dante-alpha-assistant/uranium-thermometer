import { useState, useEffect } from 'react'
import { Shield, TrendingUp, TrendingDown, Minus, DollarSign, Activity, Droplets, Zap } from 'lucide-react'

function ScoreGauge({ score, label, size = "lg" }) {
  const color = score >= 75 ? 'text-emerald-400' : score >= 60 ? 'text-green-400' : score >= 45 ? 'text-yellow-400' : 'text-red-400'
  const bg = score >= 75 ? 'bg-emerald-400' : score >= 60 ? 'bg-green-400' : score >= 45 ? 'bg-yellow-400' : 'bg-red-400'
  const pct = Math.min(100, Math.max(0, score))
  return (
    <div className={size === "lg" ? "text-center" : ""}>
      {size === "lg" && <p className="text-[10px] uppercase tracking-widest text-gray-500 mb-2">{label}</p>}
      <div className={`relative ${size === "lg" ? "w-20 h-20" : "w-12 h-12"} mx-auto`}>
        <svg className="w-full h-full -rotate-90" viewBox="0 0 36 36">
          <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
            fill="none" stroke="#1f2937" strokeWidth="3" />
          <path d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
            fill="none" strokeWidth="3" strokeDasharray={`${pct}, 100`}
            className={score >= 75 ? 'stroke-emerald-400' : score >= 60 ? 'stroke-green-400' : score >= 45 ? 'stroke-yellow-400' : 'stroke-red-400'} />
        </svg>
        <span className={`absolute inset-0 flex items-center justify-center ${size === "lg" ? "text-xl" : "text-sm"} font-bold ${color}`}>
          {score}
        </span>
      </div>
      {size === "sm" && <p className="text-[10px] text-gray-500 text-center mt-1">{label}</p>}
    </div>
  )
}

function ComponentRow({ name, icon: Icon, score, weight, value, detail }) {
  const barColor = score >= 70 ? 'bg-emerald-500' : score >= 50 ? 'bg-yellow-500' : 'bg-red-500'
  return (
    <div className="flex items-center gap-3 py-2">
      <Icon className="w-4 h-4 text-gray-500 shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs text-gray-300 font-medium truncate">{name}</span>
          <span className="text-xs text-gray-500 font-mono ml-2">{value}</span>
        </div>
        <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
          <div className={`h-full ${barColor} rounded-full transition-all`} style={{ width: `${score}%` }} />
        </div>
      </div>
      <span className="text-xs font-mono text-gray-400 w-8 text-right">{score}</span>
    </div>
  )
}

function MiniCard({ title, value, sub, signal, signalColor }) {
  return (
    <div className="bg-gray-800/30 rounded-lg p-3 border border-gray-700/30">
      <p className="text-[10px] uppercase tracking-widest text-gray-500 mb-1">{title}</p>
      <p className="text-lg font-bold text-white">{value}</p>
      {sub && <p className="text-[11px] text-gray-400 mt-0.5">{sub}</p>}
      {signal && (
        <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded mt-1.5 inline-block ${signalColor || 'bg-gray-700 text-gray-300'}`}>
          {signal}
        </span>
      )}
    </div>
  )
}

const iconMap = {
  real_yield: DollarSign,
  dollar: DollarSign,
  supply_deficit: Droplets,
  divergence: Activity,
  flow_positioning: TrendingDown,
  geopolitical_optionality: Zap,
}

const nameMap = {
  real_yield: "Real Yield",
  dollar: "Dollar Weakness",
  supply_deficit: "Supply Deficit",
  divergence: "Spot-Equity Divergence",
  flow_positioning: "Flow Contrarian",
  geopolitical_optionality: "Geopolitical Optionality",
}

export default function AntifragilePanel() {
  const [af, setAf] = useState(null)
  const [ry, setRy] = useState(null)
  const [sed, setSed] = useState(null)
  const [fm, setFm] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      fetch('api/antifragile-score').then(r => r.json()).catch(() => null),
      fetch('api/real-yield').then(r => r.json()).catch(() => null),
      fetch('api/spot-equity-divergence').then(r => r.json()).catch(() => null),
      fetch('api/flow-momentum').then(r => r.json()).catch(() => null),
    ]).then(([a, r, s, f]) => {
      setAf(a)
      setRy(r)
      setSed(s)
      setFm(f)
      setLoading(false)
    })
  }, [])

  if (loading) {
    return (
      <div className="animate-pulse space-y-4">
        <div className="bg-gray-800/50 rounded-xl p-6 border border-gray-700/30">
          <div className="w-20 h-20 rounded-full bg-gray-700/50 mx-auto mb-4" />
          <div className="grid grid-cols-3 gap-3">
            {[1,2,3].map(i => <div key={i} className="h-16 bg-gray-700/30 rounded-lg" />)}
          </div>
        </div>
      </div>
    )
  }

  const regimeColors = {
    ANTI_FRAGILE_OPTIMAL: 'bg-emerald-900/40 border-emerald-500/40 text-emerald-400',
    FAVORABLE: 'bg-green-900/30 border-green-500/40 text-green-400',
    NEUTRAL: 'bg-yellow-900/30 border-yellow-500/40 text-yellow-400',
    DEFENSIVE: 'bg-red-900/30 border-red-500/40 text-red-400',
  }

  const awColors = {
    OPTIMAL: 'bg-emerald-900/40 text-emerald-400',
    FAVORABLE: 'bg-green-900/30 text-green-400',
    PARTIAL: 'bg-yellow-900/30 text-yellow-400',
    HEADWIND: 'bg-red-900/30 text-red-400',
  }

  const regime = af?.regime || 'NEUTRAL'
  const regimeStyle = regimeColors[regime] || regimeColors.NEUTRAL

  return (
    <div className="space-y-4">
      {/* Hero: Antifragile Score */}
      {af && (
        <div className={`rounded-xl p-5 border ${regimeStyle}`}>
          <div className="flex items-center justify-between flex-wrap gap-4">
            <div className="flex items-center gap-4">
              <ScoreGauge score={af.composite_score} label="Anti-Fragile" />
              <div>
                <p className="text-xs text-gray-500 uppercase tracking-widest">Entry Quality</p>
                <p className={`text-lg font-bold ${regimeStyle.split(' ').pop()}`}>{regime.replace(/_/g, ' ')}</p>
                <p className="text-xs text-gray-400 mt-1 max-w-md">{af.action}</p>
              </div>
            </div>
            <div className="flex gap-2">
              {Object.entries(af.components || {}).map(([k, v]) => (
                <ScoreGauge key={k} score={v.score} label={nameMap[k] || k} size="sm" />
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Detail grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Real Yield */}
        {ry && !ry.error && (
          <div className="bg-gray-800/40 border border-gray-700/30 rounded-xl p-4">
            <div className="flex items-center gap-2 mb-3">
              <DollarSign className="w-4 h-4 text-blue-400" />
              <p className="text-xs font-semibold text-gray-300 uppercase tracking-wide">Real Yield Environment</p>
            </div>
            <div className="grid grid-cols-2 gap-2 mb-3">
              <MiniCard title="Real Yield" value={`${ry.real_yield_pct}%`} sub={`Nominal: ${ry.nominal_yield_pct}%`}
                signal={ry.real_yield_regime?.replace(/_/g, ' ')}
                signalColor={ry.real_yield_regime === 'NEGATIVE_REAL' || ry.real_yield_regime === 'LOW_REAL' ? 'bg-emerald-900/40 text-emerald-400' : 'bg-yellow-900/40 text-yellow-400'} />
              <MiniCard title="Dollar" value={ry.dxy_current ? `${ry.dxy_current}` : '—'}
                sub={ry.dxy_percentile_2y != null ? `${ry.dxy_percentile_2y}th pctile (2yr)` : ''}
                signal={ry.dollar_regime} signalColor={ry.dollar_regime === 'WEAK' ? 'bg-emerald-900/40 text-emerald-400' : 'bg-yellow-900/40 text-yellow-400'} />
            </div>
            <div className={`text-xs px-2 py-1.5 rounded ${awColors[ry.all_weather_signal] || 'bg-gray-700/40 text-gray-300'}`}>
              <span className="font-bold">All-Weather: {ry.all_weather_signal}</span>
              <p className="text-[11px] opacity-80 mt-0.5">{ry.all_weather_detail}</p>
            </div>
          </div>
        )}

        {/* Spot-Equity Divergence */}
        {sed && !sed.error && (
          <div className="bg-gray-800/40 border border-gray-700/30 rounded-xl p-4">
            <div className="flex items-center gap-2 mb-3">
              <Activity className="w-4 h-4 text-purple-400" />
              <p className="text-xs font-semibold text-gray-300 uppercase tracking-wide">Spot vs Equity</p>
            </div>
            <div className="grid grid-cols-2 gap-2 mb-3">
              <MiniCard title="Z-Score" value={sed.divergence_z_score}
                signal={sed.signal?.replace(/_/g, ' ')}
                signalColor={sed.signal === 'EQUITY_CATCH_UP' ? 'bg-emerald-900/40 text-emerald-400' : sed.signal === 'SPOT_CORRECTION_RISK' ? 'bg-red-900/40 text-red-400' : 'bg-gray-700/40 text-gray-300'} />
              <MiniCard title="Current Div" value={`${sed.current_divergence_pct}%`} />
            </div>
            {sed.rolling_returns && Object.entries(sed.rolling_returns).map(([period, data]) => (
              <div key={period} className="flex items-center justify-between text-[11px] py-1 border-t border-gray-700/20">
                <span className="text-gray-500">{period}</span>
                <span className="text-gray-300">Spot: <span className={data.spot_proxy_return_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}>{data.spot_proxy_return_pct > 0 ? '+' : ''}{data.spot_proxy_return_pct}%</span></span>
                <span className="text-gray-300">URA: <span className={data.ura_return_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}>{data.ura_return_pct > 0 ? '+' : ''}{data.ura_return_pct}%</span></span>
              </div>
            ))}
            <p className="text-[11px] text-gray-500 mt-2">{sed.detail}</p>
          </div>
        )}

        {/* Flow Momentum */}
        {fm && !fm.error && (
          <div className="bg-gray-800/40 border border-gray-700/30 rounded-xl p-4">
            <div className="flex items-center gap-2 mb-3">
              <TrendingDown className="w-4 h-4 text-amber-400" />
              <p className="text-xs font-semibold text-gray-300 uppercase tracking-wide">Flow Positioning</p>
            </div>
            {Object.entries(fm.etfs || {}).map(([sym, data]) => (
              <div key={sym} className="mb-2 last:mb-0">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-mono text-gray-300">{sym}</span>
                  <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                    data.signal === 'CAPITULATION' ? 'bg-red-900/40 text-red-400' :
                    data.signal === 'FLOW_DROUGHT' ? 'bg-amber-900/40 text-amber-400' :
                    data.signal === 'BREAKOUT_CONFIRMATION' ? 'bg-emerald-900/40 text-emerald-400' :
                    'bg-gray-700/40 text-gray-300'
                  }`}>{data.signal?.replace(/_/g, ' ')}</span>
                </div>
                <div className="grid grid-cols-3 gap-1 text-[10px]">
                  <span className="text-gray-500">5d: <span className="text-gray-300">${data.dollar_volume_5d}M</span></span>
                  <span className="text-gray-500">22d: <span className="text-gray-300">${data.dollar_volume_22d}M</span></span>
                  <span className="text-gray-500">Trend: <span className={data.flow_trend_short_pct < -20 ? 'text-red-400' : data.flow_trend_short_pct > 20 ? 'text-emerald-400' : 'text-gray-300'}>{data.flow_trend_short_pct > 0 ? '+' : ''}{data.flow_trend_short_pct}%</span></span>
                </div>
              </div>
            ))}
            <div className={`text-xs px-2 py-1.5 rounded mt-3 ${
              fm.aggregate_signal === 'CAPITULATION_WATCH' ? 'bg-red-900/30 text-red-300' :
              fm.aggregate_signal === 'DISINTEREST_BOTTOM' ? 'bg-amber-900/30 text-amber-300' :
              'bg-gray-700/40 text-gray-300'
            }`}>
              <span className="font-bold">{fm.aggregate_signal?.replace(/_/g, ' ')}</span>
              <p className="text-[11px] opacity-80 mt-0.5">{fm.aggregate_detail}</p>
            </div>
          </div>
        )}
      </div>

      {/* Dalio Note */}
      {af?.dalio_note && (
        <div className="bg-blue-900/10 border border-blue-800/20 rounded-lg px-4 py-3">
          <p className="text-[11px] text-blue-300/70 leading-relaxed">
            <span className="font-semibold text-blue-400">🧠 Dalio Framework:</span> {af.dalio_note}
          </p>
        </div>
      )}
    </div>
  )
}
