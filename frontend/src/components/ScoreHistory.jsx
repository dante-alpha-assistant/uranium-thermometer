import { useState, useEffect } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, ReferenceArea } from 'recharts';

export default function ScoreHistory({ symbol = 'URA' }) {
  const [data, setData] = useState([]);
  const [days, setDays] = useState(30);

  useEffect(() => {
    fetch(`/api/score-history/${symbol}?days=${days}`)
      .then(r => r.json())
      .then(d => setData(d.history || []))
      .catch(() => {});
  }, [symbol, days]);

  if (data.length < 2) {
    return (
      <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
        <h3 className="text-lg font-bold text-white mb-2">📈 Signal Score History — {symbol}</h3>
        <p className="text-gray-500 text-sm">Accumulating data... Score history will appear after a few refresh cycles.</p>
      </div>
    );
  }

  const chartData = data.map(d => ({
    time: d.timestamp?.replace('T', ' ') || '',
    score: d.signal_score,
    price: d.price,
    zone: d.zone,
  }));

  return (
    <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-bold text-white">📈 Signal Score History — {symbol}</h3>
        <div className="flex gap-2">
          {[7, 14, 30].map(d => (
            <button key={d} onClick={() => setDays(d)}
              className={`px-3 py-1 rounded text-xs font-mono ${days === d ? 'bg-emerald-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}>
              {d}d
            </button>
          ))}
        </div>
      </div>
      <ResponsiveContainer width="100%" height={250}>
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
          <XAxis dataKey="time" tick={{ fill: '#9CA3AF', fontSize: 10 }} tickFormatter={v => v.split(' ')[0]?.slice(5)} />
          <YAxis domain={[0, 100]} tick={{ fill: '#9CA3AF', fontSize: 11 }} />
          <Tooltip contentStyle={{ backgroundColor: '#1F2937', border: '1px solid #374151', borderRadius: 8, color: '#fff' }}
            formatter={(v, name) => [name === 'score' ? `${v}/100` : `$${v}`, name === 'score' ? 'Signal Score' : 'Price']} />
          <ReferenceArea y1={70} y2={100} fill="#16a34a" fillOpacity={0.08} />
          <ReferenceArea y1={0} y2={30} fill="#dc2626" fillOpacity={0.08} />
          <ReferenceLine y={70} stroke="#16a34a" strokeDasharray="3 3" label={{ value: 'BUY', fill: '#16a34a', fontSize: 10 }} />
          <ReferenceLine y={30} stroke="#dc2626" strokeDasharray="3 3" label={{ value: 'SELL', fill: '#dc2626', fontSize: 10 }} />
          <ReferenceLine y={50} stroke="#6B7280" strokeDasharray="3 3" />
          <Line type="monotone" dataKey="score" stroke="#10b981" strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
