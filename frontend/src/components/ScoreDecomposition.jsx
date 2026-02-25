import { useState, useEffect } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'

const SIGNAL_DOTS = { BUY: '🟢', SELL: '🔴', NEUTRAL: '⚪' }
const CAT_LABELS = {
  technical: { label: 'Technical', icon: '📊', color: 'text-indigo-400' },
  macro: { label: 'Macro', icon: '🌍', color: 'text-amber-400' },
  fundamental: { label: 'Fundamental', icon: '💎', color: 'text-emerald-400' },
  sentiment: { label: 'Sentiment', icon: '📡', color: 'text-cyan-400' },
}

function ScoreBar({ score }) {
  const color = score >= 60 ? 'bg-emerald-500' : score <= 40 ? 'bg-red-500' : 'bg-amber-500'
  return (
    <div className="flex items-center gap-1.5 flex-1">
      <div className="flex-1 h-1.5 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.04)' }}>
        <div className={`h-full rounded-full ${color} transition-all duration-500`} style={{ width: `${score}%`, opacity: 0.7 }} />
      </div>
      <span className="font-mono text-[10px] text-zinc-300 w-6 text-right">{Math.round(score)}</span>
    </div>
  )
}

function CategorySummary({ cat, data }) {
  const info = CAT_LABELS[cat] || { label: cat, icon: '•', color: 'text-zinc-400' }
  if (!data) return null
  const scoreColor = data.score >= 60 ? 'text-emerald-400' : data.score <= 40 ? 'text-red-400' : 'text-zinc-300'
  return (
    <div className="flex items-center gap-2 p-2 rounded-lg" style={{ background: 'rgba(255,255,255,0.02)' }}>
      <span className="text-sm">{info.icon}</span>
      <span className={`text-xs font-medium ${info.color} w-20`}>{info.label}</span>
      <div className="flex-1 h-1.5 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.04)' }}>
        <div
          className={`h-full rounded-full transition-all ${data.score >= 60 ? 'bg-emerald-500' : data.score <= 40 ? 'bg-red-500' : 'bg-amber-500'}`}
          style={{ width: `${data.score}%`, opacity: 0.6 }}
        />
      </div>
      <span className={`font-mono text-sm font-bold w-8 text-right ${scoreColor}`}>{data.score}</span>
      <span className="text-[10px] text-zinc-600 w-8 text-right">{data.weight}</span>
    </div>
  )
}

