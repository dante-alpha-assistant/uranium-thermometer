import { useState, useEffect } from 'react'
import { Brain, RefreshCw, AlertTriangle, TrendingUp, TrendingDown, Minus, Target, Zap, Shield, Eye, ChevronDown, ChevronRight } from 'lucide-react'

const outlookConfig = {
  bullish: { color: 'text-emerald-400', icon: TrendingUp, label: 'BULLISH' },
  neutral: { color: 'text-zinc-400', icon: Minus, label: 'NEUTRAL' },
  bearish: { color: 'text-red-400', icon: TrendingDown, label: 'BEARISH' },
}

const regimeConfig = {
  'risk-on': { color: 'text-emerald-400', label: 'RISK-ON' },
  'risk-off': { color: 'text-red-400', label: 'RISK-OFF' },
  'transitioning': { color: 'text-zinc-400', label: 'TRANSITIONING' },
  'uncertain': { color: 'text-zinc-500', label: 'UNCERTAIN' },
}

const convictionConfig = {
  high: { color: '#34d399', bars: 3 },
  medium: { color: '#fbbf24', bars: 2 },
  low: { color: '#f87171', bars: 1 },
}

function TimeframeRow({ data, horizon }) {
  const [expanded, setExpanded] = useState(false)
  if (!data) return null
  const cfg = outlookConfig[data.outlook] || outlookConfig.neutral
  const Icon = cfg.icon

  return (
    <div className="u-card p-5">
      <button onClick={() => setExpanded(!expanded)} className="w-full text-left">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Icon className={`w-4 h-4 ${cfg.color}`} />
            <div>
              <span className="text-sm font-semibold text-zinc-200">{horizon}</span>
              <span className="text-xs text-zinc-600 ml-2">{data.horizon}</span>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className={`text-xs font-bold font-mono tracking-wide ${cfg.color}`}>{cfg.label}</span>
            {expanded ? <ChevronDown className="w-3.5 h-3.5 text-zinc-600" /> : <ChevronRight className="w-3.5 h-3.5 text-zinc-600" />}
          </div>
        </div>
      </button>

      {expanded && (
        <div className="mt-4 pt-4 border-t border-zinc-800/50 space-y-4 animate-fade-in">
          <p className="text-sm text-zinc-400 leading-relaxed">{data.hypothesis}</p>

          {data.key_drivers?.length > 0 && (
            <div>
              <p className="text-[10px] uppercase tracking-widest text-zinc-400 mb-2">Key Drivers</p>
              <div className="flex flex-wrap gap-1.5">
                {data.key_drivers.map((d, i) => (
                  <span key={i} className="text-xs px-2.5 py-1 rounded-lg bg-zinc-800/60 text-zinc-300">{d}</span>
                ))}
              </div>
            </div>
          )}

          {data.risk_factors?.length > 0 && (
            <div>
              <p className="text-[10px] uppercase tracking-widest text-zinc-400 mb-2">Risks</p>
              <div className="flex flex-wrap gap-1.5">
                {data.risk_factors.map((r, i) => (
                  <span key={i} className="text-xs px-2.5 py-1 rounded-lg bg-red-950/30 text-red-300/80">{r}</span>
                ))}
              </div>
            </div>
          )}

          {data.actionable && (
            <div className="flex items-start gap-2 pt-2">
              <Target className="w-3.5 h-3.5 text-indigo-400 mt-0.5 shrink-0" />
              <p className="text-sm text-indigo-300/80 leading-relaxed">{data.actionable}</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export default function AIAnalysis() {
  const [analysis, setAnalysis] = useState(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState(null)
  const [showDetails, setShowDetails] = useState(false)

  const fetchAnalysis = async (force = false, retries = 2) => {
    try {
      if (force) setRefreshing(true)
      else setLoading(true)
      setError(null)
      const url = force ? 'api/ai-analysis?force=true' : 'api/ai-analysis'
      const res = await fetch(url)
      const text = await res.text()
      if (text.startsWith('<!') || text.startsWith('<html')) {
        if (retries > 0) { await new Promise(r => setTimeout(r, 3000)); return fetchAnalysis(force, retries - 1) }
        setError('Service restarting'); return
      }
      const data = JSON.parse(text)
      if (data.error) setError(data.error)
      else setAnalysis(data)
    } catch (e) {
      if (retries > 0) { await new Promise(r => setTimeout(r, 3000)); return fetchAnalysis(force, retries - 1) }
      setError('Failed to load AI analysis')
    } finally { setLoading(false); setRefreshing(false) }
  }

  useEffect(() => { fetchAnalysis() }, [])

  if (loading) {
    return (
      <div className="u-card p-6 animate-pulse">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-zinc-800/60" />
          <div className="space-y-2 flex-1">
            <div className="w-48 h-4 bg-zinc-800/60 rounded" />
            <div className="w-32 h-3 bg-zinc-800/40 rounded" />
          </div>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="u-card p-5 flex items-center gap-3 text-sm text-red-300/80">
        <AlertTriangle className="w-4 h-4 text-red-400/60" />
        {error}
      </div>
    )
  }

  if (!analysis) return null

  const regime = regimeConfig[analysis.market_regime] || regimeConfig.uncertain
  const conviction = convictionConfig[analysis.conviction_level] || convictionConfig.low
  const updatedAt = analysis.generated_at ? new Date(analysis.generated_at) : null
  const timeAgo = updatedAt ? getTimeAgo(updatedAt) : null

  // Summary outlook pills
  const outlooks = [
    { label: 'Short', data: analysis.short_term },
    { label: 'Medium', data: analysis.medium_term },
    { label: 'Long', data: analysis.long_term },
  ]

  return (
    <div className="space-y-3">
      {/* Compact hero bar — always visible */}
      <div className="u-card p-5">
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div className="flex items-center gap-4">
            <div className="w-10 h-10 rounded-xl flex items-center justify-center" style={{ background: 'var(--accent-dim)' }}>
              <Brain className="w-5 h-5" style={{ color: 'var(--accent)' }} />
            </div>
            <div>
              <h3 className="text-base font-bold text-zinc-100">AI Intelligence</h3>
              <p className="text-xs text-zinc-400 mt-0.5">
                {analysis.data_sources} sources · {timeAgo || 'recent'}
                {analysis.cached && ' · cached'}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-6">
            {/* Regime pill */}
            <div className="text-center">
              <p className="text-[10px] uppercase tracking-widest text-zinc-400 mb-1">Regime</p>
              <span className={`text-xs font-bold font-mono ${regime.color}`}>{regime.label}</span>
            </div>

            {/* Conviction bars */}
            <div className="text-center">
              <p className="text-[10px] uppercase tracking-widest text-zinc-400 mb-1">Conviction</p>
              <div className="flex items-center gap-0.5 justify-center">
                {[1, 2, 3].map(i => (
                  <div key={i} className="w-4 h-1.5 rounded-sm"
                    style={{ backgroundColor: i <= conviction.bars ? conviction.color : 'rgba(255,255,255,0.06)' }} />
                ))}
              </div>
            </div>

            {/* Outlook summary pills */}
            <div className="hidden sm:flex items-center gap-2">
              {outlooks.map(({ label, data }) => {
                if (!data) return null
                const cfg = outlookConfig[data.outlook] || outlookConfig.neutral
                return (
                  <div key={label} className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-zinc-800/40">
                    <span className="text-[10px] text-zinc-500">{label}</span>
                    <span className={`text-[10px] font-bold font-mono ${cfg.color}`}>{cfg.label}</span>
                  </div>
                )
              })}
            </div>

            {/* Expand + Refresh */}
            <div className="flex items-center gap-1.5">
              <button onClick={() => setShowDetails(!showDetails)}
                className="p-2 rounded-lg hover:bg-zinc-800/60 text-zinc-500 hover:text-zinc-300 transition-colors">
                {showDetails ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
              </button>
              <button onClick={() => fetchAnalysis(true)} disabled={refreshing}
                className="p-2 rounded-lg hover:bg-zinc-800/60 text-zinc-500 hover:text-zinc-300 transition-colors disabled:opacity-40">
                <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Expanded details */}
      {showDetails && (
        <div className="space-y-3 animate-fade-in">
          {/* Timeframe cards — each collapsible */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <TimeframeRow data={analysis.short_term} horizon="Short Term" />
            <TimeframeRow data={analysis.medium_term} horizon="Medium Term" />
            <TimeframeRow data={analysis.long_term} horizon="Long Term" />
          </div>

          {/* Signal Conflicts */}
          {analysis.signal_conflicts?.length > 0 && (
            <div className="u-card p-5">
              <div className="flex items-center gap-2 mb-3">
                <Zap className="w-4 h-4 text-zinc-400" />
                <span className="text-sm font-semibold text-zinc-300">Signal Conflicts</span>
                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-zinc-800/60 text-zinc-500">{analysis.signal_conflicts.length}</span>
              </div>
              <div className="space-y-2">
                {analysis.signal_conflicts.map((c, i) => (
                  <p key={i} className="text-sm text-zinc-400 leading-relaxed pl-6 relative">
                    <span className="absolute left-0 text-zinc-400">—</span>
                    {c}
                  </p>
                ))}
              </div>
            </div>
          )}

          {/* Bottom row: Picks + Contrarian + Dalio */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className="u-card p-5 space-y-4">
              {analysis.top_pick && (
                <div>
                  <p className="text-[10px] uppercase tracking-widest text-emerald-500/60 font-semibold mb-1.5">Top Pick</p>
                  <p className="text-sm text-zinc-300 leading-relaxed">{analysis.top_pick}</p>
                </div>
              )}
              {analysis.avoid && (
                <div>
                  <p className="text-[10px] uppercase tracking-widest text-red-400/60 font-semibold mb-1.5">Avoid</p>
                  <p className="text-sm text-zinc-300 leading-relaxed">{analysis.avoid}</p>
                </div>
              )}
            </div>

            {analysis.contrarian_view && (
              <div className="u-card p-5">
                <p className="text-[10px] uppercase tracking-widest text-zinc-600 font-semibold mb-2">Contrarian View</p>
                <p className="text-sm text-zinc-400 leading-relaxed">{analysis.contrarian_view}</p>
              </div>
            )}

            {analysis.dalio_verdict && (
              <div className="u-card p-5">
                <p className="text-[10px] uppercase tracking-widest text-zinc-600 font-semibold mb-2">Dalio Framework</p>
                <p className="text-sm text-zinc-400 leading-relaxed">{analysis.dalio_verdict}</p>
              </div>
            )}
          </div>
        </div>
      )}
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
