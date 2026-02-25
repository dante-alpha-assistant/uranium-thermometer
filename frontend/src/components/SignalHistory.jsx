import { useState, useEffect } from 'react'
import { ComposedChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceArea } from 'recharts'

function fmt(d) {
  if (!d) return ''
  const [, m, day] = d.split('-')
  return `${['','Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][parseInt(m)]} ${parseInt(day)}`
}

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  const d = payload[0]?.payload
  if (!d) return null
  return (
    <div className="bg-zinc-900 border border-zinc-700 rounded-lg p-3 shadow-xl text-xs">
      <p className="text-zinc-300 font-medium mb-1.5">{fmt(d.date)}</p>
      <div className="space-y-1">
        <div className="flex justify-between gap-4">
          <span className="text-zinc-500">Composite</span>
          <span className="font-mono font-bold" style={{
            color: d.score >= 60 ? '#34d399' : d.score <= 40 ? '#f87171' : '#fbbf24'
          }}>{d.score}/100</span>
        </div>
        <div className="flex justify-between gap-4">
          <span className="text-zinc-500">URA Price</span>
          <span className="font-mono text-zinc-200">${d.price}</span>
        </div>
        {d.label && (
          <div className="flex justify-between gap-4">
            <span className="text-zinc-500">Signal</span>
            <span className="font-mono text-zinc-300">{d.label}</span>
          </div>
        )}
        {d.fwd_5d != null && (
          <div className="flex justify-between gap-4 pt-1 border-t" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
            <span className="text-zinc-500">5d Return</span>
            <span className={`font-mono font-bold ${d.fwd_5d >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
              {d.fwd_5d > 0 ? '+' : ''}{d.fwd_5d}%
            </span>
          </div>
        )}
      </div>
    </div>
  )
}

export default function SignalHistory() {
  const [data, setData] = useState(null)
  const [sym, setSym] = useState('URA')

  useEffect(() => {
    fetch(`api/signal-history?symbol=${sym}&days=90`)
      .then(r => r.json())
      .then(setData)
      .catch(() => {})
  }, [sym])

  if (!data?.snapshots?.length) return null

  const chartData = data.snapshots.map(s => ({
    date: s.date,
    score: s.total_score,
    price: s.price,
    label: s.label,
    fwd_5d: s.fwd_5d,
    technical: s.technical_score,
    macro: s.macro_score,
    fundamental: s.fundamental_score,
    sentiment: s.sentiment_score,
  }))

  const prices = chartData.map(d => d.price).filter(Boolean)
  const minPrice = Math.floor(Math.min(...prices) * 0.98)
  const maxPrice = Math.ceil(Math.max(...prices) * 1.02)

  const tickers = ['URA', 'CCJ', 'UEC', 'UUUU', 'DNN', 'NXE', 'OKLO', 'LEU', 'PDN.AX', 'U-UN.TO']
  const summary = data.summary || {}
  const corr = summary.score_return_correlation_5d

  return (
    <div className="u-card p-5">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-sm font-semibold text-zinc-200">Signal History</h3>
          <p className="text-xs text-zinc-500 mt-0.5">
            {data.count} day{data.count !== 1 ? 's' : ''} tracked
            {summary.avg_score != null && ` · avg ${summary.avg_score}`}
            {corr != null && (
              <span className={corr > 0.3 ? 'text-emerald-400/70' : corr < -0.1 ? 'text-red-400/70' : 'text-zinc-400'}>
                {' '}· r={corr} (5d)
              </span>
            )}
          </p>
        </div>
        <div className="flex gap-1">
          {tickers.map(t => (
            <button
              key={t}
              onClick={() => setSym(t)}
              className={`px-2 py-0.5 rounded text-[10px] font-mono transition-colors ${sym === t ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-600 hover:text-zinc-400'}`}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      <ResponsiveContainer width="100%" height={220}>
        <ComposedChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.03)" />

          {/* Zone bands */}
          <ReferenceArea y1={60} y2={100} yAxisId="score" fill="#16a34a" fillOpacity={0.06} />
          <ReferenceArea y1={40} y2={60} yAxisId="score" fill="#eab308" fillOpacity={0.04} />
          <ReferenceArea y1={0} y2={40} yAxisId="score" fill="#dc2626" fillOpacity={0.06} />

          <XAxis
            dataKey="date"
            tick={{ fill: '#52525b', fontSize: 10 }}
            tickFormatter={fmt}
            interval={Math.max(0, Math.floor(chartData.length / 7) - 1)}
          />
          <YAxis
            yAxisId="score"
            domain={[0, 100]}
            tick={{ fill: '#52525b', fontSize: 10 }}
            tickFormatter={v => v}
            width={30}
          />
          <YAxis
            yAxisId="price"
            orientation="right"
            domain={[minPrice, maxPrice]}
            tick={{ fill: '#52525b', fontSize: 10 }}
            tickFormatter={v => `$${v}`}
            width={45}
          />

          <Tooltip content={<CustomTooltip />} />

          <Line
            type="monotone"
            dataKey="score"
            stroke="#818cf8"
            strokeWidth={2.5}
            dot={chartData.length <= 30}
            yAxisId="score"
            name="Score"
          />
          <Line
            type="monotone"
            dataKey="price"
            stroke="#6366f1"
            strokeWidth={1.5}
            strokeDasharray="4 2"
            dot={false}
            yAxisId="price"
            name="Price"
            opacity={0.5}
          />
        </ComposedChart>
      </ResponsiveContainer>

      {/* Category mini-bars for latest snapshot */}
      {chartData.length > 0 && (
        <div className="flex items-center gap-4 mt-3 pt-3 border-t" style={{ borderColor: 'var(--border)' }}>
          {[
            { key: 'technical', label: '📊 Tech', color: '#818cf8' },
            { key: 'macro', label: '🌍 Macro', color: '#f59e0b' },
            { key: 'fundamental', label: '💎 Fund', color: '#10b981' },
            { key: 'sentiment', label: '📡 Sent', color: '#06b6d4' },
          ].map(({ key, label, color }) => {
            const val = chartData[chartData.length - 1][key]
            if (val == null) return null
            return (
              <div key={key} className="flex items-center gap-1.5 text-[10px]">
                <span className="text-zinc-500">{label}</span>
                <div className="w-8 h-1.5 rounded-full overflow-hidden bg-zinc-800">
                  <div className="h-full rounded-full" style={{ width: `${val}%`, background: color, opacity: 0.6 }} />
                </div>
                <span className="font-mono text-zinc-400">{val}</span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
