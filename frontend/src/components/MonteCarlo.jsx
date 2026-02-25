import { useState, useEffect } from 'react'
import { AreaChart, Area, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'

export default function MonteCarlo({ symbol = 'URA' }) {
  const [data, setData] = useState(null)
  const [days, setDays] = useState(30)
  const [drift, setDrift] = useState('neutral')

  useEffect(() => {
    fetch(`api/monte-carlo/${symbol}?days=${days}&simulations=1000&drift_mode=${drift}`)
      .then(r => r.json()).then(setData).catch(() => {})
  }, [symbol, days, drift])

  if (!data?.bands) return null

  const chartData = data.bands.p50.map((_, i) => ({
    day: i, p5: data.bands.p5[i], p25: data.bands.p25[i],
    p50: data.bands.p50[i], p75: data.bands.p75[i], p95: data.bands.p95[i],
  }))

  const tickInterval = Math.max(0, Math.floor(chartData.length / 6) - 1)
  const pct = data.percentiles
  const zp = data.zone_probabilities || {}
  const upside = pct.p75 ? ((pct.p75 - data.current_price) / data.current_price * 100).toFixed(1) : null
  const downside = pct.p25 ? ((pct.p25 - data.current_price) / data.current_price * 100).toFixed(1) : null

  return (
    <div className="u-card p-6">
      <div className="flex items-center justify-between mb-1">
        <h3 className="text-sm font-semibold text-zinc-200">Price Simulation — {symbol}</h3>
        <div className="flex gap-1">
          {[30, 60, 90].map(d => (
            <button key={d} onClick={() => setDays(d)}
              className={`px-2.5 py-1 rounded-lg text-[10px] font-mono transition-colors ${
                days === d ? 'bg-zinc-700/60 text-zinc-200' : 'text-zinc-600 hover:text-zinc-400 hover:bg-zinc-800/40'
              }`}>
              {d}d
            </button>
          ))}
        </div>
      </div>
      <div className="flex items-center gap-3 mb-4">
        <p className="text-[10px] text-zinc-400">
          1,000 paths · Vol {data.vol_annual}%/yr · Drift {data.drift_annual > 0 ? '+' : ''}{data.drift_annual}%/yr
        </p>
        <div className="flex gap-1 ml-auto">
          {[['neutral', 'Risk-Neutral'], ['historical', 'Historical']].map(([mode, label]) => (
            <button key={mode} onClick={() => setDrift(mode)}
              className={`px-2 py-0.5 rounded-lg text-[10px] transition-colors ${
                drift === mode ? 'bg-zinc-700/60 text-zinc-200' : 'text-zinc-600 hover:text-zinc-400 hover:bg-zinc-800/40'
              }`}>
              {label}
            </button>
          ))}
        </div>
      </div>

      <ResponsiveContainer width="100%" height={240}>
        <AreaChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.03)" />
          <XAxis dataKey="day" tick={{ fill: '#52525b', fontSize: 10 }} interval={tickInterval} tickFormatter={v => `D${v}`} />
          <YAxis tick={{ fill: '#52525b', fontSize: 10 }} tickFormatter={v => `$${v.toFixed(0)}`} domain={['auto', 'auto']} />
          <Tooltip contentStyle={{ backgroundColor: '#18181b', border: '1px solid rgba(255,255,255,0.06)', borderRadius: 12, color: '#fafafa', fontSize: 12 }}
            formatter={(v) => [`$${v.toFixed(2)}`]} labelFormatter={v => `Day ${v}`} />
          <Area type="monotone" dataKey="p95" stroke="none" fill="#818cf8" fillOpacity={0.04} />
          <Area type="monotone" dataKey="p75" stroke="none" fill="#818cf8" fillOpacity={0.08} />
          <Area type="monotone" dataKey="p25" stroke="none" fill="#818cf8" fillOpacity={0.08} />
          <Area type="monotone" dataKey="p5" stroke="none" fill="#09090b" fillOpacity={1} />
          <Line type="monotone" dataKey="p50" stroke="#818cf8" strokeWidth={2} dot={false} />
          <Line type="monotone" dataKey="p75" stroke="#818cf8" strokeWidth={1} strokeDasharray="4 4" dot={false} opacity={0.4} />
          <Line type="monotone" dataKey="p25" stroke="#818cf8" strokeWidth={1} strokeDasharray="4 4" dot={false} opacity={0.4} />
        </AreaChart>
      </ResponsiveContainer>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4">
        {[
          { label: 'Upside (p75)', val: upside, price: pct.p75 },
          { label: 'Downside (p25)', val: downside, price: pct.p25 },
          zp.prob_green != null ? { label: 'P(Buy Zone)', val: `${zp.prob_green}%`, price: `≤$${zp.green_price}` } : null,
          zp.prob_red != null ? { label: 'P(Sell Zone)', val: `${zp.prob_red}%`, price: `≥$${zp.red_price}` } : null,
        ].filter(Boolean).map((s, i) => (
          <div key={i} className="rounded-xl p-2.5 text-center" className="u-stat" >
            <p className="text-[10px] text-zinc-400">{s.label}</p>
            <p className="font-mono text-sm font-bold text-zinc-200">
              {typeof s.val === 'string' ? s.val : `${s.val > 0 ? '+' : ''}${s.val}%`}
            </p>
            <p className="text-[10px] font-mono text-zinc-400">{typeof s.price === 'string' ? s.price : `$${s.price}`}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
