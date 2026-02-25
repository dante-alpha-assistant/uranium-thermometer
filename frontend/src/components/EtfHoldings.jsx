import { useState, useEffect } from 'react'

export default function EtfHoldings() {
  const [data, setData] = useState(null)

  useEffect(() => {
    fetch('api/etf-holdings').then(r => r.json()).then(setData).catch(() => {})
  }, [])

  if (!data?.holdings?.length) return null

  return (
    <div className="u-card p-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-lg font-bold text-white">📊 URA ETF Holdings</h3>
          <p className="text-xs text-gray-500 mt-0.5">{data.source} · {data.last_updated}</p>
        </div>
        <div className="text-right">
          <span className="text-xs font-mono text-zinc-400">{data.concentration}</span>
          <p className="text-[10px] text-zinc-400 mt-0.5">Top 10 = {data.top10_weight_pct}%</p>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full">
          <thead>
            <tr className="border-b border-gray-700/50">
              <th className="text-left text-xs text-gray-500 uppercase tracking-wider py-2 pr-4">Holding</th>
              <th className="text-right text-xs text-gray-500 uppercase tracking-wider py-2 px-4">Weight</th>
              <th className="text-right text-xs text-gray-500 uppercase tracking-wider py-2 px-4">Price</th>
              <th className="text-center text-xs text-gray-500 uppercase tracking-wider py-2 pl-4">Tracked</th>
            </tr>
          </thead>
          <tbody>
            {data.holdings.map((h, i) => (
              <tr key={i} className="border-b border-gray-800/50 hover:bg-gray-800/30 transition-colors">
                <td className="py-3 pr-4">
                  <div className="flex items-center gap-3">
                    <span className="font-mono text-base font-bold text-white">{h.ticker}</span>
                    <span className="text-sm text-gray-400">{h.name}</span>
                  </div>
                </td>
                <td className="py-3 px-4 text-right">
                  <div className="flex items-center justify-end gap-2">
                    <div className="w-20 h-2 bg-gray-800 rounded-full overflow-hidden">
                      <div className="h-full bg-indigo-500 rounded-full" style={{ width: `${Math.min(100, h.weight_pct * 4)}%` }} />
                    </div>
                    <span className="font-mono text-base font-semibold text-white w-14 text-right">{h.weight_pct}%</span>
                  </div>
                </td>
                <td className="py-3 px-4 text-right font-mono text-sm text-gray-300">
                  {h.price ? `$${h.price.toLocaleString()}` : '—'}
                </td>
                <td className="py-3 pl-4 text-center">
                  {h.tracked_by_dashboard ? (
                    <span className="text-emerald-400 text-sm">✓</span>
                  ) : (
                    <span className="text-gray-600 text-sm">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="text-xs text-gray-500 mt-3">{data.concentration_note}</p>
    </div>
  )
}
