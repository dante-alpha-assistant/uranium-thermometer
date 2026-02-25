import { useState, useEffect } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, Legend } from 'recharts';

const COLORS = ['#10b981', '#f59e0b', '#3b82f6', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4'];

export default function RelativeStrength() {
  const [period, setPeriod] = useState('30d');
  const [data, setData] = useState(null);

  useEffect(() => {
    fetch(`api/relative-strength?period=${period}`)
      .then(r => r.json())
      .then(setData)
      .catch(() => {});
  }, [period]);

  if (!data?.tickers?.length) return null;

  // Merge all tickers into unified date-keyed rows
  const dateMap = {};
  data.tickers.forEach(t => {
    t.data.forEach(d => {
      if (!dateMap[d.date]) dateMap[d.date] = { date: d.date };
      dateMap[d.date][t.symbol] = d.pct_change;
    });
  });
  const chartData = Object.values(dateMap).sort((a, b) => a.date.localeCompare(b.date));

  const symbols = data.tickers.map(t => t.symbol);

  const formatDate = (v) => {
    if (!v) return '';
    const [, m, d] = v.split('-');
    const months = ['','Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    return `${months[parseInt(m)] || m} ${parseInt(d)}`;
  };

  const tickInterval = Math.max(0, Math.floor(chartData.length / 6) - 1);

  return (
    <div className="u-card p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-zinc-200">📊 Relative Strength</h3>
        <div className="flex gap-2">
          {['7d', '14d', '30d'].map(p => (
            <button key={p} onClick={() => setPeriod(p)}
              className={`px-3 py-1 rounded text-xs font-mono ${period === p ? 'bg-emerald-600 text-zinc-100' : 'bg-zinc-800 text-zinc-300 hover:bg-gray-700'}`}>
              {p}
            </button>
          ))}
        </div>
      </div>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
          <XAxis dataKey="date" tick={{ fill: '#9CA3AF', fontSize: 10 }} tickFormatter={formatDate} interval={tickInterval} />
          <YAxis tick={{ fill: '#9CA3AF', fontSize: 11 }} tickFormatter={v => `${v > 0 ? '+' : ''}${v}%`} />
          <Tooltip
            contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151', borderRadius: 8, color: '#fff' }}
            formatter={(v, name) => [`${v > 0 ? '+' : ''}${v}%`, name]}
            labelFormatter={formatDate}
          />
          <ReferenceLine y={0} stroke="#6B7280" strokeDasharray="3 3" />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          {symbols.map((sym, i) => (
            <Line key={sym} type="monotone" dataKey={sym} stroke={COLORS[i % COLORS.length]}
              strokeWidth={sym === 'URA' ? 2.5 : 1.5} dot={false} opacity={sym === 'URA' ? 1 : 0.7} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
