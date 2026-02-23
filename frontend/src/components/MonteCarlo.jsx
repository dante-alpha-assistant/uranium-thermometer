import { useState, useEffect } from 'react';
import { AreaChart, Area, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

export default function MonteCarlo({ symbol = 'URA' }) {
  const [data, setData] = useState(null);
  const [days, setDays] = useState(30);
  const [drift, setDrift] = useState('neutral');

  useEffect(() => {
    fetch(`api/monte-carlo/${symbol}?days=${days}&simulations=1000&drift_mode=${drift}`)
      .then(r => r.json())
      .then(setData)
      .catch(() => {});
  }, [symbol, days, drift]);

  if (!data?.bands) return null;

  const chartData = data.bands.p50.map((_, i) => ({
    day: i,
    p5: data.bands.p5[i],
    p25: data.bands.p25[i],
    p50: data.bands.p50[i],
    p75: data.bands.p75[i],
    p95: data.bands.p95[i],
  }));

  const tickInterval = Math.max(0, Math.floor(chartData.length / 6) - 1);
  const pct = data.percentiles;
  const zp = data.zone_probabilities || {};
  const upside = pct.p75 ? ((pct.p75 - data.current_price) / data.current_price * 100).toFixed(1) : null;
  const downside = pct.p25 ? ((pct.p25 - data.current_price) / data.current_price * 100).toFixed(1) : null;

  return (
    <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
      <div className="flex items-center justify-between mb-1">
        <h3 className="text-lg font-bold text-white">🎲 Price Simulation — {symbol}</h3>
        <div className="flex gap-2">
          {[30, 60, 90].map(d => (
            <button key={d} onClick={() => setDays(d)}
              className={`px-3 py-1 rounded text-xs font-mono ${days === d ? 'bg-emerald-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}>
              {d}d
            </button>
          ))}
        </div>
      </div>
      <div className="flex items-center gap-3 mb-4">
        <p className="text-xs text-gray-500">
          1,000 paths • Vol: {data.vol_annual}%/yr • Drift: {data.drift_annual > 0 ? '+' : ''}{data.drift_annual}%/yr
        </p>
        <div className="flex gap-1 ml-auto">
          {[['neutral', 'Risk-Neutral'], ['historical', 'Historical']].map(([mode, label]) => (
            <button key={mode} onClick={() => setDrift(mode)}
              className={`px-2 py-0.5 rounded text-xs ${drift === mode ? 'bg-blue-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}>
              {label}
            </button>
          ))}
        </div>
      </div>

      <ResponsiveContainer width="100%" height={280}>
        <AreaChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
          <XAxis dataKey="day" tick={{ fill: '#9CA3AF', fontSize: 10 }} interval={tickInterval}
            tickFormatter={v => `D${v}`} />
          <YAxis tick={{ fill: '#9CA3AF', fontSize: 11 }} tickFormatter={v => `$${v.toFixed(0)}`} domain={['auto', 'auto']} />
          <Tooltip contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151', borderRadius: 8, color: '#fff' }}
            formatter={(v) => [`$${v.toFixed(2)}`]} labelFormatter={v => `Day ${v}`} />
          <Area type="monotone" dataKey="p95" stroke="none" fill="#10b981" fillOpacity={0.08} />
          <Area type="monotone" dataKey="p75" stroke="none" fill="#10b981" fillOpacity={0.12} />
          <Area type="monotone" dataKey="p25" stroke="none" fill="#10b981" fillOpacity={0.12} />
          <Area type="monotone" dataKey="p5" stroke="none" fill="#0f172a" fillOpacity={1} />
          <Line type="monotone" dataKey="p50" stroke="#10b981" strokeWidth={2} dot={false} />
          <Line type="monotone" dataKey="p75" stroke="#10b981" strokeWidth={1} strokeDasharray="4 4" dot={false} opacity={0.5} />
          <Line type="monotone" dataKey="p25" stroke="#10b981" strokeWidth={1} strokeDasharray="4 4" dot={false} opacity={0.5} />
        </AreaChart>
      </ResponsiveContainer>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4">
        <div className="bg-gray-800/50 rounded p-2 text-center">
          <p className="text-xs text-gray-500">Upside (p75)</p>
          <p className={`font-mono text-sm font-bold ${upside >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
            {upside > 0 ? '+' : ''}{upside}%
          </p>
          <p className="text-xs text-gray-600">${pct.p75}</p>
        </div>
        <div className="bg-gray-800/50 rounded p-2 text-center">
          <p className="text-xs text-gray-500">Downside (p25)</p>
          <p className={`font-mono text-sm font-bold ${downside >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
            {downside > 0 ? '+' : ''}{downside}%
          </p>
          <p className="text-xs text-gray-600">${pct.p25}</p>
        </div>
        {zp.prob_green != null && (
          <div className="bg-gray-800/50 rounded p-2 text-center">
            <p className="text-xs text-gray-500">P(Green Zone)</p>
            <p className="font-mono text-sm font-bold text-emerald-400">{zp.prob_green}%</p>
            <p className="text-xs text-gray-600">≤${zp.green_price}</p>
          </div>
        )}
        {zp.prob_red != null && (
          <div className="bg-gray-800/50 rounded p-2 text-center">
            <p className="text-xs text-gray-500">P(Red Zone)</p>
            <p className="font-mono text-sm font-bold text-red-400">{zp.prob_red}%</p>
            <p className="text-xs text-gray-600">≥${zp.red_price}</p>
          </div>
        )}
      </div>
      <a href="#/simulation/dashboard" className="block text-center text-xs text-indigo-400 hover:text-indigo-300 mt-3">
        Full Simulation Dashboard →
      </a>
    </div>
  );
}
