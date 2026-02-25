import { useState, useEffect } from 'react'

export default function TermSpread() {
  const [data, setData] = useState(null)
  useEffect(() => { fetch('api/term-spread').then(r => r.json()).then(setData).catch(() => {}) }, [])
  if (!data) return null

  const hist = data.historical || []
  const maxPrice = Math.max(...hist.map(h => Math.max(h.spot, h.lt)), 1)

  return (
    <div className="u-card p-6">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h3 className="text-sm font-semibold text-zinc-200">Term vs Spot Spread</h3>
          <p className="text-[10px] text-zinc-400 mt-0.5">{data.source}</p>
        </div>
        <span className="text-xs font-mono text-zinc-400">{data.signal}</span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-5">
        {[
          { label: 'Spot', price: data.spot_price },
          { label: 'Mid-Term', price: data.mid_term_price, spread: data.mt_spread_pct },
          { label: 'Long-Term', price: data.long_term_price, spread: data.lt_spread_pct },
        ].map(item => (
          <div key={item.label} className="text-center p-3 rounded-xl" className="u-stat" >
            <p className="text-[10px] text-zinc-400 mb-1">{item.label}</p>
            <p className="font-mono text-lg font-bold text-zinc-100">${item.price}</p>
            {item.spread != null && (
              <p className="text-[10px] font-mono text-zinc-400">{item.spread > 0 ? '+' : ''}{item.spread}%</p>
            )}
          </div>
        ))}
      </div>

      {hist.length > 2 && (
        <div className="mb-4">
          <div className="flex items-end gap-0.5 h-16">
            {hist.map((h, i) => (
              <div key={i} className="flex-1 relative h-full">
                <div className="absolute bottom-0 w-full rounded-t" style={{ height: `${(h.spot / maxPrice) * 100}%`, background: 'var(--accent)', opacity: 0.25 }} />
                <div className="absolute bottom-0 w-full rounded-t" style={{ height: `${(h.lt / maxPrice) * 100}%`, background: 'var(--accent)', opacity: 0.1 }} />
              </div>
            ))}
          </div>
        </div>
      )}

      <p className="text-xs text-zinc-500 leading-relaxed">{data.detail}</p>
    </div>
  )
}
