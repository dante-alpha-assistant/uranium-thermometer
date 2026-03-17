import { useState, useEffect } from 'react'
import { TrendingUp, TrendingDown, DollarSign, BarChart3, Target, Activity } from 'lucide-react'

function StatCard({ label, value, sub, color = 'text-zinc-100', icon: Icon }) {
  return (
    <div className="bg-zinc-800/40 rounded-xl p-3">
      <div className="flex items-center gap-1.5 mb-1">
        {Icon && <Icon className="w-3 h-3 text-zinc-500" />}
        <span className="text-[10px] text-zinc-500 uppercase tracking-wider">{label}</span>
      </div>
      <div className={`text-lg font-bold font-mono ${color}`}>{value}</div>
      {sub && <div className="text-[10px] text-zinc-500 mt-0.5">{sub}</div>}
    </div>
  )
}

export default function PortfolioPerformance() {
  const [perf, setPerf] = useState(null)
  const [attr, setAttr] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      fetch('api/portfolio/performance').then(r => r.json()),
      fetch('api/portfolio/attribution').then(r => r.json()),
    ]).then(([p, a]) => {
      setPerf(p); setAttr(a); setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  if (loading) return <div className="bg-zinc-900/60 border border-zinc-800 rounded-2xl p-6 animate-pulse h-48" />
  if (!perf) return null

  const retColor = (v) => v > 0 ? 'text-emerald-400' : v < 0 ? 'text-red-400' : 'text-zinc-400'
  const fmt = (v, prefix = '', suffix = '') => v != null ? `${prefix}${v >= 0 ? '+' : ''}${v.toFixed(2)}${suffix}` : '—'

  const stats = perf.stats || perf
  const tickers = attr?.by_ticker || attr?.tickers || []

  return (
    <div className="bg-zinc-900/60 border border-zinc-800 rounded-2xl p-6 space-y-4">
      <div className="flex items-center gap-2">
        <BarChart3 className="w-5 h-5 text-indigo-400" />
        <h3 className="text-base font-bold text-zinc-100">Portfolio Performance</h3>
      </div>

      {/* Key metrics */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard
          label="Total Value"
          value={`$${(stats.total_value || stats.portfolio_value || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`}
          icon={DollarSign}
        />
        <StatCard
          label="Return"
          value={fmt(stats.total_return_pct || stats.return_pct, '', '%')}
          color={retColor(stats.total_return_pct || stats.return_pct || 0)}
          sub={`vs ${fmt(stats.benchmark_return_pct, '', '%')} URA`}
          icon={TrendingUp}
        />
        <StatCard
          label="Alpha"
          value={fmt(stats.alpha_pct || stats.alpha, '', '%')}
          color={retColor(stats.alpha_pct || stats.alpha || 0)}
          icon={Target}
        />
        <StatCard
          label="Win Rate"
          value={stats.win_rate != null ? `${(stats.win_rate * 100).toFixed(0)}%` : stats.win_rate_pct != null ? `${stats.win_rate_pct}%` : '—'}
          sub={`${stats.total_trades || stats.trades || 0} trades`}
          icon={Activity}
        />
      </div>

      {/* P&L breakdown */}
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-zinc-800/30 rounded-lg p-3 text-center">
          <div className="text-[10px] text-zinc-500 mb-1">Realized P&L</div>
          <div className={`text-sm font-bold font-mono ${retColor(stats.realized_pnl || 0)}`}>
            {fmt(stats.realized_pnl, '$')}
          </div>
        </div>
        <div className="bg-zinc-800/30 rounded-lg p-3 text-center">
          <div className="text-[10px] text-zinc-500 mb-1">Unrealized P&L</div>
          <div className={`text-sm font-bold font-mono ${retColor(stats.unrealized_pnl || 0)}`}>
            {fmt(stats.unrealized_pnl, '$')}
          </div>
        </div>
        <div className="bg-zinc-800/30 rounded-lg p-3 text-center">
          <div className="text-[10px] text-zinc-500 mb-1">Cash</div>
          <div className="text-sm font-bold font-mono text-zinc-300">
            ${(stats.cash || 0).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}
          </div>
        </div>
      </div>

      {/* Attribution table */}
      {tickers.length > 0 && (
        <div>
          <div className="text-[10px] text-zinc-500 uppercase tracking-wider mb-2">P&L Attribution</div>
          <div className="space-y-1">
            {tickers.sort((a, b) => (b.contribution_pct || b.pnl || 0) - (a.contribution_pct || a.pnl || 0)).slice(0, 6).map(t => {
              const pnl = t.contribution_pct || t.pnl_pct || t.return_pct || 0
              const width = Math.min(Math.abs(pnl) * 10, 100)
              return (
                <div key={t.symbol || t.ticker} className="flex items-center gap-2">
                  <span className="text-[11px] font-mono text-zinc-300 w-16">{t.symbol || t.ticker}</span>
                  <div className="flex-1 h-4 bg-zinc-800/30 rounded-full overflow-hidden relative">
                    <div className={`h-full rounded-full ${pnl >= 0 ? 'bg-emerald-400/30' : 'bg-red-400/30'}`}
                         style={{ width: `${width}%` }} />
                  </div>
                  <span className={`text-[11px] font-mono w-16 text-right ${retColor(pnl)}`}>
                    {pnl >= 0 ? '+' : ''}{pnl.toFixed(1)}%
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}
