import { useState, useEffect } from 'react'
import { X } from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine, Area, ComposedChart } from 'recharts'

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

  if (!data) {
    return (
      <div className="rounded-xl p-6" style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
        <p style={{ color: 'var(--text-muted)' }}>Loading {symbol}...</p>
      </div>
    )
  }

  const zoneColor = meta?.zone === 'GREEN' ? 'var(--green)' : meta?.zone === 'RED' ? 'var(--red)' : 'var(--yellow)'

  return (
    <div className="rounded-xl p-6" style={{ background: 'var(--surface)', border: `1px solid ${zoneColor}44` }}>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-xl font-bold font-mono">{symbol}</h2>
          <p className="text-sm" style={{ color: 'var(--text-muted)' }}>{meta?.name}</p>
        </div>
        <button onClick={onClose} className="p-2 rounded-lg hover:opacity-70" style={{ background: 'var(--surface2)' }}>
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Chart */}
      <div className="h-64 mb-4">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data}>
            <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#64748b' }} tickFormatter={d => d?.slice(5)} interval={Math.floor(data.length / 6)} />
            <YAxis domain={['auto', 'auto']} tick={{ fontSize: 10, fill: '#64748b' }} />
            <Tooltip
              contentStyle={{ background: '#1a2332', border: '1px solid #1e293b', borderRadius: '8px', fontSize: '12px' }}
              labelStyle={{ color: '#64748b' }}
            />
            {meta?.bb_upper && <ReferenceLine y={meta.bb_upper} stroke="#ffc107" strokeDasharray="3 3" label={{ value: 'BB Upper', fill: '#64748b', fontSize: 9 }} />}
            {meta?.bb_lower && <ReferenceLine y={meta.bb_lower} stroke="#ffc107" strokeDasharray="3 3" label={{ value: 'BB Lower', fill: '#64748b', fontSize: 9 }} />}
            {meta?.sma_50 && <ReferenceLine y={meta.sma_50} stroke="#00c853" strokeDasharray="5 5" label={{ value: 'SMA50', fill: '#64748b', fontSize: 9 }} />}
            {meta?.sma_200 && <ReferenceLine y={meta.sma_200} stroke="#ff1744" strokeDasharray="5 5" label={{ value: 'SMA200', fill: '#64748b', fontSize: 9 }} />}
            {meta?.support && <ReferenceLine y={meta.support} stroke="#00c85355" label={{ value: 'Support', fill: '#64748b', fontSize: 9 }} />}
            {meta?.resistance && <ReferenceLine y={meta.resistance} stroke="#ff174455" label={{ value: 'Resistance', fill: '#64748b', fontSize: 9 }} />}
            <Line type="monotone" dataKey="close" stroke={zoneColor} strokeWidth={2} dot={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Technical details */}
      {meta && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            ['Signal', `${meta.signal_score} (${meta.signal_label})`],
            ['Zone', `${meta.zone} (${meta.zone_pct}%)`],
            ['RSI (14)', meta.rsi || '—'],
            ['MACD', meta.macd || '—'],
            ['BB Upper', meta.bb_upper ? `$${meta.bb_upper}` : '—'],
            ['BB Lower', meta.bb_lower ? `$${meta.bb_lower}` : '—'],
            ['SMA 50', meta.sma_50 ? `$${meta.sma_50}` : '—'],
            ['SMA 200', meta.sma_200 ? `$${meta.sma_200}` : '—'],
          ].map(([label, value]) => (
            <div key={label} className="rounded-lg p-2 text-center" style={{ background: 'var(--surface2)' }}>
              <p className="text-[10px]" style={{ color: 'var(--text-muted)' }}>{label}</p>
              <p className="font-mono text-xs font-bold">{value}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
