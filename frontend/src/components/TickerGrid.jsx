import { TrendingUp, TrendingDown } from 'lucide-react'

export default function TickerGrid({ tickers, onSelect }) {
  if (!tickers || tickers.length === 0) return null

  return (
    <div>
      <h2 className="text-lg font-bold mb-4 tracking-wide">URANIUM STOCKS</h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {tickers.map(t => (
          <TickerCard key={t.symbol} ticker={t} onClick={() => onSelect(t.symbol)} />
        ))}
      </div>
    </div>
  )
}

function TickerCard({ ticker: t, onClick }) {
  const zoneColor = t.zone === 'GREEN' ? 'var(--green)' : t.zone === 'RED' ? 'var(--red)' : 'var(--yellow)'
  const changePct = t.change_pct || 0
  const scoreColor = t.signal_score >= 55 ? 'var(--green)' : t.signal_score <= 45 ? 'var(--red)' : 'var(--yellow)'

  // Mini bar showing position in range
  const pct = t.zone_pct || 50

  return (
    <div
      className="rounded-xl p-4 cursor-pointer hover:opacity-90 transition-all"
      style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}
      onClick={onClick}
    >
      <div className="flex items-start justify-between mb-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="font-bold font-mono text-base">{t.symbol}</span>
            <span className="text-xs px-2 py-0.5 rounded-full font-bold" style={{ background: zoneColor + '22', color: zoneColor }}>
              {t.zone}
            </span>
          </div>
          <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>{t.name}</p>
        </div>
        <div className="text-right">
          <p className="font-mono font-bold">${t.current_price}</p>
          <p className="text-xs font-mono flex items-center justify-end gap-0.5" style={{ color: changePct >= 0 ? 'var(--green)' : 'var(--red)' }}>
            {changePct >= 0 ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
            {changePct >= 0 ? '+' : ''}{changePct}%
          </p>
        </div>
      </div>

      {/* Mini range bar */}
      <div className="mb-3">
        <div className="h-2 rounded-full overflow-hidden" style={{ background: 'var(--surface2)' }}>
          <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, background: zoneColor }} />
        </div>
        <div className="flex justify-between mt-1">
          <span className="text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>${t.range_low}</span>
          <span className="text-[10px] font-mono" style={{ color: 'var(--text-muted)' }}>${t.range_high}</span>
        </div>
      </div>

      {/* Bottom stats */}
      <div className="flex justify-between text-xs">
        <div>
          <span style={{ color: 'var(--text-muted)' }}>Signal </span>
          <span className="font-mono font-bold" style={{ color: scoreColor }}>{t.signal_score}</span>
        </div>
        <div>
          <span style={{ color: 'var(--text-muted)' }}>RSI </span>
          <span className="font-mono">{t.rsi || '—'}</span>
        </div>
        <div>
          <span style={{ color: 'var(--text-muted)' }}>SMA50 </span>
          <span className="font-mono">${t.sma_50 || '—'}</span>
        </div>
      </div>
    </div>
  )
}
