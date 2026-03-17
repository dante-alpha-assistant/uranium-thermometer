import { useState, useEffect } from 'react'
import { Target, ArrowUpCircle, ArrowDownCircle, MinusCircle, Clock } from 'lucide-react'

export default function TradeTickets() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [sortKey, setSortKey] = useState('rank_score')
  const [sortDir, setSortDir] = useState('desc')

  useEffect(() => {
    fetch('api/trade-tickets')
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  if (loading) return <div className="bg-zinc-900/60 border border-zinc-800 rounded-2xl p-6 animate-pulse h-48" />
  if (!data) return null

  const tickets = data.top_opportunities || data.full_tickets || []

  const actionIcon = (a) => {
    if (!a) return <MinusCircle className="w-3.5 h-3.5 text-zinc-500" />
    const al = a.toLowerCase()
    if (al.includes('buy')) return <ArrowUpCircle className="w-3.5 h-3.5 text-emerald-400" />
    if (al.includes('sell')) return <ArrowDownCircle className="w-3.5 h-3.5 text-red-400" />
    if (al.includes('hold')) return <MinusCircle className="w-3.5 h-3.5 text-yellow-400" />
    return <Clock className="w-3.5 h-3.5 text-zinc-500" />
  }

  const actionColor = (a) => {
    if (!a) return 'text-zinc-500'
    const al = a.toLowerCase()
    if (al.includes('strong_buy') || al.includes('strong buy')) return 'text-emerald-300 bg-emerald-400/10'
    if (al.includes('buy')) return 'text-emerald-400 bg-emerald-400/10'
    if (al.includes('sell')) return 'text-red-400 bg-red-400/10'
    if (al.includes('hold')) return 'text-yellow-400 bg-yellow-400/10'
    return 'text-zinc-400 bg-zinc-800'
  }

  const sorted = [...tickets].sort((a, b) => {
    const av = a[sortKey] || 0, bv = b[sortKey] || 0
    return sortDir === 'desc' ? bv - av : av - bv
  })

  const toggleSort = (key) => {
    if (sortKey === key) setSortDir(d => d === 'desc' ? 'asc' : 'desc')
    else { setSortKey(key); setSortDir('desc') }
  }

  const SortHeader = ({ k, children, className = '' }) => (
    <th className={`text-[10px] text-zinc-500 uppercase tracking-wider font-medium cursor-pointer hover:text-zinc-300 px-2 py-2 ${className}`}
        onClick={() => toggleSort(k)}>
      {children} {sortKey === k && (sortDir === 'desc' ? '↓' : '↑')}
    </th>
  )

  return (
    <div className="bg-zinc-900/60 border border-zinc-800 rounded-2xl p-6">
      <div className="flex items-center gap-2 mb-4">
        <Target className="w-5 h-5 text-indigo-400" />
        <h3 className="text-base font-bold text-zinc-100">Trade Tickets</h3>
        <span className="text-[10px] text-zinc-600 ml-auto">{tickets.length} tickers</span>
      </div>

      <div className="overflow-x-auto -mx-2">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-zinc-800/50">
              <SortHeader k="rank">Rank</SortHeader>
              <th className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium px-2 py-2 text-left">Ticker</th>
              <th className="text-[10px] text-zinc-500 uppercase tracking-wider font-medium px-2 py-2 text-left">Action</th>
              <SortHeader k="composite_score" className="text-right">Score</SortHeader>
              <SortHeader k="conviction" className="text-right">Conv</SortHeader>
              <SortHeader k="entry" className="text-right">Entry</SortHeader>
              <SortHeader k="stop_loss" className="text-right">SL</SortHeader>
              <SortHeader k="take_profit" className="text-right">TP</SortHeader>
              <SortHeader k="risk_reward" className="text-right">R:R</SortHeader>
              <SortHeader k="position_pct" className="text-right">Alloc%</SortHeader>
            </tr>
          </thead>
          <tbody>
            {sorted.map((t, i) => (
              <tr key={t.symbol} className="border-b border-zinc-800/20 hover:bg-zinc-800/20 transition-colors">
                <td className="px-2 py-2.5 text-zinc-600 font-mono">{t.rank || i + 1}</td>
                <td className="px-2 py-2.5 font-mono font-bold text-zinc-200">{t.symbol}</td>
                <td className="px-2 py-2.5">
                  <span className={`inline-flex items-center gap-1 text-[10px] font-bold uppercase px-2 py-0.5 rounded-full ${actionColor(t.action)}`}>
                    {actionIcon(t.action)} {t.action}
                  </span>
                </td>
                <td className="px-2 py-2.5 text-right text-zinc-300 font-mono">{t.composite_score?.toFixed(0)}</td>
                <td className="px-2 py-2.5 text-right text-zinc-300">{t.conviction || '—'}</td>
                <td className="px-2 py-2.5 text-right text-zinc-400 font-mono">${t.entry?.toFixed(2)}</td>
                <td className="px-2 py-2.5 text-right text-red-400/60 font-mono">${t.stop_loss?.toFixed(2)}</td>
                <td className="px-2 py-2.5 text-right text-emerald-400/60 font-mono">${t.take_profit?.toFixed(2)}</td>
                <td className="px-2 py-2.5 text-right font-mono">
                  <span className={t.risk_reward >= 2.5 ? 'text-emerald-400' : t.risk_reward >= 1.5 ? 'text-yellow-400' : 'text-red-400'}>
                    {t.risk_reward?.toFixed(1) || '—'}
                  </span>
                </td>
                <td className="px-2 py-2.5 text-right text-zinc-300 font-mono">{t.position_pct?.toFixed(0)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-3 text-[10px] text-zinc-600 italic">
        ⚠️ Paper trading only — position sizes are forward-testing estimates, not validated with 50+ closed trades.
      </div>
    </div>
  )
}
