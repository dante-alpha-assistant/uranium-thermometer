import { useState, useRef, useCallback, useEffect } from 'react'

export default function TickerGrid({ tickers, onSelect }) {
  if (!tickers || tickers.length === 0) return null

  return (
    <div>
      <p className="text-xs uppercase tracking-wider text-zinc-400 mb-4">Uranium Stocks</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {tickers.map(t => (
          <TickerCard key={t.symbol} ticker={t} onClick={() => onSelect(t.symbol)} />
        ))}
      </div>
    </div>
  )
}

function Tooltip({ children, align = 'left' }) {
  return (
    <div className={`absolute z-50 bottom-full ${align === 'right' ? 'right-0' : 'left-0'} mb-2 w-64 p-3 rounded-xl shadow-xl border`}
      style={{ background: '#18181b', borderColor: 'rgba(255,255,255,0.1)' }}>
      {children}
    </div>
  )
}

function SignalTooltip({ t }) {
  const [decomp, setDecomp] = useState(null)

  useEffect(() => {
    fetch(`api/score-decomposition?symbol=${t.symbol}`)
      .then(r => r.json())
      .then(setDecomp)
      .catch(() => {})
  }, [t.symbol])

  const DOTS = { BUY: '🟢', SELL: '🔴', NEUTRAL: '⚪' }

  const CAT_ICONS = { technical: '📊', macro: '🌍', fundamental: '💎', sentiment: '📡' }

  return (
    <Tooltip>
      <p className="text-sm font-semibold text-zinc-100 mb-2">
        Composite: {decomp?.total_score ?? t.signal_score}/100 <span className="text-zinc-500 font-normal">({decomp?.label || 'HOLD'})</span>
      </p>
      {decomp ? (
        <div className="space-y-1.5">
          {/* Category scores */}
          {['technical', 'macro', 'fundamental', 'sentiment'].map(cat => {
            const c = decomp.categories?.[cat]
            if (!c) return null
            return (
              <div key={cat} className="flex items-center justify-between text-xs">
                <span className="text-zinc-400">{CAT_ICONS[cat]} {cat}</span>
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
          {/* Key signals */}
          <div className="pt-1.5 border-t space-y-0.5" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
            {decomp.components.filter(c => c.signal !== 'NEUTRAL').slice(0, 4).map(c => (
              <div key={c.name} className="flex items-center justify-between text-[10px]">
                <span className="text-zinc-500">{c.name.replace(/_/g, ' ')}</span>
                <span>{DOTS[c.signal]} <span className="font-mono text-zinc-400">{Math.round(c.score)}</span></span>
              </div>
            ))}
          </div>
          <p className="text-[10px] text-zinc-600 pt-1">{decomp.summary?.total_signals} signals · Tech 40% · Macro 20% · Fund 20% · Sent 20%</p>
        </div>
      ) : (
        <p className="text-xs text-zinc-500">Loading breakdown...</p>
      )}
    </Tooltip>
  )
}

function ValueTooltip({ t }) {
  return (
    <Tooltip align="right">
      <p className="text-sm font-semibold text-zinc-100 mb-2">
        Value: {t.value_score}/100 <span className="text-zinc-500 font-normal">({t.value_label})</span>
      </p>
      <p className="text-xs text-zinc-500 mb-2">Fundamental valuation vs peers:</p>
      <div className="space-y-1.5">
        <div className="flex items-center justify-between text-xs">
          <span className="text-zinc-400">EV per lb</span>
          <span className="font-mono text-zinc-200">${t.ev_per_lb}/lb</span>
        </div>
        <div className="flex items-center justify-between text-xs">
          <span className="text-zinc-400">vs peer avg</span>
          <span className={`font-mono ${t.ev_vs_avg_pct <= -20 ? 'text-emerald-400/70' : t.ev_vs_avg_pct >= 20 ? 'text-red-400/70' : 'text-zinc-200'}`}>
            {t.ev_vs_avg_pct > 0 ? '+' : ''}{t.ev_vs_avg_pct}%
          </span>
        </div>
        <div className="pt-1.5 border-t text-xs text-zinc-500" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
          {t.ev_vs_avg_pct <= -30 ? 'Significantly undervalued vs peers — strong fundamental case'
            : t.ev_vs_avg_pct <= -10 ? 'Below average valuation — decent value'
            : t.ev_vs_avg_pct <= 10 ? 'Fairly valued relative to peers'
            : 'Premium valuation — priced for growth'}
        </div>
      </div>
    </Tooltip>
  )
}

function useTooltip() {
  const [show, setShow] = useState(false)
  const timer = useRef(null)
  const enter = useCallback(() => { timer.current = setTimeout(() => setShow(true), 200) }, [])
  const leave = useCallback(() => { clearTimeout(timer.current); setShow(false) }, [])
  const tap = useCallback((e) => { e.stopPropagation(); setShow(s => !s) }, [])
  return { show, enter, leave, tap }
}

function TickerCard({ ticker: t, onClick }) {
  const [compositeScore, setCompositeScore] = useState(null)
  const [compositeLabel, setCompositeLabel] = useState(null)

  useEffect(() => {
    fetch(`api/score-decomposition?symbol=${t.symbol}`)
      .then(r => r.json())
      .then(d => {
        if (d.total_score != null) {
          setCompositeScore(Math.round(d.total_score * 10) / 10)
          setCompositeLabel(d.label)
        }
      })
      .catch(() => {})
  }, [t.symbol])

  const displayScore = compositeScore ?? t.signal_score
  const changePct = t.change_pct || 0
  const pct = t.zone_pct || 50
  const scoreWidth = Math.min(100, Math.max(0, displayScore))
  const valueWidth = t.value_score != null ? Math.min(100, Math.max(0, t.value_score)) : null
  const sig = useTooltip()
  const val = useTooltip()

  return (
    <div className="u-card p-3 sm:p-4 cursor-pointer hover:bg-zinc-800/20 transition-all" onClick={onClick}>
      <div className="flex items-start justify-between mb-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="font-bold font-mono text-base text-zinc-100">{t.symbol}</span>
            <span className={`text-sm font-mono ${
              (compositeLabel || t.zone) === 'BUY' || (compositeLabel || t.zone) === 'STRONG BUY' ? 'text-emerald-400/70' :
              (compositeLabel || t.zone) === 'SELL' || (compositeLabel || t.zone) === 'STRONG SELL' ? 'text-red-400/70' :
              'text-zinc-500'
            }`}>{compositeLabel || t.zone}</span>
          </div>
          <p className="text-sm text-zinc-400 mt-0.5 truncate">{t.name}</p>
        </div>
        <div className="text-right ml-2">
          <p className="font-mono font-bold text-base text-zinc-100">${t.current_price}</p>
          <p className={`text-sm font-mono ${changePct >= 0 ? 'text-emerald-400/60' : 'text-red-400/60'}`}>
            {changePct >= 0 ? '+' : ''}{changePct}%
          </p>
        </div>
      </div>

      <div className="mb-3">
        <div className="h-1 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.04)' }}>
          <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, background: 'var(--accent)', opacity: 0.35 }} />
        </div>
        <div className="flex justify-between mt-1">
          <span className="text-sm font-mono text-zinc-500">${t.range_low}</span>
          <span className="text-sm font-mono text-zinc-500">${t.range_high}</span>
        </div>
      </div>

      {/* Signal (technical) */}
      <div className="relative flex items-center gap-2 text-sm"
        onMouseEnter={sig.enter} onMouseLeave={sig.leave}>
        {sig.show && <SignalTooltip t={t} />}
        <span className="text-zinc-400 w-14 cursor-help underline decoration-dotted decoration-zinc-600 underline-offset-2"
          onClick={sig.tap}>Score</span>
        <div className="flex-1 h-1 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.04)' }}>
          <div className="h-full rounded-full" style={{
            width: `${scoreWidth}%`,
            background: displayScore >= 60 ? 'var(--green)' : displayScore >= 45 ? 'var(--accent)' : 'var(--red)',
            opacity: 0.4
          }} />
        </div>
        <span className={`font-mono w-8 text-right ${displayScore >= 60 ? 'text-emerald-400/70' : displayScore >= 45 ? 'text-zinc-400' : 'text-red-400/70'}`}>
          {displayScore}
        </span>
      </div>

      {/* Value (fundamental) — only for miners */}
      {t.value_score != null && (
        <div className="relative flex items-center gap-2 text-sm mt-1.5"
          onMouseEnter={val.enter} onMouseLeave={val.leave}>
          {val.show && <ValueTooltip t={t} />}
          <span className="text-zinc-400 w-14 cursor-help underline decoration-dotted decoration-zinc-600 underline-offset-2"
            onClick={val.tap}>Value</span>
          <div className="flex-1 h-1 rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.04)' }}>
            <div className="h-full rounded-full" style={{
              width: `${valueWidth}%`,
              background: t.value_score >= 65 ? 'var(--green)' : t.value_score >= 40 ? 'var(--yellow)' : 'var(--red)',
              opacity: 0.4
            }} />
          </div>
          <span className={`font-mono w-8 text-right ${t.value_score >= 65 ? 'text-emerald-400/70' : t.value_score >= 40 ? 'text-zinc-400' : 'text-red-400/70'}`}>
            {t.value_score}
          </span>
        </div>
      )}
    </div>
  )
}
