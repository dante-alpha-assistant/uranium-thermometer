import { useState, useEffect } from 'react'
import { Brain, RefreshCw, AlertTriangle, TrendingUp, TrendingDown, Minus, Clock, Zap, Shield, Target, Eye } from 'lucide-react'

const outlookConfig = {
  bullish: { color: 'text-emerald-400', bg: 'bg-emerald-900/30', border: 'border-emerald-500/40', icon: TrendingUp, label: 'BULLISH' },
  neutral: { color: 'text-yellow-400', bg: 'bg-yellow-900/30', border: 'border-yellow-500/40', icon: Minus, label: 'NEUTRAL' },
  bearish: { color: 'text-red-400', bg: 'bg-red-900/30', border: 'border-red-500/40', icon: TrendingDown, label: 'BEARISH' },
}

const regimeConfig = {
  'risk-on': { color: 'text-emerald-400', bg: 'bg-emerald-900/40', label: 'RISK-ON' },
  'risk-off': { color: 'text-red-400', bg: 'bg-red-900/40', label: 'RISK-OFF' },
  'transitioning': { color: 'text-amber-400', bg: 'bg-amber-900/40', label: 'TRANSITIONING' },
  'uncertain': { color: 'text-gray-400', bg: 'bg-gray-800/60', label: 'UNCERTAIN' },
}

const convictionConfig = {
  high: { color: 'text-emerald-400', bars: 3 },
  medium: { color: 'text-yellow-400', bars: 2 },
  low: { color: 'text-red-400', bars: 1 },
}

