import { useState, useEffect } from 'react'
import { Zap } from 'lucide-react'

export default function SignalPanel({ signals }) {
  const [composites, setComposites] = useState({})

  useEffect(() => {
    if (!signals || signals.length === 0) return
    // Fetch composite scores for all tickers
    Promise.all(
      signals.map(s =>
        fetch(`api/score-decomposition?symbol=${s.symbol}`)
          .then(r => r.json())
          .then(d => ({ symbol: s.symbol, score: d.total_score, label: d.label }))
          .catch(() => null)
      )
    ).then(results => {
      const map = {}
      results.filter(Boolean).forEach(r => { map[r.symbol] = r })
      setComposites(map)
    })
  }, [signals])

  if (!signals || signals.length === 0) return null

  return (
    <div className="rounded-xl p-5 h-full" style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
      <div className="flex items-center gap-2 mb-4">
        <Zap className="w-4 h-4" style={{ color: 'var(--yellow)' }} />
        <h2 className="text-lg font-bold tracking-wide">COMPOSITE SCORES</h2>
      </div>
      <div className="space-y-3">
        {signals.map(s => {
          const comp = composites[s.symbol]
          const score = comp?.score ?? s.signal_score
          const label = comp?.label ?? s.signal_label
          const scoreColor = score >= 55 ? 'var(--green)' : score <= 45 ? 'var(--red)' : 'var(--yellow)'
          const labelColor = label?.includes('BUY') ? 'var(--green)' : label?.includes('SELL') ? 'var(--red)' : 'var(--yellow)'
          
          return (
            <div key={s.symbol} className="flex items-center justify-between py-2 border-b" style={{ borderColor: 'var(--border)' }}>
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg flex items-center justify-center font-mono font-bold text-xs"
                  style={{ background: scoreColor + '18', color: scoreColor }}>
                  {Math.round(score)}
                </div>
                <div>
                  <p className="font-mono font-bold text-sm">{s.symbol}</p>
                  <p className="text-xs" style={{ color: 'var(--text-muted)' }}>${s.price}</p>
                </div>
              </div>
              <div className="text-right">
                <p className="text-xs font-bold" style={{ color: labelColor }}>{label}</p>
                <p className="text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>
                  17-signal composite
                </p>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
