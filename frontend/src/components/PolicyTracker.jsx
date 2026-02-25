import { useState, useEffect } from 'react';

const sentimentStyle = {
  BULLISH: 'bg-zinc-800/40 text-emerald-400/60',
  BEARISH: 'bg-zinc-800/40 text-red-400/60',
  NEUTRAL: 'bg-zinc-800 text-zinc-400',
};
const momentumStyle = {
  'STRONG TAILWIND': 'bg-zinc-800/40 text-emerald-400/60',
  'TAILWIND': 'bg-zinc-800/40 text-emerald-400/60',
  'HEADWIND': 'bg-zinc-800/40 text-red-400/60',
  'NEUTRAL': 'bg-zinc-800 text-zinc-300',
};

export default function PolicyTracker() {
  const [data, setData] = useState(null);

  useEffect(() => {
    fetch('api/policy-tracker')
      .then(r => r.json())
      .then(setData)
      .catch(() => {});
  }, []);

  if (!data?.bills?.length) return null;

  const { bills, summary } = data;

  return (
    <div className="u-card p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-zinc-200">🏛️ Nuclear Policy Tracker</h3>
        <div className="flex gap-2">
          <span className={`text-xs font-mono px-2 py-1 rounded ${momentumStyle[summary.momentum] || ''}`}>
            {summary.momentum}
          </span>
          <span className="text-xs font-mono px-2 py-1 rounded bg-zinc-800/40 text-emerald-400">
            {summary.bullish_count}↑
          </span>
          <span className="text-xs font-mono px-2 py-1 rounded bg-zinc-800/40 text-red-400">
            {summary.bearish_count}↓
          </span>
        </div>
      </div>
      <div className="overflow-x-auto max-h-64 overflow-y-auto">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-gray-900">
            <tr className="text-zinc-400 border-b border-zinc-800/50">
              <th className="text-left p-1.5">Bill</th>
              <th className="text-left p-1.5">Title</th>
              <th className="text-center p-1.5">Status</th>
              <th className="text-center p-1.5">Signal</th>
              <th className="text-right p-1.5">Date</th>
            </tr>
          </thead>
          <tbody>
            {bills.slice(0, 12).map((b) => (
              <tr key={b.id} className="border-b border-zinc-800/50/50">
                <td className="p-1.5 font-mono text-zinc-300">
                  <a href={b.link} target="_blank" rel="noopener" className="hover:text-zinc-100">{b.number}</a>
                </td>
                <td className="p-1.5 text-zinc-200 truncate max-w-64" title={b.title}>{b.title}</td>
                <td className="p-1.5 text-center">
                  <span className="text-xs text-zinc-400">{b.status}</span>
                </td>
                <td className="p-1.5 text-center">
                  <span className={`text-xs font-mono px-1.5 py-0.5 rounded ${sentimentStyle[b.sentiment]}`}>
                    {b.sentiment === 'BULLISH' ? '🟢' : b.sentiment === 'BEARISH' ? '🔴' : '⚪'}
                  </span>
                </td>
                <td className="p-1.5 text-right font-mono text-zinc-400">{b.date}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-zinc-500 mt-2">119th Congress • GovTrack data • 6h refresh</p>
    </div>
  );
}