function TimeframeCard({ data, horizon }) {
  if (!data) return null
  const cfg = outlookConfig[data.outlook] || outlookConfig.neutral
  const Icon = cfg.icon

  return (
    <div className={`${cfg.bg} ${cfg.border} border rounded-xl p-5 flex flex-col h-full`}>
      <div className="flex items-center justify-between mb-3">
        <div>
          <p className="text-[10px] uppercase tracking-widest text-gray-500 font-mono">{horizon}</p>
          <p className="text-xs text-gray-400 mt-0.5">{data.horizon}</p>
        </div>
        <div className={`flex items-center gap-1.5 px-3 py-1 rounded-full ${cfg.bg} border ${cfg.border}`}>
          <Icon className={`w-3.5 h-3.5 ${cfg.color}`} />
          <span className={`text-xs font-bold tracking-wide ${cfg.color}`}>{cfg.label}</span>
        </div>
      </div>

      <p className="text-sm text-gray-300 leading-relaxed mb-4 min-h-[4.5rem]">{data.hypothesis}</p>

      <div className="space-y-3 mt-auto">
        <div>
          <p className="text-[10px] uppercase tracking-widest text-gray-500 mb-2">Key Drivers</p>
          <div className="flex flex-wrap gap-2">
            {(data.key_drivers || []).map((d, i) => (
              <span key={i} className="text-sm px-3.5 py-2 rounded-lg bg-gray-800/80 text-gray-200 border border-gray-700/50 leading-snug">
                {d}
              </span>
            ))}
          </div>
        </div>

        <div>
          <p className="text-[10px] uppercase tracking-widest text-gray-500 mb-2">Risks</p>
          <div className="flex flex-wrap gap-2">
            {(data.risk_factors || []).map((r, i) => (
              <span key={i} className="text-sm px-3.5 py-2 rounded-lg bg-red-900/20 text-red-200/90 border border-red-800/30 leading-snug">
                {r}
              </span>
            ))}
          </div>
        </div>

        {data.actionable && (
          <div className="mt-2 pt-3 border-t border-gray-700/30">
            <div className="flex items-start gap-2">
              <Target className="w-4 h-4 text-blue-400 mt-0.5 shrink-0" />
              <p className="text-sm text-blue-300/90 leading-relaxed">{data.actionable}</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default function AIAnalysis() {
  const [analysis, setAnalysis] = useState(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState(null)

  const fetchAnalysis = async (force = false, retries = 2) => {
    try {
      if (force) setRefreshing(true)
      else setLoading(true)
      setError(null)
      const url = force ? 'api/ai-analysis?force=true' : 'api/ai-analysis'
      const res = await fetch(url)
      const text = await res.text()
      // Guard against HTML responses (SPA fallback during restart)
      if (text.startsWith('<!') || text.startsWith('<html')) {
        if (retries > 0) {
          await new Promise(r => setTimeout(r, 3000))
          return fetchAnalysis(force, retries - 1)
        }
        setError('Service restarting — try again in a moment')
        return
      }
      const data = JSON.parse(text)
      if (data.error) {
        setError(data.error)
      } else {
        setAnalysis(data)
      }
    } catch (e) {
      if (retries > 0) {
        await new Promise(r => setTimeout(r, 3000))
        return fetchAnalysis(force, retries - 1)
      }
      setError('Failed to load AI analysis — try refreshing')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => { fetchAnalysis() }, [])

  // Loading skeleton
  if (loading) {
    return (
      <div className="space-y-4 animate-pulse">
        <div className="bg-gray-800/50 rounded-xl p-6 border border-gray-700/30">
          <div className="flex items-center gap-3 mb-4">
            <div className="w-10 h-10 rounded-lg bg-gray-700/50" />
            <div className="space-y-2">
              <div className="w-48 h-4 bg-gray-700/50 rounded" />
              <div className="w-32 h-3 bg-gray-700/30 rounded" />
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {[1, 2, 3].map(i => (
              <div key={i} className="bg-gray-800/30 rounded-xl p-5 border border-gray-700/20 space-y-3">
                <div className="w-24 h-3 bg-gray-700/30 rounded" />
                <div className="w-full h-16 bg-gray-700/20 rounded" />
                <div className="w-full h-8 bg-gray-700/20 rounded" />
              </div>
            ))}
          </div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="bg-red-900/20 border border-red-800/30 rounded-xl p-4 text-sm text-red-300">
        <AlertTriangle className="w-4 h-4 inline mr-2" />
        {error}
      </div>
    )
  }

  if (!analysis) return null

  const regime = regimeConfig[analysis.market_regime] || regimeConfig.uncertain
  const conviction = convictionConfig[analysis.conviction_level] || convictionConfig.low
  const updatedAt = analysis.generated_at ? new Date(analysis.generated_at) : null
  const timeAgo = updatedAt ? getTimeAgo(updatedAt) : null

  return (
    <div className="space-y-4">
      {/* Hero: Regime + Conviction */}
      <div className="bg-gradient-to-r from-gray-800/60 via-gray-800/40 to-gray-800/60 rounded-xl p-5 border border-gray-700/30">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-4">
            <div className="w-10 h-10 rounded-lg bg-indigo-900/40 border border-indigo-500/30 flex items-center justify-center">
              <Brain className="w-5 h-5 text-indigo-400" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-lg font-bold text-white">AI Market Intelligence</h3>
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-900/40 text-indigo-400 border border-indigo-500/30 font-mono">
                  {analysis.model || 'opus'}
                </span>
              </div>
              <p className="text-xs text-gray-500">
                {analysis.data_sources} data sources analyzed
                {timeAgo && <> · Updated {timeAgo}</>}
                {analysis.cached && <span className="ml-1 text-gray-600">(cached)</span>}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-4">
            {/* Market Regime */}
            <div className="text-center">
              <p className="text-[10px] uppercase tracking-widest text-gray-500 mb-1">Regime</p>
              <span className={`text-xs font-bold px-3 py-1 rounded-full ${regime.bg} ${regime.color} border border-current/20`}>
                {regime.label}
              </span>
            </div>

            {/* Conviction */}
            <div className="text-center">
              <p className="text-[10px] uppercase tracking-widest text-gray-500 mb-1">Conviction</p>
              <div className="flex items-center gap-1 justify-center">
                {[1, 2, 3].map(i => (
                  <div key={i}
                    className={`w-5 h-2 rounded-sm ${i <= conviction.bars ? '' : 'bg-gray-700/40'}`}
                    style={i <= conviction.bars ? {
                      backgroundColor: conviction.color.includes('emerald') ? '#10b981' :
                        conviction.color.includes('yellow') ? '#eab308' : '#ef4444'
                    } : {}}
                  />
                ))}
                <span className={`text-xs font-mono ml-1 ${conviction.color}`}>
                  {(analysis.conviction_level || '').toUpperCase()}
                </span>
              </div>
            </div>

            {/* Refresh */}
            <button
              onClick={() => fetchAnalysis(true)}
              disabled={refreshing}
              className="p-2 rounded-lg bg-gray-800 hover:bg-gray-700 border border-gray-700/50 text-gray-400 hover:text-white transition-all disabled:opacity-50"
              title="Refresh analysis (4h cache)"
            >
              <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>
      </div>

      {/* 3 Timeframe Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <TimeframeCard data={analysis.short_term} horizon="Short Term" />
        <TimeframeCard data={analysis.medium_term} horizon="Medium Term" />
        <TimeframeCard data={analysis.long_term} horizon="Long Term" />
      </div>

      {/* Signal Conflicts */}
      {analysis.signal_conflicts && analysis.signal_conflicts.length > 0 && (
        <div className="bg-amber-900/15 border border-amber-700/30 rounded-xl p-5">
          <div className="flex items-center gap-2 mb-3">
            <Zap className="w-4 h-4 text-amber-400" />
            <h4 className="text-sm font-semibold text-amber-400 uppercase tracking-wide">Signal Conflicts</h4>
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-900/40 text-amber-500 font-mono">
              {analysis.signal_conflicts.length}
            </span>
          </div>
          <div className="space-y-2">
            {analysis.signal_conflicts.map((conflict, i) => (
              <div key={i} className="flex items-start gap-2">
                <span className="text-amber-500 mt-0.5">⚡</span>
                <p className="text-sm text-amber-200/80 leading-relaxed">{conflict}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Bottom row: Picks + Contrarian + Dalio */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Top Pick & Avoid */}
        <div className="bg-gray-800/40 border border-gray-700/30 rounded-xl p-5 space-y-4">
          {analysis.top_pick && (
            <div>
              <div className="flex items-center gap-2 mb-1.5">
                <TrendingUp className="w-3.5 h-3.5 text-emerald-400" />
                <p className="text-[10px] uppercase tracking-widest text-emerald-500 font-semibold">Top Pick</p>
              </div>
              <p className="text-sm text-gray-300 leading-relaxed">{analysis.top_pick}</p>
            </div>
          )}
          {analysis.avoid && (
            <div>
              <div className="flex items-center gap-2 mb-1.5">
                <Shield className="w-3.5 h-3.5 text-red-400" />
                <p className="text-[10px] uppercase tracking-widest text-red-500 font-semibold">Avoid</p>
              </div>
              <p className="text-sm text-gray-300 leading-relaxed">{analysis.avoid}</p>
            </div>
          )}
        </div>

        {/* Contrarian View */}
        {analysis.contrarian_view && (
          <div className="bg-red-900/10 border border-red-800/25 rounded-xl p-5">
            <div className="flex items-center gap-2 mb-2">
              <Eye className="w-3.5 h-3.5 text-red-400" />
              <p className="text-[10px] uppercase tracking-widest text-red-500 font-semibold">Contrarian View</p>
            </div>
            <p className="text-sm text-red-200/70 leading-relaxed">{analysis.contrarian_view}</p>
          </div>
        )}

        {/* Dalio Verdict */}
        {analysis.dalio_verdict && (
          <div className="bg-blue-900/10 border border-blue-800/25 rounded-xl p-5">
            <div className="flex items-center gap-2 mb-2">
              <Brain className="w-3.5 h-3.5 text-blue-400" />
              <p className="text-[10px] uppercase tracking-widest text-blue-500 font-semibold">Dalio Framework</p>
            </div>
            <p className="text-sm text-blue-200/70 leading-relaxed">{analysis.dalio_verdict}</p>
          </div>
        )}
      </div>
    </div>
  )
}

function getTimeAgo(date) {
  const seconds = Math.floor((new Date() - date) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}
