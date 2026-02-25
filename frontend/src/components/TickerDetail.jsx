import { useState, useEffect } from 'react'
import { X } from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, ComposedChart } from 'recharts'

export default function TickerDetail({ symbol, onClose }) {
  const [data, setData] = useState(null)
  const [meta, setMeta] = useState(null)

  useEffect(() => {
    Promise.all([
      fetch(`api/history/${symbol}?days=180`).then(r => r.json()),
      fetch(`api/ticker/${symbol}`).then(r => r.json()),
    ]).then(([hist, m]) => {
      setData(hist.prices || [])
      setMeta(m)
    }).catch(console.error)
  }, [symbol])

  // Close on Escape
  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  const zoneColor = meta?.zone === 'GREEN' ? 'var(--green)' : meta?.zone === 'RED' ? 'var(--red)' : 'var(--yellow)'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={onClose}>
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60" />

      {/* Modal */}
      <div className="relative w-full max-w-3xl max-h-[90vh] overflow-y-auto u-card p-4 sm:p-6 animate-fade-in"
        onClick={e => e.stopPropagation()}>

        {!data ? (
          <p className="text-zinc-400">Loading {symbol}...</p>
        ) : (
          <>
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-xl font-bold font-mono text-zinc-100">{symbol}</h2>
                <p className="text-sm text-zinc-400">{meta?.name}</p>
              </div>
              <button onClick={onClose} className="p-2 rounded-lg hover:bg-zinc-700/40 text-zinc-400 hover:text-zinc-200 transition-colors">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="h-64 mb-4">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={data}>
                  <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#71717a' }} tickFormatter={d => d?.slice(5)} interval={Math.floor(data.length / 6)} />
                  <YAxis domain={['auto', 'auto']} tick={{ fontSize: 10, fill: '#71717a' }} />
                  <Tooltip
                    contentStyle={{ background: '#1c1c22', border: '1px solid rgba(255,255,255,0.08)', borderRadius: '12px', fontSize: '12px', color: '#fafafa' }}
                    labelStyle={{ color: '#71717a' }}
                  />
                  {meta?.bb_upper && <ReferenceLine y={meta.bb_upper} stroke="#818cf8" strokeDasharray="3 3" strokeOpacity={0.4} />}
                  {meta?.bb_lower && <ReferenceLine y={meta.bb_lower} stroke="#818cf8" strokeDasharray="3 3" strokeOpacity={0.4} />}
                  {meta?.sma_50 && <ReferenceLine y={meta.sma_50} stroke="#34d399" strokeDasharray="5 5" strokeOpacity={0.5} />}
                  {meta?.sma_200 && <ReferenceLine y={meta.sma_200} stroke="#f87171" strokeDasharray="5 5" strokeOpacity={0.5} />}
                  <Line type="monotone" dataKey="close" stroke={zoneColor} strokeWidth={2} dot={false} />
                </ComposedChart>
              </ResponsiveContainer>
            </div>

            {meta && (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {[
                  ['Signal', 'See Composite Score above'],
                  ['Zone', `${meta.zone} (${meta.zone_pct}%)`],
                  ['RSI (14)', meta.rsi?.toFixed(1) || '—'],
                  ['MACD', meta.macd?.toFixed(2) || '—'],
                  ['BB Upper', meta.bb_upper ? `$${meta.bb_upper}` : '—'],
                  ['BB Lower', meta.bb_lower ? `$${meta.bb_lower}` : '—'],
                  ['SMA 50', meta.sma_50 ? `$${meta.sma_50}` : '—'],
                  ['SMA 200', meta.sma_200 ? `$${meta.sma_200}` : '—'],
                ].map(([label, value]) => (
                  <div key={label} className="u-stat p-2.5 text-center">
                    <p className="text-xs text-zinc-400">{label}</p>
                    <p className="font-mono text-sm font-bold text-zinc-200">{value}</p>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
