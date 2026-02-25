import { useState, useEffect } from 'react'
import { ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'

function FlowTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0]?.payload
  if (!d) return null
  return (
    <div className="bg-zinc-900 border border-zinc-700 rounded-lg p-3 shadow-xl text-xs space-y-1">
      <p className="text-zinc-300 font-medium">{d.week}</p>
      {d.ura_flow != null && (
        <div className="flex justify-between gap-4">
          <span className="text-zinc-500">URA</span>
          <span className={`font-mono ${d.ura_flow >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
            {d.ura_flow > 0 ? '+' : ''}${d.ura_flow}M
          </span>
        </div>
      )}
      {d.urnm_flow != null && (
        <div className="flex justify-between gap-4">
          <span className="text-zinc-500">URNM</span>
          <span className={`font-mono ${d.urnm_flow >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
            {d.urnm_flow > 0 ? '+' : ''}${d.urnm_flow}M
          </span>
        </div>
      )}
      {d.ura_price && (
        <div className="flex justify-between gap-4 pt-1 border-t" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
          <span className="text-zinc-500">URA Price</span>
          <span className="font-mono text-zinc-300">${d.ura_price}</span>
        </div>
      )}
    </div>
  )
}

function StatCard({ label, value, sub, positive }) {
  return (
    <div className="p-2.5 rounded-lg text-center" style={{ background: 'rgba(255,255,255,0.02)' }}>
      <p className="text-[9px] uppercase tracking-wider text-zinc-600 mb-0.5">{label}</p>
      <p className={`font-mono text-sm font-bold ${positive == null ? 'text-zinc-300' : positive ? 'text-emerald-400' : 'text-red-400'}`}>
        {value}
      </p>
      {sub && <p className="text-[9px] text-zinc-600 mt-0.5">{sub}</p>}
    </div>
  )
}

export default function FundFlows() {
  const [data, setData] = useState(null)

  useEffect(() => {
    fetch('api/fund-flows')
      .then(r => r.json())
      .then(setData)
      .catch(() => {})
  }, [])

  if (!data?.etfs?.length) return null

  const ura = data.etfs.find(e => e.symbol === 'URA')
  const urnm = data.etfs.find(e => e.symbol === 'URNM')

  // Merge weekly flows for chart
  const weekMap = {}
  if (ura) {
    ura.weekly_flows.forEach(w => {
      weekMap[w.week] = { ...weekMap[w.week], week: w.week, ura_flow: w.flow_mm, ura_price: w.avg_price }
    })
  }
  if (urnm) {
    urnm.weekly_flows.forEach(w => {
      weekMap[w.week] = { ...weekMap[w.week], week: w.week, urnm_flow: w.flow_mm }
    })
  }
  const chartData = Object.values(weekMap).sort((a, b) => a.week.localeCompare(b.week))

  // Divergence detection
  const hasDivergence = ura && urnm && (
    (ura.flow_22d_mm < -10 && urnm.flow_22d_mm > 10) ||
    (ura.flow_22d_mm > 10 && urnm.flow_22d_mm < -10)
  )
  const divergenceType = ura && urnm && ura.flow_22d_mm < 0 && urnm.flow_22d_mm > 0
    ? 'bullish' : 'bearish'

  const fmtDate = d => {
    if (!d) return ''
    const [, m, day] = d.split('-')
    return `${['','Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][parseInt(m)]} ${parseInt(day)}`
  }

  const sigColor = s => s?.includes('INFLOW') ? 'text-emerald-400' : s?.includes('OUTFLOW') ? 'text-red-400' : 'text-zinc-400'

  return (
    <div className="u-card p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-zinc-200">Fund Flows</h3>
          <p className="text-xs text-zinc-500 mt-0.5">
            Estimated ETF inflows/outflows · <span className={sigColor(data.sector_signal)}>{data.sector_signal}</span>
          </p>
        </div>
        {hasDivergence && (
          <div className={`px-3 py-1.5 rounded-lg text-[10px] font-medium ${
            divergenceType === 'bullish'
              ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
              : 'bg-red-500/10 text-red-400 border border-red-500/20'
          }`}>
            ⚡ {divergenceType === 'bullish' ? 'Bullish' : 'Bearish'} Divergence — {
              divergenceType === 'bullish'
                ? 'URNM inflows while URA outflows'
                : 'URA inflows while URNM outflows'
            }
          </div>
        )}
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
        {ura && <>
          <StatCard label="URA 5d" value={`$${ura.flow_5d_mm > 0 ? '+' : ''}${ura.flow_5d_mm}M`} positive={ura.flow_5d_mm > 0} />
          <StatCard label="URA 22d" value={`$${ura.flow_22d_mm > 0 ? '+' : ''}${ura.flow_22d_mm}M`} sub={ura.signal} positive={ura.flow_22d_mm > 0} />
          <StatCard label="URA 63d" value={`$${ura.flow_63d_mm > 0 ? '+' : ''}${ura.flow_63d_mm}M`} positive={ura.flow_63d_mm > 0} />
        </>}
        {urnm && <>
          <StatCard label="URNM 5d" value={`$${urnm.flow_5d_mm > 0 ? '+' : ''}${urnm.flow_5d_mm}M`} positive={urnm.flow_5d_mm > 0} />
          <StatCard label="URNM 22d" value={`$${urnm.flow_22d_mm > 0 ? '+' : ''}${urnm.flow_22d_mm}M`} sub={urnm.signal} positive={urnm.flow_22d_mm > 0} />
          <StatCard label="URNM 63d" value={`$${urnm.flow_63d_mm > 0 ? '+' : ''}${urnm.flow_63d_mm}M`} positive={urnm.flow_63d_mm > 0} />
        </>}
      </div>

      {/* Weekly flow chart */}
      {chartData.length > 0 && (
        <ResponsiveContainer width="100%" height={200}>
          <ComposedChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.03)" />
            <XAxis dataKey="week" tick={{ fill: '#52525b', fontSize: 10 }} tickFormatter={fmtDate}
              interval={Math.max(0, Math.floor(chartData.length / 8) - 1)} />
            <YAxis tick={{ fill: '#52525b', fontSize: 10 }} tickFormatter={v => `$${v}M`} width={50} />
            <YAxis yAxisId="price" orientation="right" tick={{ fill: '#52525b', fontSize: 10 }}
              tickFormatter={v => `$${v}`} width={40}
              domain={['auto', 'auto']} />
            <Tooltip content={<FlowTooltip />} />
            <ReferenceLine y={0} stroke="rgba(255,255,255,0.1)" />
            <Bar dataKey="ura_flow" fill="#818cf8" opacity={0.6} radius={[2, 2, 0, 0]} name="URA Flow" />
            <Bar dataKey="urnm_flow" fill="#06b6d4" opacity={0.6} radius={[2, 2, 0, 0]} name="URNM Flow" />
            <Line type="monotone" dataKey="ura_price" stroke="#a1a1aa" strokeWidth={1.5} strokeDasharray="4 2"
              dot={false} yAxisId="price" name="URA Price" />
          </ComposedChart>
        </ResponsiveContainer>
      )}

      {/* Momentum */}
      <div className="flex items-center gap-4 text-[10px] text-zinc-500">
        {ura && <span>URA momentum: <span className={ura.momentum === 'ACCELERATING' ? 'text-emerald-400' : ura.momentum === 'DECELERATING' ? 'text-amber-400' : 'text-zinc-400'}>{ura.momentum}</span></span>}
        {urnm && <span>URNM momentum: <span className={urnm.momentum === 'ACCELERATING' ? 'text-emerald-400' : urnm.momentum === 'DECELERATING' ? 'text-amber-400' : 'text-zinc-400'}>{urnm.momentum}</span></span>}
        <span className="text-zinc-600">Method: OBV-style flow estimation</span>
      </div>
    </div>
  )
}
