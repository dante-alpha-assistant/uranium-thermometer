import { useState, useEffect } from 'react';

const regimeStyle = {
  'HERD MODE': { bg: 'bg-red-900/30', text: 'text-red-400', color: '#ef4444' },
  'CONVERGING': { bg: 'bg-amber-900/30', text: 'text-amber-400', color: '#f59e0b' },
  'DIVERSIFIED': { bg: 'bg-emerald-900/30', text: 'text-emerald-400', color: '#10b981' },
};

export default function CorrelationRegime() {
  const [data, setData] = useState(null);
  useEffect(() => { fetch('api/correlation-regime').then(r => r.json()).then(setData).catch(() => {}); }, []);
  if (!data?.cci_history) return null;

  const style = regimeStyle[data.regime] || regimeStyle['DIVERSIFIED'];
  const cci = data.cci;
  const circumference = 2 * Math.PI * 36;
  const dashoffset = circumference * (1 - cci);

  // CCI sparkline
  const hist = data.cci_history;
  const spyHist = data.ura_spy_history;
  const W = 260, H = 50;

  const sparkline = (arr, key, color) => {
    if (arr.length < 3) return null;
    const vals = arr.map(h => h[key]);
    const min = Math.min(...vals), max = Math.max(...vals);
    const range = max - min || 0.01;
    const pts = vals.map((v, i) => `${(i / (vals.length - 1)) * W},${H - ((v - min) / range) * H}`).join(' ');
    return <polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" />;
  };

  return (
    <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-bold text-white">🔗 Correlation Regime</h3>
        <span className={`text-xs font-mono px-2 py-1 rounded ${style.bg} ${style.text}`}>
          {data.regime}
        </span>
      </div>

      <div className="flex items-center gap-6 mb-4">
        {/* CCI Gauge */}
        <div className="text-center flex-shrink-0">
          <svg viewBox="0 0 80 80" className="w-20 h-20">
            <circle cx="40" cy="40" r="36" fill="none" stroke="#1f2937" strokeWidth="6" />
            <circle cx="40" cy="40" r="36" fill="none" stroke={style.color}
              strokeWidth="6" strokeLinecap="round" strokeDasharray={circumference}
              strokeDashoffset={dashoffset} transform="rotate(-90 40 40)" />
            <text x="40" y="37" textAnchor="middle" fill="white" fontSize="14" fontWeight="bold">{(cci * 100).toFixed(0)}%</text>
            <text x="40" y="50" textAnchor="middle" fill="#6b7280" fontSize="7">CCI</text>
          </svg>
        </div>

        {/* Stats */}
        <div className="flex-1 space-y-2">
          <div className="flex justify-between text-xs">
            <span className="text-gray-500">URA-SPY Correlation</span>
            <span className={`font-mono ${data.ura_spy_correlation < 0 ? 'text-emerald-400' : data.ura_spy_correlation > 0.6 ? 'text-red-400' : 'text-gray-300'}`}>
              {data.ura_spy_correlation.toFixed(3)}
            </span>
          </div>
          <div className="flex justify-between text-xs">
            <span className="text-gray-500">90d Baseline CCI</span>
            <span className="font-mono text-gray-400">{data.cci_baseline_90d.toFixed(3)}</span>
          </div>
          {data.decorrelation_event && (
            <div className="bg-emerald-900/20 rounded px-2 py-1 text-xs text-emerald-400">
              🟢 Decorrelation event — uranium diverging from S&P
            </div>
          )}
        </div>
      </div>

      {/* CCI + URA-SPY sparklines */}
      <div className="space-y-2">
        <div>
          <p className="text-xs text-gray-600 mb-0.5">CCI (sector herding) — 90d</p>
          <svg width={W} height={H} className="w-full">
            {/* Threshold lines */}
            <line x1="0" y1={H * 0.3} x2={W} y2={H * 0.3} stroke="#374151" strokeWidth="0.5" strokeDasharray="2,2" />
            <line x1="0" y1={H * 0.6} x2={W} y2={H * 0.6} stroke="#374151" strokeWidth="0.5" strokeDasharray="2,2" />
            {sparkline(hist, 'cci', style.color)}
          </svg>
        </div>
        <div>
          <p className="text-xs text-gray-600 mb-0.5">URA-SPY correlation — 90d</p>
          <svg width={W} height={H} className="w-full">
            <line x1="0" y1={H * 0.5} x2={W} y2={H * 0.5} stroke="#374151" strokeWidth="0.5" />
            {sparkline(spyHist, 'corr', '#6366f1')}
          </svg>
        </div>
      </div>

      <p className="text-xs text-gray-600 mt-2">CCI = avg pairwise correlation among 6 uranium tickers. High CCI = sector moving as one (herding). Low URA-SPY = diversification benefit intact.</p>
    </div>
  );
}
