import { useState, useEffect, useCallback } from 'react'
import { ComposedChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'
import { AlertTriangle } from 'lucide-react'

function MetricCard({ label, value, sub, color }) {
  return (
    <div className="p-3 rounded-lg" style={{ background: 'rgba(255,255,255,0.02)' }}>
      <p className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">{label}</p>
      <p className={`font-mono text-lg font-bold ${color || 'text-zinc-200'}`}>{value}</p>
      {sub && <p className="text-[10px] text-zinc-500 mt-0.5">{sub}</p>}
    </div>
  )
}

function fmt(d) {
  if (!d) return ''
  const [, m, day] = d.split('-')
  return `${['','Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][parseInt(m)]} ${parseInt(day)}`
}

function ChartTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const d = payload[0]?.payload
  if (!d) return null
  return (
    <div className="bg-zinc-900 border border-zinc-700 rounded-lg p-3 shadow-xl text-xs space-y-1">
      <p className="text-zinc-300 font-medium">{fmt(d.date)}</p>
      <div className="flex justify-between gap-4">
        <span className="text-zinc-500">Strategy</span>
        <span className="font-mono text-indigo-400">${d.equity?.toLocaleString()}</span>
      </div>
      <div className="flex justify-between gap-4">
        <span className="text-zinc-500">Buy & Hold</span>
        <span className="font-mono text-zinc-400">${d.buyhold?.toLocaleString()}</span>
      </div>
      <div className="flex justify-between gap-4">
        <span className="text-zinc-500">Score</span>
        <span className="font-mono" style={{
          color: d.score >= 60 ? '#34d399' : d.score <= 40 ? '#f87171' : '#fbbf24'
        }}>{d.score}</span>
      </div>
      <div className="flex justify-between gap-4">
        <span className="text-zinc-500">Position</span>
        <span className={`font-mono ${d.position === 'LONG' ? 'text-emerald-400' : 'text-zinc-500'}`}>{d.position}</span>
      </div>
    </div>
  )
}

// Sharpe heatmap color: maps value to green/red
function sharpeColor(val, minV, maxV) {
  if (val == null) return 'rgba(255,255,255,0.02)'
  const range = maxV - minV || 1
  const norm = (val - minV) / range // 0..1
  if (norm >= 0.5) {
    const t = (norm - 0.5) * 2
    return `rgba(16, 185, 129, ${0.1 + t * 0.5})`
  } else {
    const t = (0.5 - norm) * 2
    return `rgba(239, 68, 68, ${0.1 + t * 0.4})`
  }
}

