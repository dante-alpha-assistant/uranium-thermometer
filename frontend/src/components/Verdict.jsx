const actionColors = {
  'ACCUMULATE': { bg: 'bg-emerald-900/50', border: 'border-emerald-500', text: 'text-emerald-400', icon: '🟢' },
  'BUY': { bg: 'bg-green-900/30', border: 'border-green-500', text: 'text-green-400', icon: '🟢' },
  'HOLD': { bg: 'bg-yellow-900/30', border: 'border-yellow-500', text: 'text-yellow-400', icon: '🟡' },
  'REDUCE': { bg: 'bg-orange-900/30', border: 'border-orange-500', text: 'text-orange-400', icon: '🟠' },
  'SELL': { bg: 'bg-red-900/30', border: 'border-red-500', text: 'text-red-400', icon: '🔴' },
};

const convictionBars = { HIGH: 3, MEDIUM: 2, LOW: 1 };

export default function Verdict({ verdict }) {
  if (!verdict) return null;
  
  const style = actionColors[verdict.action] || actionColors.HOLD;
  const bars = convictionBars[verdict.conviction] || 1;

  return (
    <div className={`${style.bg} ${style.border} border-2 rounded-xl p-6 mb-6`}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          <span className="text-3xl">{style.icon}</span>
          <div>
            <p className="text-xs text-gray-400 uppercase tracking-widest font-mono">The Machine Says</p>
            <p className={`text-3xl font-black tracking-tight ${style.text}`}>{verdict.action}</p>
          </div>
        </div>
        <div className="text-right">
          <p className="text-xs text-gray-400">Conviction</p>
          <div className="flex gap-1 justify-end mt-1">
            {[1, 2, 3].map(i => (
              <div key={i} className={`w-4 h-4 rounded-sm ${i <= bars ? style.bg.replace('/30', '').replace('/50', '') + ' opacity-100' : 'bg-gray-700 opacity-40'}`}
                style={i <= bars ? { backgroundColor: style.text.includes('emerald') ? '#10b981' : style.text.includes('green') ? '#22c55e' : style.text.includes('yellow') ? '#eab308' : style.text.includes('orange') ? '#f97316' : '#ef4444' } : {}} />
            ))}
          </div>
          <p className={`text-xs font-mono mt-1 ${style.text}`}>{verdict.conviction}</p>
        </div>
      </div>
      <p className="text-gray-300 text-sm">{verdict.detail}</p>
      <div className="mt-3 flex gap-4 text-xs text-gray-500">
        <span>Score: <span className="font-mono text-gray-300">{verdict.composite_score}/100</span></span>
        <span>Bullish: <span className="font-mono text-green-400">{verdict.bullish_tickers}/{verdict.total_tickers}</span></span>
        <span>Bearish: <span className="font-mono text-red-400">{verdict.bearish_tickers}/{verdict.total_tickers}</span></span>
      </div>
    </div>
  );
}
