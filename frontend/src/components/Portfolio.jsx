import { useState, useEffect } from 'react';

export default function Portfolio() {
  const [portfolio, setPortfolio] = useState(null);
  const [journal, setJournal] = useState(null);
  const [swing, setSwing] = useState(null);

  useEffect(() => {
    fetch('api/portfolio').then(r => r.json()).then(setPortfolio).catch(() => {});
    fetch('api/portfolio/journal').then(r => r.json()).then(setJournal).catch(() => {});
    fetch('api/swing-rules').then(r => r.json()).then(setSwing).catch(() => {});
  }, []);

  if (!portfolio) return null;

  const { cash, positions, total_value, total_pnl, total_pnl_pct } = portfolio;
  const hasPositions = positions?.length > 0;

  // Allocation data for pie
  const allocs = [];
  if (hasPositions) {
    positions.forEach(p => allocs.push({ label: p.symbol, value: p.market_value, color: p.pnl_pct >= 0 ? '#10b981' : '#ef4444' }));
  }
  allocs.push({ label: 'Cash', value: cash, color: '#374151' });
  const total = allocs.reduce((s, a) => s + a.value, 0);

  return (
    <div className="u-card p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-zinc-200">💼 Portfolio</h3>
        <div className="flex gap-2">
          <span className="text-xs font-mono px-2 py-1 rounded bg-zinc-800 text-zinc-200">
            ${total_value?.toLocaleString(undefined, {minimumFractionDigits: 2})}
          </span>
          {total_pnl != null && (
            <span className={`text-xs font-mono px-2 py-1 rounded ${total_pnl >= 0 ? 'bg-zinc-800/40 text-emerald-400/60' : 'bg-zinc-800/40 text-red-400/60'}`}>
              {total_pnl >= 0 ? '+' : ''}${total_pnl?.toFixed(2)} ({total_pnl_pct?.toFixed(2)}%)
            </span>
          )}
          <span className="text-xs font-mono px-2 py-1 rounded bg-zinc-800/40 text-amber-400">PAPER</span>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Allocation bar */}
        <div>
          <h4 className="text-xs text-zinc-400 font-bold mb-2">ALLOCATION</h4>
          <div className="h-4 flex rounded-full overflow-hidden mb-2">
            {allocs.map((a, i) => (
              <div key={i} style={{ width: `${(a.value / total) * 100}%`, backgroundColor: a.color }}
                title={`${a.label}: $${a.value.toFixed(0)} (${((a.value / total) * 100).toFixed(1)}%)`} />
            ))}
          </div>
          <div className="flex flex-wrap gap-2">
            {allocs.map((a, i) => (
              <span key={i} className="text-xs text-zinc-400">
                <span className="inline-block w-2 h-2 rounded-full mr-1" style={{ backgroundColor: a.color }} />
                {a.label} {((a.value / total) * 100).toFixed(0)}%
              </span>
            ))}
          </div>
          <p className="text-xs text-zinc-500 mt-2">Cash: ${cash?.toFixed(2)}</p>
        </div>

        {/* Holdings */}
        <div>
          <h4 className="text-xs text-zinc-400 font-bold mb-2">HOLDINGS</h4>
          {hasPositions ? (
            <div className="space-y-1">
              {positions.map(p => (
                <div key={p.symbol} className="flex justify-between text-xs">
                  <span className="text-zinc-200 font-mono">{p.symbol}</span>
                  <span className="text-zinc-400">{p.shares?.toFixed(1)} shares @ ${p.avg_cost?.toFixed(2)}</span>
                  <span className={`font-mono ${p.pnl_pct >= 0 ? 'text-emerald-400/60' : 'text-red-400/60'}`}>
                    {p.pnl_pct >= 0 ? '+' : ''}{p.pnl_pct?.toFixed(1)}%
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-zinc-500">No positions — waiting for entry signals (score ≥55)</p>
          )}
        </div>

        {/* Active signals */}
        <div>
          <h4 className="text-xs text-zinc-400 font-bold mb-2">SIGNALS</h4>
          {swing?.signals?.length > 0 ? (
            <div className="space-y-1">
              {swing.signals.map((s, i) => (
                <div key={i} className={`text-xs p-1.5 rounded ${
                  s.signal === 'TAKE_PROFIT' ? 'bg-zinc-800/40 text-emerald-400/60' :
                  s.signal === 'STOP_LOSS' ? 'bg-zinc-800/40 text-red-400/60' :
                  'bg-zinc-800/40 text-blue-400'
                }`}>
                  {s.signal.replace('_', ' ')} {s.symbol}
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-zinc-500">No active signals</p>
          )}
        </div>
      </div>

      {/* Trade journal */}
      {journal?.journal?.length > 0 && (
        <div className="mt-4">
          <h4 className="text-xs text-zinc-400 font-bold mb-2">TRADE JOURNAL</h4>
          <div className="overflow-x-auto max-h-32 overflow-y-auto">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-gray-900">
                <tr className="text-zinc-400 border-b border-zinc-800/50">
                  <th className="text-left p-1">Time</th>
                  <th className="text-center p-1">Action</th>
                  <th className="text-left p-1">Ticker</th>
                  <th className="text-right p-1">Shares</th>
                  <th className="text-right p-1">Price</th>
                  <th className="text-right p-1">Total</th>
                </tr>
              </thead>
              <tbody>
                {journal.journal.slice(0, 10).map((t, i) => (
                  <tr key={i} className="border-b border-zinc-800/50/50">
                    <td className="p-1 text-zinc-400 font-mono">{t.timestamp?.slice(0, 16)}</td>
                    <td className="p-1 text-center">
                      <span className={`px-1 py-0.5 rounded ${t.action === 'BUY' ? 'bg-zinc-800/40 text-blue-400' : 'bg-zinc-800/40 text-amber-400/60'}`}>
                        {t.action}
                      </span>
                    </td>
                    <td className="p-1 font-mono text-zinc-200">{t.symbol}</td>
                    <td className="p-1 text-right font-mono text-zinc-300">{t.shares?.toFixed(1)}</td>
                    <td className="p-1 text-right font-mono text-zinc-300">${t.price?.toFixed(2)}</td>
                    <td className="p-1 text-right font-mono text-zinc-300">${t.total?.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