export default function ScoreDecomposition({ symbol = 'URA' }) {
  const [data, setData] = useState(null)
  const [open, setOpen] = useState(true)
  const [expandedCat, setExpandedCat] = useState(null)
  const [sym, setSym] = useState(symbol)

  useEffect(() => {
    fetch(`api/score-decomposition?symbol=${sym}`)
      .then(r => r.json())
      .then(setData)
      .catch(() => {})
  }, [sym])

  if (!data) return null

  const tickers = ['URA', 'CCJ', 'UEC', 'UUUU', 'DNN', 'NXE', 'OKLO', 'LEU', 'PDN.AX', 'U-UN.TO']
  const scoreColor = data.total_score >= 60 ? 'var(--green)' : data.total_score <= 40 ? 'var(--red)' : 'var(--yellow)'
  const cats = data.categories || {}
  const bullish = data.summary?.bullish_signals || []
  const bearish = data.summary?.bearish_signals || []
  const totalSignals = data.summary?.total_signals || 0

  return (
    <div className="u-card p-5">
      <button onClick={() => setOpen(!open)} className="w-full text-left">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-14 h-14 rounded-xl flex flex-col items-center justify-center"
              style={{ background: scoreColor + '18' }}>
              <span className="font-mono font-bold text-xl" style={{ color: scoreColor }}>{data.total_score}</span>
              <span className="text-[8px] text-zinc-500 -mt-0.5">/ 100</span>
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-zinc-200">Composite Score</span>
                <span className="text-xs font-mono font-bold px-2 py-0.5 rounded" style={{ color: scoreColor, background: scoreColor + '15' }}>
                  {data.label}
                </span>
              </div>
              <p className="text-xs text-zinc-500 mt-0.5">
                {totalSignals} signals · {bullish.length} bullish · {bearish.length} bearish
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <div className="hidden sm:flex gap-1">
              {tickers.map(t => (
                <button
                  key={t}
                  onClick={(e) => { e.stopPropagation(); setSym(t) }}
                  className={`px-2 py-0.5 rounded text-[10px] font-mono transition-colors ${sym === t ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-600 hover:text-zinc-400'}`}
                >
                  {t}
                </button>
              ))}
            </div>
            {open ? <ChevronDown className="w-4 h-4 text-zinc-600" /> : <ChevronRight className="w-4 h-4 text-zinc-600" />}
          </div>
        </div>
      </button>

      {open && (
        <div className="mt-5 space-y-4 animate-fade-in">
          {/* Category overview */}
          <div className="space-y-1.5">
            {['technical', 'macro', 'fundamental', 'sentiment'].map(cat => (
              <div key={cat}>
                <button className="w-full" onClick={() => setExpandedCat(expandedCat === cat ? null : cat)}>
                  <CategorySummary cat={cat} data={cats[cat]} />
                </button>

                {expandedCat === cat && (
                  <div className="ml-7 mt-1 mb-2 space-y-0.5 animate-fade-in">
                    {data.components.filter(c => c.category === cat).map(c => (
                      <div key={c.name} className="flex items-center gap-2 py-1 px-2 rounded hover:bg-zinc-800/30 transition-colors">
                        <span className="text-[10px] text-zinc-400 w-24 truncate" title={c.name}>
                          {c.name.replace(/_/g, ' ')}
                        </span>
                        <span className="text-[9px] font-mono text-zinc-600 w-8">{(c.weight * 100).toFixed(0)}%</span>
                        <ScoreBar score={c.score} />
                        <span className="text-[10px]">{SIGNAL_DOTS[c.signal]}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Full component table */}
          <details className="group">
            <summary className="text-[10px] uppercase tracking-wider text-zinc-600 cursor-pointer hover:text-zinc-400 transition-colors">
              All {totalSignals} signals ▸
            </summary>
            <div className="mt-2 space-y-0.5">
              {data.components.map(c => {
                const catInfo = CAT_LABELS[c.category] || {}
                return (
                  <div key={c.name} className="flex items-center gap-2 py-1.5 px-2 rounded-lg hover:bg-zinc-800/20 transition-colors text-xs">
                    <span className="text-[10px]">{catInfo.icon || '•'}</span>
                    <span className="text-zinc-300 w-28 truncate font-medium" title={c.detail}>
                      {c.name.replace(/_/g, ' ')}
                    </span>
                    <span className="text-[10px] font-mono text-zinc-600 w-8">{(c.weight * 100).toFixed(0)}%</span>
                    <ScoreBar score={c.score} />
                    <span className="text-[10px] font-mono text-zinc-500 w-20 text-right truncate" title={typeof c.raw_value === 'object' ? JSON.stringify(c.raw_value) : String(c.raw_value)}>
                      {typeof c.raw_value === 'object' ? `${c.raw_value}` : c.raw_value}
                    </span>
                    <span className="text-[10px]">{SIGNAL_DOTS[c.signal]}</span>
                  </div>
                )
              })}
            </div>
          </details>

          {/* Detail text */}
          <div className="pt-2 border-t space-y-0.5" style={{ borderColor: 'var(--border)' }}>
            {data.components.filter(c => c.signal !== 'NEUTRAL').map(c => (
              <p key={c.name} className="text-[10px] text-zinc-500 leading-relaxed">
                {SIGNAL_DOTS[c.signal]} <span className="text-zinc-400">{c.name.replace(/_/g, ' ')}:</span> {c.detail}
              </p>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// Lightweight tooltip version for ticker cards
export function ScoreTooltip({ symbol }) {
  const [data, setData] = useState(null)
  const [visible, setVisible] = useState(false)

  const load = () => {
    if (!data) {
      fetch(`api/score-decomposition?symbol=${symbol}`)
        .then(r => r.json())
        .then(setData)
        .catch(() => {})
    }
    setVisible(true)
  }

  return (
    <div className="relative inline-block" onMouseEnter={load} onMouseLeave={() => setVisible(false)}>
      <span className="cursor-help border-b border-dotted border-zinc-700">{data?.total_score ?? '...'}</span>
      {visible && data && (
        <div className="absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-2 w-64 bg-zinc-900 border border-zinc-700 rounded-lg p-3 shadow-xl animate-fade-in">
          <div className="flex items-center justify-between mb-2">
            <span className="font-mono text-sm font-bold text-zinc-200">{data.symbol}</span>
            <span className="text-xs font-bold" style={{
              color: data.total_score >= 60 ? 'var(--green)' : data.total_score <= 40 ? 'var(--red)' : 'var(--yellow)'
            }}>{data.label}</span>
          </div>

          {/* Category scores */}
          <div className="space-y-1 mb-2">
            {['technical', 'macro', 'fundamental', 'sentiment'].map(cat => {
              const c = data.categories?.[cat]
              if (!c) return null
              const info = CAT_LABELS[cat]
              return (
                <div key={cat} className="flex items-center justify-between text-[10px]">
                  <span className="text-zinc-400">{info.icon} {info.label}</span>
                  <div className="flex items-center gap-1.5">
                    <div className="w-12 h-1.5 rounded-full overflow-hidden bg-zinc-800">
                      <div
                        className={`h-full rounded-full ${c.score >= 60 ? 'bg-emerald-500' : c.score <= 40 ? 'bg-red-500' : 'bg-amber-500'}`}
                        style={{ width: `${c.score}%`, opacity: 0.7 }}
                      />
                    </div>
                    <span className="font-mono text-zinc-300 w-6 text-right">{c.score}</span>
                  </div>
                </div>
              )
            })}
          </div>

          {/* Top signals */}
          <div className="pt-1.5 border-t space-y-0.5" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
            {data.components.filter(c => c.signal !== 'NEUTRAL').slice(0, 5).map(c => (
              <div key={c.name} className="flex items-center justify-between text-[10px]">
                <span className="text-zinc-400">{c.name.replace(/_/g, ' ')}</span>
                <span>{SIGNAL_DOTS[c.signal]}</span>
              </div>
            ))}
          </div>
          <div className="absolute left-1/2 -translate-x-1/2 top-full w-2 h-2 bg-zinc-900 border-b border-r border-zinc-700 rotate-45 -mt-1" />
        </div>
      )}
    </div>
  )
}
