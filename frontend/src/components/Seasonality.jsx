import { useState, useEffect } from 'react';

export default function Seasonality({ symbol = 'URA' }) {
  const [data, setData] = useState(null);

  useEffect(() => {
    fetch(`api/seasonality/${symbol}`)
      .then(r => r.json())
      .then(setData)
      .catch(() => {});
  }, [symbol]);

  if (!data?.months?.length) return null;

  const maxAbs = Math.max(...data.months.map(m => Math.abs(m.avg_return)), 1);
  const signalColors = { TAILWIND: 'text-emerald-400', HEADWIND: 'text-red-400', NEUTRAL: 'text-zinc-300' };
  const signalEmoji = { TAILWIND: '🟢', HEADWIND: '🔴', NEUTRAL: '⚪' };

  return (
    <div className="u-card p-6">
      <div className="flex items-center justify-between mb-1">
        <h3 className="text-sm font-semibold text-zinc-200">📅 Seasonality — {symbol}</h3>
        {data.current_month_signal && (
          <span className={`text-xs font-mono px-2 py-1 rounded bg-zinc-800 ${signalColors[data.current_month_signal]}`}>
            {signalEmoji[data.current_month_signal]} {data.current_month}: {data.current_month_signal}
          </span>
        )}
      </div>
      <p className="text-xs text-zinc-400 mb-4">{data.years_of_data} years of monthly data</p>

      <div className="space-y-1.5">
        {data.months.map(m => {
          const isCurrentMonth = m.month === data.current_month;
          const barWidth = (Math.abs(m.avg_return) / maxAbs) * 100;
          const isPositive = m.avg_return >= 0;
          return (
            <div key={m.month} className={`flex items-center gap-2 text-xs ${isCurrentMonth ? 'bg-zinc-800/30 rounded px-1 py-0.5' : ''}`}>
              <span className={`w-8 font-mono ${isCurrentMonth ? 'text-zinc-100 font-bold' : 'text-zinc-300'}`}>{m.month}</span>
              <div className="flex-1 flex items-center h-4">
                <div className="w-1/2 flex justify-end">
                  {!isPositive && (
                    <div className="bg-red-500/60 h-3 rounded-l" style={{ width: `${barWidth}%` }} />
                  )}
                </div>
                <div className="w-px h-4 bg-gray-600" />
                <div className="w-1/2">
                  {isPositive && (
                    <div className="bg-emerald-500/60 h-3 rounded-r" style={{ width: `${barWidth}%` }} />
                  )}
                </div>
              </div>
              <span className={`w-12 text-right font-mono ${isPositive ? 'text-emerald-400' : 'text-red-400'}`}>
                {m.avg_return > 0 ? '+' : ''}{m.avg_return}%
              </span>
              <span className={`w-10 text-right font-mono ${m.win_rate >= 0.6 ? 'text-emerald-600' : m.win_rate <= 0.4 ? 'text-red-600' : 'text-zinc-500'}`}>
                {Math.round(m.win_rate * 100)}%w
              </span>
            </div>
          );
        })}
      </div>
      <p className="text-xs text-zinc-500 mt-3">Avg monthly return (left) • Win rate (right) • Current month highlighted</p>
    </div>
  );
}
