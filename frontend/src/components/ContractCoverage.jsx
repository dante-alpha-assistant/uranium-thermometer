import { useState, useEffect } from 'react';

export default function ContractCoverage() {
  const [data, setData] = useState(null);
  useEffect(() => {
    fetch('api/contract-coverage').then(r => r.json()).then(setData).catch(() => {});
  }, []);
  if (!data) return null;

  const us = data.us_utilities.coverage;
  const eu = data.eu_utilities.coverage;
  const maxUncov = Math.max(...us.map(c => c.uncovered_mlbs), ...eu.map(c => c.uncovered_mlbs));

  return (
    <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-bold text-white">📋 Contract Coverage Gap</h3>
        <span className="text-xs font-mono px-2 py-1 rounded bg-red-900/30 text-red-400">
          {data.signal}
        </span>
      </div>

      <div className="grid grid-cols-3 gap-3 mb-4">
        <div className="bg-gray-800/40 rounded-lg p-2 text-center">
          <p className="text-xs text-gray-500">Uncovered 2028</p>
          <p className="font-mono text-amber-400 font-bold">{data.total_uncovered_2028_mlbs}M lbs</p>
        </div>
        <div className="bg-gray-800/40 rounded-lg p-2 text-center">
          <p className="text-xs text-gray-500">Uncovered 2030</p>
          <p className="font-mono text-red-400 font-bold">{data.total_uncovered_2030_mlbs}M lbs</p>
        </div>
        <div className="bg-gray-800/40 rounded-lg p-2 text-center">
          <p className="text-xs text-gray-500">US+EU Demand</p>
          <p className="font-mono text-gray-300">{data.us_utilities.annual_requirement_mlbs + data.eu_utilities.annual_requirement_mlbs}M lbs/yr</p>
        </div>
      </div>

      {/* Stacked uncovered bars by year */}
      <div className="flex items-end gap-1 h-24 mb-1">
        {us.map((c, i) => {
          const euMatch = eu[i] || { uncovered_mlbs: 0 };
          const total = c.uncovered_mlbs + euMatch.uncovered_mlbs;
          const usPct = (c.uncovered_mlbs / maxUncov) * 80;
          const euPct = (euMatch.uncovered_mlbs / maxUncov) * 80;
          return (
            <div key={c.year} className="flex-1 flex flex-col items-center justify-end h-full">
              <span className="text-xs font-mono text-gray-500 mb-0.5">{total.toFixed(0)}M</span>
              <div className="w-full flex flex-col justify-end" style={{ height: '80%' }}>
                <div className="bg-blue-600/60 rounded-t" style={{ height: `${euPct}%`, minHeight: euPct > 0 ? 2 : 0 }}
                  title={`EU: ${euMatch.uncovered_mlbs}M uncovered`} />
                <div className="bg-amber-500/60" style={{ height: `${usPct}%`, minHeight: 2 }}
                  title={`US: ${c.uncovered_mlbs}M uncovered`} />
              </div>
              <span className="text-xs text-gray-600 mt-1">{c.year}</span>
            </div>
          );
        })}
      </div>
      <div className="flex gap-3 text-xs text-gray-600 mb-3">
        <span><span className="inline-block w-2 h-2 rounded bg-amber-500/60 mr-1" />US uncovered</span>
        <span><span className="inline-block w-2 h-2 rounded bg-blue-600/60 mr-1" />EU uncovered</span>
      </div>

      {/* Coverage % table */}
      <div className="flex gap-1">
        {us.map(c => (
          <div key={c.year} className="flex-1 text-center">
            <div className={`text-xs font-mono rounded py-0.5 ${
              c.contracted_pct >= 70 ? 'bg-emerald-900/20 text-emerald-400' :
              c.contracted_pct >= 40 ? 'bg-amber-900/20 text-amber-400' :
              'bg-red-900/20 text-red-400'
            }`}>{c.contracted_pct}%</div>
          </div>
        ))}
      </div>
      <p className="text-xs text-gray-600 text-center mt-0.5">US contracted %</p>

      <p className="text-xs text-gray-600 mt-3">{data.insight}</p>
    </div>
  );
}
