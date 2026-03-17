import { useState, useEffect } from 'react'
import { Zap, TrendingUp, TrendingDown, Minus, AlertTriangle, Shield } from 'lucide-react'

export default function DailyDigest() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetch('api/daily-digest')
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false) })
      .catch(e => { setError(e.message); setLoading(false) })
  }, [])

  if (loading) return <div className="bg-zinc-900/60 border border-zinc-800 rounded-2xl p-6 animate-pulse h-64" />
  if (error) return <div className="bg-red-900/20 border border-red-800 rounded-2xl p-4 text-red-400 text-sm">Daily Digest: {error}</div>
  if (!data) return null

  const macro = data.macro_context || {}
  const action = data.action_summary || {}
  const top3 = (data.top_3 || []).slice(0, 3)

  const regimeColors = {
    BULL_QUIET: 'text-emerald-400 bg-emerald-400/10',
    BULL_VOLATILE: 'text-yellow-400 bg-yellow-400/10',
    SIDEWAYS: 'text-zinc-400 bg-zinc-400/10',
    BEAR_QUIET: 'text-orange-400 bg-orange-400/10',
    BEAR_VOLATILE: 'text-red-400 bg-red-400/10',
  }

  const macroColors = {
    RISK_ON: 'text-emerald-400',
    LEAN_RISK_ON: 'text-emerald-300',
    NEUTRAL: 'text-zinc-400',
    LEAN_RISK_OFF: 'text-orange-400',
    RISK_OFF: 'text-red-400',
  }

  const actionColor = (a) => {
    if (!a) return 'text-zinc-400'
    const al = a.toLowerCase()
    if (al.includes('buy') || al.includes('strong_buy')) return 'text-emerald-400'
    if (al.includes('sell')) return 'text-red-400'
    if (al.includes('hold')) return 'text-yellow-400'
    return 'text-zinc-400'
  }

  return (
    <div className="bg-zinc-900/60 border border-zinc-800 rounded-2xl p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Zap className="w-5 h-5 text-indigo-400" />
          <h3 className="text-base font-bold text-zinc-100">Daily Digest</h3>
        </div>
        <span className="text-[10px] text-zinc-600">{data.timestamp?.split('T')[0]}</span>
      </div>

      {/* Sector + Macro row */}
      <div className="grid grid-cols-2 gap-3">
        <div className="bg-zinc-800/50 rounded-xl p-4">
          <div className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1">Sector Score</div>
          <div className="text-2xl font-bold text-zinc-100">{data.sector_avg_score}</div>
          <div className="text-xs text-zinc-400 mt-1">{data.sector_view}</div>
        </div>
        <div className="bg-zinc-800/50 rounded-xl p-4">
          <div className="text-[10px] text-zinc-500 uppercase tracking-wider mb-1">Macro</div>
          <div className={`text-2xl font-bold ${macroColors[macro.macro_label] || 'text-zinc-400'}`}>
            {macro.macro_score || '—'}
          </div>
          <div className="flex items-center gap-2 mt-1">
            <span className={`text-[10px] px-2 py-0.5 rounded-full ${regimeColors[macro.regime] || 'text-zinc-400 bg-zinc-800'}`}>
              {macro.regime?.replace('_', ' ') || '—'}
            </span>
            <span className="text-[10px] text-zinc-500">{macro.position_sizing_multiplier}x size</span>
          </div>
        </div>
      </div>

      {/* Action summary pills */}
      <div className="flex gap-2">
        {action.buy > 0 && <span className="text-xs px-3 py-1 rounded-full bg-emerald-400/10 text-emerald-400 font-medium">{action.buy} BUY</span>}
        {action.hold > 0 && <span className="text-xs px-3 py-1 rounded-full bg-yellow-400/10 text-yellow-400 font-medium">{action.hold} HOLD</span>}
        {action.wait > 0 && <span className="text-xs px-3 py-1 rounded-full bg-zinc-400/10 text-zinc-400 font-medium">{action.wait} WAIT</span>}
        {action.sell > 0 && <span className="text-xs px-3 py-1 rounded-full bg-red-400/10 text-red-400 font-medium">{action.sell} SELL</span>}
      </div>

      {/* Top 3 trades */}
      {top3.length > 0 && (
        <div>
          <div className="text-[10px] text-zinc-500 uppercase tracking-wider mb-2">Top Opportunities</div>
          <div className="space-y-2">
            {top3.map((t, i) => (
              <div key={i} className="flex items-center justify-between bg-zinc-800/30 rounded-lg px-3 py-2">
                <div className="flex items-center gap-3">
                  <span className="text-xs font-mono font-bold text-zinc-200 w-16">{t.symbol}</span>
                  <span className={`text-[10px] font-bold uppercase ${actionColor(t.action)}`}>{t.action}</span>
                </div>
                <div className="flex items-center gap-4 text-[11px]">
                  <span className="text-zinc-400">Score <span className="text-zinc-200">{t.composite_score?.toFixed(0) || t.score?.toFixed(0) || '—'}</span></span>
                  {t.entry && <span className="text-zinc-400">${t.entry?.toFixed(2)}</span>}
                  {t.confidence && <span className="text-zinc-500">{t.confidence}% conf</span>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Macro headwinds/tailwinds */}
      {(macro.headwinds?.length > 0 || macro.tailwinds?.length > 0) && (
        <div className="flex gap-4 text-[11px]">
          {macro.tailwinds?.length > 0 && (
            <div className="flex items-center gap-1 text-emerald-400/70">
              <TrendingUp className="w-3 h-3" />
              {macro.tailwinds.join(', ')}
            </div>
          )}
          {macro.headwinds?.length > 0 && (
            <div className="flex items-center gap-1 text-red-400/70">
              <TrendingDown className="w-3 h-3" />
              {macro.headwinds.join(', ')}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
