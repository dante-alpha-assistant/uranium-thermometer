const actionConfig = {
  'ACCUMULATE': { color: '#34d399', label: 'ACCUMULATE' },
  'BUY': { color: '#34d399', label: 'BUY' },
  'HOLD': { color: '#fbbf24', label: 'HOLD' },
  'REDUCE': { color: '#f87171', label: 'REDUCE' },
  'SELL': { color: '#f87171', label: 'SELL' },
}

export default function Verdict({ verdict }) {
  if (!verdict) return null
  const cfg = actionConfig[verdict.action] || actionConfig.HOLD
  const bars = verdict.conviction === 'HIGH' ? 3 : verdict.conviction === 'MEDIUM' ? 2 : 1

  return (
    <div className="u-card p-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <p className="text-[10px] uppercase tracking-widest text-zinc-600 font-mono mb-1">The Machine Says</p>
          <p className="text-3xl font-black tracking-tight" style={{ color: cfg.color }}>{verdict.action}</p>
        </div>
        <div className="text-right">
          <p className="text-[10px] uppercase tracking-widest text-zinc-400 mb-1.5">Conviction</p>
          <div className="flex gap-1 justify-end">
            {[1, 2, 3].map(i => (
              <div key={i} className="w-5 h-1.5 rounded-sm"
                style={{ backgroundColor: i <= bars ? cfg.color : 'rgba(255,255,255,0.06)' }} />
            ))}
          </div>
          <p className="text-xs font-mono mt-1 text-zinc-500">{verdict.conviction}</p>
        </div>
      </div>

      <p className="text-sm text-zinc-400 leading-relaxed mb-4">{verdict.detail}</p>

      <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-zinc-400">
        <span>Score <span className="font-mono text-zinc-300">{verdict.composite_score}/100</span></span>
        <span>Bullish <span className="font-mono text-emerald-400/80">{verdict.bullish_tickers}/{verdict.total_tickers}</span></span>
        <span>Bearish <span className="font-mono text-red-400/80">{verdict.bearish_tickers}/{verdict.total_tickers}</span></span>
        {verdict.macro_regime && (
          <span>Macro <span className={`font-mono ${verdict.macro_regime === 'FAVORABLE' ? 'text-emerald-400/80' : verdict.macro_regime === 'HOSTILE' ? 'text-red-400/80' : 'text-zinc-400'}`}>{verdict.macro_regime}</span></span>
        )}
      </div>
    </div>
  )
}
