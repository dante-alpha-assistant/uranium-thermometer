import { Zap } from 'lucide-react'

export default function SignalPanel({ signals }) {
  if (!signals || signals.length === 0) return null

  return (
    <div className="rounded-xl p-5 h-full" style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
      <div className="flex items-center gap-2 mb-4">
        <Zap className="w-4 h-4" style={{ color: 'var(--yellow)' }} />
        <h2 className="text-lg font-bold tracking-wide">SIGNALS</h2>
      </div>
      <div className="space-y-3">
        {signals.map(s => {
          const scoreColor = s.signal_score >= 55 ? 'var(--green)' : s.signal_score <= 45 ? 'var(--red)' : 'var(--yellow)'
          const labelColor = s.signal_label?.includes('BUY') ? 'var(--green)' : s.signal_label?.includes('SELL') ? 'var(--red)' : 'var(--yellow)'
          
          return (
            <div key={s.symbol} className="flex items-center justify-between py-2 border-b" style={{ borderColor: 'var(--border)' }}>
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg flex items-center justify-center font-mono font-bold text-xs"
                  style={{ background: scoreColor + '18', color: scoreColor }}>
                  {Math.round(s.signal_score)}
                </div>
                <div>
                  <p className="font-mono font-bold text-sm">{s.symbol}</p>
                  <p className="text-xs" style={{ color: 'var(--text-muted)' }}>${s.price}</p>
                </div>
              </div>
              <div className="text-right">
                <p className="text-xs font-bold" style={{ color: labelColor }}>{s.signal_label}</p>
                <p className="text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>
                  RSI {s.rsi || '—'}
                </p>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