function Heatmap({ sym, period, onSelect, currentBuy, currentSell }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [metric, setMetric] = useState('sharpe')

  useEffect(() => {
    setLoading(true)
    fetch(`api/backtest-optimizer?symbol=${sym}&period=${period}&step=5&sort_by=${metric}`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false) })
      .catch(() => setLoading(false))
  }, [sym, period, metric])

  if (!data?.all_combos) return null

  const buyVals = [...new Set(data.all_combos.map(c => c.buy_threshold))].sort((a,b) => b-a)
  const sellVals = [...new Set(data.all_combos.map(c => c.sell_threshold))].sort((a,b) => a-b)

  const lookup = {}
  data.all_combos.forEach(c => { lookup[`${c.buy_threshold}_${c.sell_threshold}`] = c })

  const metricKey = metric === 'alpha' ? 'alpha_vs_buyhold' : metric === 'return' ? 'total_return_pct' : metric === 'drawdown' ? 'max_drawdown_pct' : `${metric}_ratio`
  const vals = data.all_combos.map(c => c[metricKey]).filter(v => v != null)
  const minV = Math.min(...vals)
  const maxV = Math.max(...vals)

  const best = data.best
  const metrics = [['sharpe','Sharpe'],['sortino','Sortino'],['alpha','Alpha'],['return','Return']]

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-xs font-medium text-zinc-300">Threshold Optimizer</p>
          <p className="text-[10px] text-zinc-500">{data.combos_tested} combos · Best: B={best?.buy_threshold} S={best?.sell_threshold}</p>
        </div>
        <div className="flex gap-0.5">
          {metrics.map(([k, l]) => (
            <button key={k} onClick={() => setMetric(k)}
              className={`px-2 py-0.5 rounded text-[10px] font-mono ${metric === k ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-600 hover:text-zinc-400'}`}>
              {l}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <p className="text-[10px] text-zinc-500 animate-pulse py-4 text-center">Optimizing...</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="border-collapse">
            <thead>
              <tr>
                <th className="text-[9px] text-zinc-600 p-1 w-8">B\S</th>
                {sellVals.map(s => (
                  <th key={s} className="text-[9px] text-zinc-500 font-mono p-1 w-9 text-center">{s}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {buyVals.map(b => (
                <tr key={b}>
                  <td className="text-[9px] text-zinc-500 font-mono p-1 text-right">{b}</td>
                  {sellVals.map(s => {
                    const c = lookup[`${b}_${s}`]
                    if (!c) return <td key={s} className="p-0.5"><div className="w-9 h-7 rounded" style={{ background: 'rgba(255,255,255,0.01)' }} /></td>
                    const val = c[metricKey]
                    const isCurrent = b === currentBuy && s === currentSell
                    const isBest = b === best?.buy_threshold && s === best?.sell_threshold
                    return (
                      <td key={s} className="p-0.5">
                        <button
                          onClick={() => onSelect(b, s)}
                          className="w-9 h-7 rounded text-[8px] font-mono transition-all hover:ring-1 hover:ring-zinc-500 relative"
                          style={{
                            background: sharpeColor(val, minV, maxV),
                            color: Math.abs(val) > (maxV - minV) * 0.3 ? '#fff' : '#a1a1aa',
                            outline: isBest ? '2px solid #818cf8' : isCurrent ? '2px solid #fbbf24' : 'none',
                            outlineOffset: '-1px',
                          }}
                          title={`Buy@${b} Sell@${s}\nSharpe: ${c.sharpe_ratio}\nReturn: ${c.total_return_pct}%\nAlpha: ${c.alpha_vs_buyhold}%\nDD: ${c.max_drawdown_pct}%\nTrades: ${c.total_trades}`}
                        >
                          {val != null ? (metric === 'return' || metric === 'alpha' ? `${val > 0 ? '+' : ''}${Math.round(val)}` : val.toFixed(1)) : '—'}
                        </button>
                      </td>
                    )
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          <div className="flex items-center gap-4 mt-2 text-[9px] text-zinc-600">
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded" style={{ outline: '2px solid #818cf8' }} /> Best</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded" style={{ outline: '2px solid #fbbf24' }} /> Current</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded" style={{ background: 'rgba(16,185,129,0.4)' }} /> High</span>
            <span className="flex items-center gap-1"><span className="w-3 h-3 rounded" style={{ background: 'rgba(239,68,68,0.3)' }} /> Low</span>
          </div>
        </div>
      )}
    </div>
  )
}

export default function Backtester() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [sym, setSym] = useState('URA')
  const [period, setPeriod] = useState('2y')
  const [buyTh, setBuyTh] = useState(70)
  const [sellTh, setSellTh] = useState(55)
  const [initial] = useState(10000)

  const run = useCallback(() => {
    setLoading(true)
    fetch(`api/signal-backtest?symbol=${sym}&period=${period}&initial=${initial}&buy_threshold=${buyTh}&sell_threshold=${sellTh}`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false) })
      .catch(() => setLoading(false))
  }, [sym, period, buyTh, sellTh, initial])

  useEffect(() => { run() }, [sym, period])

  useEffect(() => {
    const t = setTimeout(run, 600)
    return () => clearTimeout(t)
  }, [buyTh, sellTh])

  const handleHeatmapSelect = (b, s) => {
    setBuyTh(b)
    setSellTh(s)
  }

  if (!data?.results) return null

  const r = data.results
  const alphaColor = r.alpha_vs_buyhold >= 0 ? 'text-emerald-400' : 'text-red-400'
  const retColor = r.total_return_pct >= 0 ? 'text-emerald-400' : 'text-red-400'

  const curve = (data.equity_curve || []).map((pt) => {
    const bhRatio = pt.price / (data.equity_curve[0]?.price || 1)
    return { ...pt, buyhold: Math.round(initial * bhRatio * 100) / 100 }
  })

  const tickers = ['URA', 'CCJ', 'UEC', 'UUUU', 'DNN', 'NXE', 'OKLO', 'LEU', 'PDN.AX', 'U-UN.TO']
  const periods = [['3m','3M'],['6m','6M'],['1y','1Y'],['2y','2Y'],['3y','3Y']]
  const trades = data.trades || []

  return (
    <div className="u-card p-5 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h3 className="text-sm font-semibold text-zinc-200">Signal Backtester</h3>
          <p className="text-xs text-zinc-500 mt-0.5">
            {data.trading_days} trading days · Technical signals only
            {loading && <span className="ml-2 animate-pulse">⏳</span>}
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <div className="flex gap-0.5">
            {tickers.map(t => (
              <button key={t} onClick={() => setSym(t)}
                className={`px-2 py-0.5 rounded text-[10px] font-mono ${sym === t ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-600 hover:text-zinc-400'}`}>
                {t}
              </button>
            ))}
          </div>
          <div className="flex gap-0.5">
            {periods.map(([v, l]) => (
              <button key={v} onClick={() => setPeriod(v)}
                className={`px-2 py-0.5 rounded text-[10px] font-mono ${period === v ? 'bg-zinc-700 text-zinc-100' : 'text-zinc-600 hover:text-zinc-400'}`}>
                {l}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Metric cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2">
        <MetricCard label="Strategy" value={`${r.total_return_pct > 0 ? '+' : ''}${r.total_return_pct}%`} sub={`$${r.final_equity.toLocaleString()}`} color={retColor} />
        <MetricCard label="Buy & Hold" value={`${r.buy_hold_return_pct > 0 ? '+' : ''}${r.buy_hold_return_pct}%`} sub={`$${r.buy_hold_final.toLocaleString()}`} color="text-zinc-300" />
        <MetricCard label="Alpha" value={`${r.alpha_vs_buyhold > 0 ? '+' : ''}${r.alpha_vs_buyhold}%`} color={alphaColor} />
        <MetricCard label="Sharpe" value={r.sharpe_ratio ?? '—'} color={r.sharpe_ratio >= 1 ? 'text-emerald-400' : 'text-zinc-300'} />
        <MetricCard label="Sortino" value={r.sortino_ratio ?? '—'} color={r.sortino_ratio >= 1.5 ? 'text-emerald-400' : 'text-zinc-300'} />
        <MetricCard label="Max DD" value={`${r.max_drawdown_pct}%`} color={r.max_drawdown_pct > 20 ? 'text-red-400' : 'text-zinc-300'} />
        <MetricCard label="Win Rate" value={r.win_rate != null ? `${r.win_rate}%` : '—'} sub={`${r.total_trades} trades`} />
        <MetricCard label="Profit Factor" value={r.profit_factor ?? '—'} color={r.profit_factor >= 1.5 ? 'text-emerald-400' : r.profit_factor && r.profit_factor < 1 ? 'text-red-400' : 'text-zinc-300'} />
      </div>

      {/* Threshold sliders */}
      <div className="flex flex-col sm:flex-row gap-4 p-3 rounded-lg" style={{ background: 'rgba(255,255,255,0.02)' }}>
        <div className="flex-1">
          <div className="flex justify-between text-[10px] mb-1">
            <span className="text-zinc-500">Buy Threshold</span>
            <span className="font-mono text-emerald-400">{buyTh}</span>
          </div>
          <input type="range" min="30" max="80" value={buyTh} onChange={e => setBuyTh(+e.target.value)}
            className="w-full h-1.5 rounded-full appearance-none cursor-pointer"
            style={{ background: `linear-gradient(to right, #10b981 ${(buyTh-30)/50*100}%, #27272a ${(buyTh-30)/50*100}%)` }} />
        </div>
        <div className="flex-1">
          <div className="flex justify-between text-[10px] mb-1">
            <span className="text-zinc-500">Sell Threshold</span>
            <span className="font-mono text-red-400">{sellTh}</span>
          </div>
          <input type="range" min="20" max="70" value={sellTh} onChange={e => setSellTh(+e.target.value)}
            className="w-full h-1.5 rounded-full appearance-none cursor-pointer"
            style={{ background: `linear-gradient(to right, #ef4444 ${(sellTh-20)/50*100}%, #27272a ${(sellTh-20)/50*100}%)` }} />
        </div>
      </div>

      {/* Equity curve */}
      {curve.length > 0 && (
        <ResponsiveContainer width="100%" height={250}>
          <ComposedChart data={curve}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.03)" />
            <XAxis dataKey="date" tick={{ fill: '#52525b', fontSize: 10 }} tickFormatter={fmt}
              interval={Math.max(0, Math.floor(curve.length / 8) - 1)} />
            <YAxis tick={{ fill: '#52525b', fontSize: 10 }} tickFormatter={v => `$${(v/1000).toFixed(1)}k`} width={50} />
            <Tooltip content={<ChartTooltip />} />
            <ReferenceLine y={initial} stroke="rgba(255,255,255,0.08)" strokeDasharray="3 3" />
            <Line type="monotone" dataKey="buyhold" stroke="#52525b" strokeWidth={1.5} strokeDasharray="4 2" dot={false} name="Buy & Hold" />
            <Line type="monotone" dataKey="equity" stroke="#818cf8" strokeWidth={2.5} dot={false} name="Strategy" />
          </ComposedChart>
        </ResponsiveContainer>
      )}

      {/* Heatmap */}
      <Heatmap sym={sym} period={period} onSelect={handleHeatmapSelect} currentBuy={buyTh} currentSell={sellTh} />

      {/* Trade log */}
      {trades.length > 0 && (
        <details className="group">
          <summary className="text-[10px] uppercase tracking-wider text-zinc-600 cursor-pointer hover:text-zinc-400">
            Trade Log ({r.total_trades} completed, {r.buy_signals} buys) ▸
          </summary>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-zinc-600 text-[10px] uppercase tracking-wider border-b" style={{ borderColor: 'var(--border)' }}>
                  <th className="text-left py-1.5 pr-2">Action</th>
                  <th className="text-left py-1.5 pr-2">Date</th>
                  <th className="text-right py-1.5 pr-2">Price</th>
                  <th className="text-right py-1.5 pr-2">Score</th>
                  <th className="text-right py-1.5 pr-2">P&L</th>
                  <th className="text-right py-1.5">Days</th>
                </tr>
              </thead>
              <tbody>
                {trades.map((t, i) => (
                  <tr key={i} className="border-b hover:bg-zinc-800/20" style={{ borderColor: 'rgba(255,255,255,0.03)' }}>
                    <td className={`py-1.5 pr-2 font-mono font-bold ${t.type === 'BUY' ? 'text-emerald-400' : 'text-red-400'}`}>
                      {t.type}
                    </td>
                    <td className="py-1.5 pr-2 text-zinc-400">{t.date}</td>
                    <td className="py-1.5 pr-2 text-right font-mono text-zinc-300">${t.price}</td>
                    <td className="py-1.5 pr-2 text-right font-mono text-zinc-400">{t.score}</td>
                    <td className={`py-1.5 pr-2 text-right font-mono ${t.pnl_pct > 0 ? 'text-emerald-400' : t.pnl_pct < 0 ? 'text-red-400' : 'text-zinc-500'}`}>
                      {t.pnl_pct != null ? `${t.pnl_pct > 0 ? '+' : ''}${t.pnl_pct}%` : '—'}
                    </td>
                    <td className="py-1.5 text-right text-zinc-500">{t.holding_days ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}

      {/* Limitations */}
      <div className="flex items-start gap-2 p-3 rounded-lg" style={{ background: 'rgba(234,179,8,0.05)', border: '1px solid rgba(234,179,8,0.1)' }}>
        <AlertTriangle className="w-4 h-4 text-amber-500/70 mt-0.5 flex-shrink-0" />
        <div className="text-[10px] text-zinc-500 space-y-0.5">
          <p className="text-amber-500/80 font-medium">Backtesting Limitations</p>
          {(data.limitations || []).map((l, i) => <p key={i}>• {l}</p>)}
        </div>
      </div>
    </div>
  )
}
