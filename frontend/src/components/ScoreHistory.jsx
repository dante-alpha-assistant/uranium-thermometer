import { useState, useEffect } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, ReferenceArea, Legend } from 'recharts';

export default function ScoreHistory({ symbol = 'URA' }) {
  const [data, setData] = useState([]);
  const [days, setDays] = useState(30);

  useEffect(() => {
    fetch(`api/score-history/${symbol}?days=${days}`)
      .then(r => r.json())
      .then(d => setData(d.history || []))
      .catch(() => {});
  }, [symbol, days]);

  if (data.length < 2) {
    return (
      <div className="u-card p-6">
        <h3 className="text-sm font-semibold text-zinc-200 mb-2">📈 Signal Score History — {symbol}</h3>
        <p className="text-zinc-400 text-sm">Accumulating data... Score history will appear after a few refresh cycles.</p>
      </div>
    );
  }

  const chartData = data.map(d => ({
    time: d.timestamp?.replace('T', ' ') || '',
    score: d.signal_score,
    price: d.price,
    zone: d.zone,
    components: d.components,
  }));

  // Smart x-axis: show time if <3 days of data, otherwise dates
  const uniqueDates = [...new Set(chartData.map(d => d.time.split(' ')[0]))];
  const isShortRange = uniqueDates.length <= 3;
  const formatTick = (v) => {
    if (isShortRange) {
      // Show "Feb 22 03:00" style
      const [date, time] = v.split(' ');
      return time ? `${time}` : date?.slice(5);
    }
    // Show "Feb 16" style
    const dateStr = v.split(' ')[0];
    if (!dateStr) return '';
    const [, m, d] = dateStr.split('-');
    const months = ['', 'Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    return `${months[parseInt(m)] || m} ${parseInt(d)}`;
  };
  // Reduce tick clutter: show max ~6 ticks
  const tickInterval = Math.max(0, Math.floor(chartData.length / 6) - 1);

  return (
    <div className="u-card p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-zinc-200">📈 Signal Score History — {symbol}</h3>
        <div className="flex gap-2">
          {[7, 14, 30].map(d => (
            <button key={d} onClick={() => setDays(d)}
              className={`px-3 py-1 rounded text-xs font-mono ${days === d ? 'bg-emerald-600 text-zinc-100' : 'bg-zinc-800 text-zinc-300 hover:bg-gray-700'}`}>
              {d}d
            </button>
          ))}
        </div>
      </div>
      <ResponsiveContainer width="100%" height={250}>
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
          <XAxis dataKey="time" tick={{ fill: '#9CA3AF', fontSize: 10 }} tickFormatter={formatTick} interval={tickInterval} />
          <YAxis yAxisId="score" domain={[0, 100]} tick={{ fill: '#9CA3AF', fontSize: 11 }} />
          <YAxis yAxisId="price" orientation="right" tick={{ fill: '#6366f1', fontSize: 10 }} tickFormatter={v => `$${v}`} />
          <Tooltip content={({ active, payload }) => {
            if (!active || !payload?.length) return null;
            const d = payload[0]?.payload;
            if (!d) return null;
            const c = d.components;
            return (
              <div style={{ backgroundColor: '#1F2937', border: '1px solid #374151', borderRadius: 8, padding: '10px 14px', color: '#fff', fontSize: 12, minWidth: 200 }}>
                <div style={{ marginBottom: 6, color: '#9CA3AF', fontSize: 11 }}>{d.time}</div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                  <span style={{ color: '#10b981', fontWeight: 'bold' }}>Score: {d.score}/100</span>
                  <span style={{ color: '#6366f1' }}>${d.price?.toFixed(2)}</span>
                </div>
                {c && (
                  <div style={{ borderTop: '1px solid #374151', paddingTop: 6, marginTop: 4 }}>
                    <div style={{ color: '#6B7280', fontSize: 10, marginBottom: 4 }}>Score Breakdown:</div>
                    {c.range && <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                      <span>Range ({c.range.weight}%)</span><span style={{ color: c.range.score > 60 ? '#10b981' : c.range.score < 40 ? '#ef4444' : '#9CA3AF' }}>{c.range.score.toFixed(0)} — {c.range.label}</span>
                    </div>}
                    {c.rsi && <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                      <span>RSI ({c.rsi.weight}%)</span><span style={{ color: c.rsi.score > 60 ? '#10b981' : c.rsi.score < 40 ? '#ef4444' : '#9CA3AF' }}>{c.rsi.score.toFixed(0)} — {c.rsi.label}</span>
                    </div>}
                    {c.macd && <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                      <span>MACD ({c.macd.weight}%)</span><span style={{ color: c.macd.score > 60 ? '#10b981' : c.macd.score < 40 ? '#ef4444' : '#9CA3AF' }}>{c.macd.score.toFixed(0)} — {c.macd.label}</span>
                    </div>}
                    {c.bollinger && <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
                      <span>Bollinger ({c.bollinger.weight}%)</span><span style={{ color: c.bollinger.score > 60 ? '#10b981' : c.bollinger.score < 40 ? '#ef4444' : '#9CA3AF' }}>{c.bollinger.score.toFixed(0)} — {c.bollinger.label}</span>
                    </div>}
                  </div>
                )}
              </div>
            );
          }} />
          <ReferenceArea y1={70} y2={100} fill="#16a34a" fillOpacity={0.08} />
          <ReferenceArea y1={0} y2={30} fill="#dc2626" fillOpacity={0.08} />
          <ReferenceLine y={70} stroke="#16a34a" strokeDasharray="3 3" label={{ value: 'BUY', fill: '#16a34a', fontSize: 10 }} />
          <ReferenceLine y={30} stroke="#dc2626" strokeDasharray="3 3" label={{ value: 'SELL', fill: '#dc2626', fontSize: 10 }} />
          <ReferenceLine y={50} stroke="#6B7280" strokeDasharray="3 3" />
          <Line type="monotone" dataKey="score" stroke="#10b981" strokeWidth={2} dot={false} yAxisId="score" />
          <Line type="monotone" dataKey="price" stroke="#6366f1" strokeWidth={1.5} dot={false} yAxisId="price" strokeDasharray="4 2" />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
