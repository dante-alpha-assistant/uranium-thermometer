import { useState, useEffect } from 'react';

const signalStyle = {
  TAKE_PROFIT: 'bg-emerald-900/40 text-emerald-400',
  STOP_LOSS: 'bg-red-900/40 text-red-400',
  ENTRY: 'bg-blue-900/40 text-blue-400',
};
const signalEmoji = { TAKE_PROFIT: '💰', STOP_LOSS: '🛑', ENTRY: '🎯' };

export default function SwingRules() {
  const [data, setData] = useState(null);

  useEffect(() => {
    fetch('api/swing-rules')
      .then(r => r.json())
      .then(setData)
      .catch(() => {});
  }, []);

  if (!data) return null;

  const { swing_rules: rules, signals, portfolio, cooldowns } = data;

  return (
    <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-bold text-white">🎯 Swing Trading Rules</h3>
        <span className={`text-xs font-mono px-2 py-1 rounded ${rules.enabled ? 'bg-emerald-900/30 text-emerald-400' : 'bg-gray-800 text-gray-500'}`}>
          {rules.enabled ? 'ACTIVE' : 'DISABLED'}
        </span>
      </div>

      {/* Rules summary */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <div className="bg-gray-800/40 rounded-lg p-2 text-center">
          <p className="text-xs text-gray-500">Take Profit</p>
          <p className="font-mono text-emerald-400 font-bold">+{rules.take_profit_pct}%</p>
        </div>
        <div className="bg-gray-800/40 rounded-lg p-2 text-center">
          <p className="text-xs text-gray-500">Stop Loss</p>
          <p className="font-mono text-red-400 font-bold">-{rules.stop_loss_pct}%</p>
        </div>
        <div className="bg-gray-800/40 rounded-lg p-2 text-center">
          <p className="text-xs text-gray-500">Entry Score</p>
          <p className="font-mono text-blue-400 font-bold">≥ {rules.entry_score_min}</p>
        </div>
        <div className="bg-gray-800/40 rounded-lg p-2 text-center">
          <p className="text-xs text-gray-500">Re-entry</p>
          <p className="font-mono text-gray-400 font-bold">≤ {rules.reentry_score_max}</p>
        </div>
      </div>

      {/* Active signals */}
      {signals.length > 0 ? (
        <div className="space-y-2 mb-3">
          <h4 className="text-xs text-gray-500 font-bold">ACTIVE SIGNALS</h4>
          {signals.map((s, i) => (
            <div key={i} className={`flex items-center justify-between p-2 rounded-lg ${signalStyle[s.signal]} bg-opacity-20`}>
              <div className="flex items-center gap-2">
                <span>{signalEmoji[s.signal]}</span>
                <span className="font-mono text-sm">{s.symbol}</span>
                <span className={`text-xs px-1.5 py-0.5 rounded ${signalStyle[s.signal]}`}>{s.signal.replace('_', ' ')}</span>
              </div>
              <span className="text-xs text-gray-400">{s.reason}</span>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-xs text-gray-600 mb-3">No active swing signals — all scores below entry threshold ({rules.entry_score_min})</p>
      )}

      {/* Cooldowns */}
      {cooldowns.length > 0 && (
        <p className="text-xs text-gray-600">
          Cooldown (waiting for score ≤{rules.reentry_score_max}): {cooldowns.join(', ')}
        </p>
      )}

      <div className="flex justify-between text-xs text-gray-600 mt-2">
        <span>Portfolio: ${portfolio.total_value.toLocaleString()} ({portfolio.positions} positions)</span>
        <span>Max per ticker: ${(rules.portfolio_size * rules.max_position_pct / 100).toLocaleString()}</span>
      </div>
    </div>
  );
}
