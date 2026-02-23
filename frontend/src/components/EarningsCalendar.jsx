import { useState, useEffect } from 'react';

export default function EarningsCalendar() {
  const [data, setData] = useState(null);

  useEffect(() => {
    fetch('api/earnings-calendar')
      .then(r => r.json())
      .then(setData)
      .catch(() => {});
  }, []);

  if (!data) return null;

  const { upcoming, recent } = data;

  const fmtDate = (d) => {
    const [,m,day] = d.split('-');
    const months = ['','Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    return `${months[parseInt(m)]} ${parseInt(day)}`;
  };

  return (
    <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
      <h3 className="text-lg font-bold text-white mb-4">📅 Earnings Calendar</h3>

      {upcoming?.length > 0 && (
        <div className="mb-4">
          <p className="text-xs text-gray-500 font-bold mb-2">UPCOMING</p>
          <div className="space-y-1.5">
            {upcoming.map((e, i) => (
              <div key={i} className="flex items-center justify-between text-xs bg-gray-800/30 rounded px-3 py-2">
                <div className="flex items-center gap-3">
                  <span className="text-amber-400 font-mono w-16">{fmtDate(e.date)}</span>
                  <span className="text-gray-300 font-mono">{e.symbol}</span>
                </div>
                <span className="text-gray-500">
                  {e.eps_estimate != null ? `Est: $${e.eps_estimate}` : 'No estimate'}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {recent?.length > 0 && (
        <div>
          <p className="text-xs text-gray-500 font-bold mb-2">RECENT RESULTS</p>
          <div className="space-y-1.5">
            {recent.slice(0, 10).map((e, i) => (
              <div key={i} className="flex items-center justify-between text-xs bg-gray-800/30 rounded px-3 py-2">
                <div className="flex items-center gap-3">
                  <span className="text-gray-500 font-mono w-16">{fmtDate(e.date)}</span>
                  <span className="text-gray-300 font-mono">{e.symbol}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-gray-500">
                    {e.eps_actual != null ? `$${e.eps_actual}` : '—'}
                    {e.eps_estimate != null ? ` / $${e.eps_estimate}` : ''}
                  </span>
                  {e.surprise_pct != null && (
                    <span className={`font-mono px-1.5 py-0.5 rounded text-xs ${e.beat ? 'bg-emerald-900/40 text-emerald-400' : 'bg-red-900/40 text-red-400'}`}>
                      {e.surprise_pct > 0 ? '+' : ''}{e.surprise_pct.toFixed(1)}%
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
