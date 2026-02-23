import { useState, useEffect } from 'react';

const statusStyle = {
  producing: 'bg-emerald-900/40 text-emerald-400',
  commissioning: 'bg-blue-900/40 text-blue-400',
  construction: 'bg-blue-900/30 text-blue-300',
  permitting: 'bg-amber-900/30 text-amber-400',
  suspended: 'bg-red-900/30 text-red-400',
};
const statusEmoji = { producing: '🟢', commissioning: '🔵', construction: '🔵', permitting: '🟡', suspended: '🔴' };

export default function MinePipeline() {
  const [data, setData] = useState(null);

  useEffect(() => {
    fetch('api/mine-pipeline')
      .then(r => r.json())
      .then(setData)
      .catch(() => {});
  }, []);

  if (!data) return null;

  const { projects, by_year, summary } = data;
  const maxCap = Math.max(...by_year.map(y => y.capacity_mlbs));

  return (
    <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-bold text-white">⛏️ Mine Development Pipeline</h3>
        <div className="flex gap-2">
          <span className="text-xs font-mono px-2 py-1 rounded bg-amber-900/30 text-amber-400">
            {summary.total_pipeline_mlbs}M lbs capacity
          </span>
          <span className={`text-xs font-mono px-2 py-1 rounded ${
            summary.supply_gap_2030_mlbs > 0 ? 'bg-red-900/30 text-red-400' : 'bg-emerald-900/30 text-emerald-400'
          }`}>
            Gap 2030: {summary.supply_gap_2030_mlbs > 0 ? '+' : ''}{summary.supply_gap_2030_mlbs}M lbs
          </span>
        </div>
      </div>

      {/* Year bar chart */}
      <div className="flex items-end gap-1 h-16 mb-4">
        {by_year.map(y => (
          <div key={y.year} className="flex-1 flex flex-col items-center">
            <div className="w-full bg-amber-600/50 rounded-t"
              style={{ height: `${(y.capacity_mlbs / maxCap) * 100}%`, minHeight: 4 }} />
            <span className="text-xs text-gray-600 mt-1">{y.year}</span>
            <span className="text-xs font-mono text-gray-500">{y.capacity_mlbs}M</span>
          </div>
        ))}
      </div>

      {/* Projects table */}
      <div className="overflow-x-auto max-h-52 overflow-y-auto">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-gray-900">
            <tr className="text-gray-500 border-b border-gray-800">
              <th className="text-left p-1.5">Project</th>
              <th className="text-left p-1.5">Company</th>
              <th className="text-center p-1.5">Status</th>
              <th className="text-right p-1.5">Capacity</th>
              <th className="text-right p-1.5">Start</th>
              <th className="text-right p-1.5">Capex</th>
            </tr>
          </thead>
          <tbody>
            {projects.map((p, i) => (
              <tr key={i} className="border-b border-gray-800/50">
                <td className="p-1.5 text-gray-300">{p.name}</td>
                <td className="p-1.5 text-gray-500">{p.company} <span className="text-gray-600">({p.ticker})</span></td>
                <td className="p-1.5 text-center">
                  <span className={`text-xs px-1.5 py-0.5 rounded ${statusStyle[p.status]}`}>
                    {statusEmoji[p.status]} {p.status}
                  </span>
                </td>
                <td className="p-1.5 text-right font-mono text-gray-400">{p.capacity_mlbs}M</td>
                <td className="p-1.5 text-right font-mono text-gray-500">{p.expected_start}</td>
                <td className="p-1.5 text-right font-mono text-gray-600">${p.capex_usd}M</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
