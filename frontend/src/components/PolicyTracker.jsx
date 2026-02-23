import { useState, useEffect } from 'react';

const sentimentStyle = {
  BULLISH: 'bg-emerald-900/30 text-emerald-400',
  BEARISH: 'bg-red-900/30 text-red-400',
  NEUTRAL: 'bg-gray-800 text-gray-500',
};
const momentumStyle = {
  'STRONG TAILWIND': 'bg-emerald-900/30 text-emerald-400',
  'TAILWIND': 'bg-emerald-900/20 text-emerald-400',
  'HEADWIND': 'bg-red-900/20 text-red-400',
  'NEUTRAL': 'bg-gray-800 text-gray-400',
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
    <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-bold text-white">🏛️ Nuclear Policy Tracker</h3>
        <div className="flex gap-2">
          <span className={`text-xs font-mono px-2 py-1 rounded ${momentumStyle[summary.momentum] || ''}`}>
            {summary.momentum}
          </span>
          <span className="text-xs font-mono px-2 py-1 rounded bg-emerald-900/20 text-emerald-400">
            {summary.bullish_count}↑
          </span>
          <span className="text-xs font-mono px-2 py-1 rounded bg-red-900/20 text-red-400">
            {summary.bearish_count}↓
          </span>
        </div>
      </div>
      <div className="overflow-x-auto max-h-64 overflow-y-auto">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-gray-900">
            <tr className="text-gray-500 border-b border-gray-800">
              <th className="text-left p-1.5">Bill</th>
              <th className="text-left p-1.5">Title</th>
              <th className="text-center p-1.5">Status</th>
              <th className="text-center p-1.5">Signal</th>
              <th className="text-right p-1.5">Date</th>
            </tr>
          </thead>
          <tbody>
            {bills.slice(0, 12).map((b) => (
              <tr key={b.id} className="border-b border-gray-800/50">
                <td className="p-1.5 font-mono text-gray-400">
                  <a href={b.link} target="_blank" rel="noopener" className="hover:text-white">{b.number}</a>
                </td>
                <td className="p-1.5 text-gray-300 truncate max-w-64" title={b.title}>{b.title}</td>
                <td className="p-1.5 text-center">
                  <span className="text-xs text-gray-500">{b.status}</span>
                </td>
                <td className="p-1.5 text-center">
                  <span className={`text-xs font-mono px-1.5 py-0.5 rounded ${sentimentStyle[b.sentiment]}`}>
                    {b.sentiment === 'BULLISH' ? '🟢' : b.sentiment === 'BEARISH' ? '🔴' : '⚪'}
                  </span>
                </td>
                <td className="p-1.5 text-right font-mono text-gray-500">{b.date}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-gray-600 mt-2">119th Congress • GovTrack data • 6h refresh</p>
    </div>
  );
}
