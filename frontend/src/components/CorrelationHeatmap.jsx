import { useState, useEffect } from 'react';

export default function CorrelationHeatmap() {
  const [data, setData] = useState(null);

  useEffect(() => {
    fetch('api/correlations')
      .then(r => r.json())
      .then(setData)
      .catch(() => {});
  }, []);

  if (!data?.symbols?.length || data.insufficient_data) return null;

  const { matrix, symbols } = data;

  const getColor = (v) => {
    if (v === 1) return 'bg-emerald-600';
    if (v >= 0.8) return 'bg-emerald-700/80';
    if (v >= 0.6) return 'bg-emerald-800/60';
    if (v >= 0.4) return 'bg-yellow-700/50';
    if (v >= 0.2) return 'bg-yellow-800/40';
    if (v >= 0) return 'bg-gray-700/40';
    return 'bg-red-800/60';
  };

  const getTextColor = (v) => {
    if (v >= 0.7) return 'text-zinc-100';
    if (v < 0) return 'text-red-300';
    return 'text-zinc-200';
  };

  return (
    <div className="u-card p-6">
      <h3 className="text-sm font-semibold text-zinc-200 mb-1">🔗 Correlation Matrix</h3>
      <p className="text-xs text-zinc-400 mb-4">3-month daily return correlations • {data.days} trading days</p>
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr>
              <th className="p-1"></th>
              {symbols.map(s => (
                <th key={s} className="p-1 text-zinc-300 font-mono text-center">{s.replace('.IL','')}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {symbols.map(s1 => (
              <tr key={s1}>
                <td className="p-1 text-zinc-300 font-mono pr-2">{s1.replace('.IL','')}</td>
                {symbols.map(s2 => {
                  const v = matrix[s1]?.[s2] ?? 0;
                  return (
                    <td key={s2} className={`p-1.5 text-center font-mono rounded ${getColor(v)} ${getTextColor(v)}`}>
                      {v === 1 ? '1.00' : v.toFixed(2)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
