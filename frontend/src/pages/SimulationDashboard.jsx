import { useState, useEffect, useCallback, useRef } from 'react';
import { Link } from 'react-router-dom';

const TICKERS = ['URA', 'CCJ', 'UEC', 'UUUU', 'DNN', 'NXE', 'OKLO', 'LEU', 'KAP.IL', 'PDN.AX', 'U-UN.TO'];

// --- Waterfall Chart ---
function WaterfallChart({ adjustments, baseDrift, adjustedDrift, baseVol, adjustedVol }) {
  if (!adjustments?.length) return null;
  const items = [
    { label: 'Base Drift', value: baseDrift, cumulative: baseDrift, type: 'base' },
    ...adjustments.map(a => {
      const val = parseFloat(a.drift_impact || a.vol_impact || '0');
      return { label: a.factor, value: val, detail: a.value, type: val >= 0 ? 'positive' : 'negative', isVol: !!a.vol_impact };
    }),
    { label: 'Final Drift', value: adjustedDrift, cumulative: adjustedDrift, type: 'total' },
  ];

  const maxAbs = Math.max(...items.map(i => Math.abs(i.value)), Math.abs(adjustedDrift), Math.abs(baseDrift)) * 1.2;
  const center = 50;
  const scale = (v) => (v / maxAbs) * 40;

  return (
    <div className="space-y-1.5">
      <h4 className="text-sm font-bold text-gray-400 mb-2">Signal Waterfall</h4>
      {items.map((item, i) => {
        const w = Math.abs(scale(item.value));
        const isPos = item.value >= 0;
        const color = item.type === 'base' ? 'bg-gray-600' :
                      item.type === 'total' ? (item.value >= baseDrift ? 'bg-indigo-500' : 'bg-amber-500') :
                      item.isVol ? 'bg-amber-500/70' :
                      isPos ? 'bg-emerald-500' : 'bg-red-500';
        return (
          <div key={i} className="flex items-center gap-2">
            <span className="text-xs text-gray-500 w-24 text-right truncate">{item.label}</span>
            <div className="flex-1 h-5 relative">
              <div className="absolute inset-0 bg-gray-800/30 rounded" />
              <div className="absolute top-0 bottom-0 w-px bg-gray-700" style={{ left: `${center}%` }} />
              <div className={`absolute top-0 bottom-0 rounded ${color} transition-all duration-500`}
                style={{
                  left: isPos ? `${center}%` : `${center - w}%`,
                  width: `${w}%`,
                }} />
            </div>
            <span className={`text-xs font-mono w-14 ${isPos ? 'text-emerald-400' : 'text-red-400'}`}>
              {item.value > 0 ? '+' : ''}{item.value.toFixed(1)}%
            </span>
          </div>
        );
      })}
      <div className="flex items-center gap-2 mt-1 pt-1 border-t border-gray-800">
        <span className="text-xs text-gray-500 w-24 text-right">Vol Adj</span>
        <div className="flex-1">
          <span className="text-xs font-mono text-amber-400">{baseVol}% → {adjustedVol}%</span>
        </div>
      </div>
    </div>
  );
}

// --- Confidence Meter ---
function ConfidenceMeter({ adjustments }) {
  if (!adjustments?.length) return null;
  const bullish = adjustments.filter(a => parseFloat(a.drift_impact || '0') > 0).length;
  const bearish = adjustments.filter(a => parseFloat(a.drift_impact || '0') < 0).length;
  const total = adjustments.filter(a => a.drift_impact).length;
  const agreement = total > 0 ? Math.abs(bullish - bearish) / total : 0;
  const confidence = Math.round(agreement * 100);
  const direction = bullish > bearish ? 'BULLISH' : bearish > bullish ? 'BEARISH' : 'MIXED';

  const circumference = 2 * Math.PI * 40;
  const dashoffset = circumference * (1 - confidence / 100);

  return (
    <div className="text-center">
      <svg viewBox="0 0 100 100" className="w-28 h-28 mx-auto">
        <circle cx="50" cy="50" r="40" fill="none" stroke="#1f2937" strokeWidth="8" />
        <circle cx="50" cy="50" r="40" fill="none"
          stroke={confidence > 60 ? '#10b981' : confidence > 30 ? '#f59e0b' : '#6b7280'}
          strokeWidth="8" strokeLinecap="round" strokeDasharray={circumference}
          strokeDashoffset={dashoffset} transform="rotate(-90 50 50)"
          className="transition-all duration-1000" />
        <text x="50" y="46" textAnchor="middle" fill="white" fontSize="18" fontWeight="bold">{confidence}%</text>
        <text x="50" y="60" textAnchor="middle" fill="#9ca3af" fontSize="8">CONFIDENCE</text>
      </svg>
      <div className="mt-1">
        <span className={`text-xs font-bold ${direction === 'BULLISH' ? 'text-emerald-400' : direction === 'BEARISH' ? 'text-red-400' : 'text-gray-400'}`}>
          {bullish} bullish / {bearish} bearish
        </span>
        <p className="text-xs text-gray-600 mt-0.5">{direction === 'MIXED' ? 'Low agreement — wider uncertainty' : `Signals ${direction.toLowerCase()} aligned`}</p>
      </div>
    </div>
  );
}

// --- Enhanced Fan Chart with animation ---
function EnhancedFanChart({ data }) {
  const [progress, setProgress] = useState(0);
  const animRef = useRef(null);

  useEffect(() => {
    setProgress(0);
    let start = null;
    const animate = (ts) => {
      if (!start) start = ts;
      const p = Math.min((ts - start) / 1200, 1);
      setProgress(p);
      if (p < 1) animRef.current = requestAnimationFrame(animate);
    };
    animRef.current = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(animRef.current);
  }, [data]);

  if (!data?.percentiles) return null;
  const p = data.percentiles;
  const days = p.p50?.length || 0;
  if (!days) return null;

  const visibleDays = Math.floor(days * progress);
  const allVals = [...(p.p5 || []).slice(0, visibleDays), ...(p.p95 || []).slice(0, visibleDays), data.current_price];
  const minV = Math.min(...allVals), maxV = Math.max(...allVals);
  const range = maxV - minV || 1;
  const W = 800, H = 320, pad = 50;

  const x = (i) => pad + (i / Math.max(days - 1, 1)) * (W - 2 * pad);
  const y = (v) => H - pad - ((v - minV) / range) * (H - 2 * pad);

  const buildPath = (arr) => arr.slice(0, visibleDays).map((v, i) => `${i === 0 ? 'M' : 'L'}${x(i)},${y(v)}`).join(' ');
  const buildArea = (top, bot) => {
    const t = top.slice(0, visibleDays);
    const b = [...bot.slice(0, visibleDays)].reverse();
    return t.map((v, i) => `${i === 0 ? 'M' : 'L'}${x(i)},${y(v)}`).join(' ') +
           b.map((v, i) => `L${x(visibleDays - 1 - i)},${y(v)}`).join(' ') + 'Z';
  };

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full">
      {/* Grid */}
      {[0.25, 0.5, 0.75].map(f => (
        <line key={f} x1={pad} y1={pad + f * (H - 2 * pad)} x2={W - pad} y2={pad + f * (H - 2 * pad)}
          stroke="#1f2937" strokeWidth="0.5" />
      ))}
      {/* Bands */}
      {p.p5 && p.p95 && <path d={buildArea(p.p95, p.p5)} fill="rgba(99,102,241,0.08)" />}
      {p.p25 && p.p75 && <path d={buildArea(p.p75, p.p25)} fill="rgba(99,102,241,0.15)" />}
      {/* Median */}
      {p.p50 && <path d={buildPath(p.p50)} fill="none" stroke="#6366f1" strokeWidth="2.5" />}
      {/* TP/SL lines */}
      {data.tp_price && <line x1={pad} y1={y(data.tp_price)} x2={W - pad} y2={y(data.tp_price)}
        stroke="#10b981" strokeWidth="1" strokeDasharray="6,4" />}
      {data.sl_price && <line x1={pad} y1={y(data.sl_price)} x2={W - pad} y2={y(data.sl_price)}
        stroke="#ef4444" strokeWidth="1" strokeDasharray="6,4" />}
      {/* Current price */}
      <line x1={pad} y1={y(data.current_price)} x2={W - pad} y2={y(data.current_price)}
        stroke="#6b7280" strokeWidth="1" strokeDasharray="3,3" />
      {/* Labels */}
      <text x={W - pad + 5} y={y(data.current_price) + 4} fill="#9ca3af" fontSize="9">${data.current_price}</text>
      {data.tp_price && <text x={W - pad + 5} y={y(data.tp_price) + 4} fill="#10b981" fontSize="9">TP ${data.tp_price}</text>}
      {data.sl_price && <text x={W - pad + 5} y={y(data.sl_price) + 4} fill="#ef4444" fontSize="9">SL ${data.sl_price}</text>}
      {visibleDays > 2 && p.p50 && (
        <>
          <text x={W - pad + 5} y={y(p.p95[visibleDays - 1]) + 4} fill="#22c55e" fontSize="8">P95</text>
          <text x={W - pad + 5} y={y(p.p50[visibleDays - 1]) + 4} fill="#6366f1" fontSize="8">P50</text>
          <text x={W - pad + 5} y={y(p.p5[visibleDays - 1]) + 4} fill="#ef4444" fontSize="8">P5</text>
        </>
      )}
      <text x={pad} y={H - 10} fill="#6b7280" fontSize="10">Today</text>
      <text x={W - pad - 30} y={H - 10} fill="#6b7280" fontSize="10">{data.horizon_days}d</text>
    </svg>
  );
}

// --- Scenario Presets ---
const SCENARIOS = [
  { label: '📊 Current', tp: 25, sl: 15, days: 90, desc: 'Live dashboard signals' },
  { label: '🐂 Bull', tp: 30, sl: 10, days: 60, desc: 'Aggressive targets, short horizon' },
  { label: '🐻 Bear', tp: 15, sl: 25, days: 120, desc: 'Conservative TP, wider SL' },
  { label: '💥 Black Swan', tp: 50, sl: 30, days: 30, desc: 'Extreme move, short window' },
  { label: '🐢 Patient', tp: 40, sl: 20, days: 180, desc: 'Wide targets, 6-month horizon' },
];

// --- Mini Ticker Cards ---
function MiniTickerComparison() {
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all(TICKERS.map(sym =>
      fetch(`api/monte-carlo-enhanced/${sym}?tp=25&sl=15&days=90`)
        .then(r => r.json()).catch(() => null)
    )).then(r => {
      setResults(r.filter(Boolean).sort((a, b) => b.expected_pnl_pct - a.expected_pnl_pct));
      setLoading(false);
    });
  }, []);

  if (loading) return <div className="grid grid-cols-7 gap-2">{TICKERS.map(t => <div key={t} className="h-24 bg-gray-800/30 rounded-lg animate-pulse" />)}</div>;

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-7 gap-2">
      {results.map((d, i) => (
        <div key={d.symbol} className={`rounded-lg p-3 text-center border ${i === 0 ? 'bg-emerald-900/10 border-emerald-800/30' : 'bg-gray-800/20 border-gray-800/50'}`}>
          <p className="font-mono font-bold text-sm text-white">{d.symbol}</p>
          <p className="text-xs text-gray-500">${d.current_price}</p>
          <div className="my-1">
            <div className="flex h-3 rounded overflow-hidden">
              <div className="bg-emerald-600" style={{ width: `${d.tp_probability}%` }} />
              <div className="bg-red-600" style={{ width: `${d.sl_probability}%` }} />
            </div>
          </div>
          <p className={`text-xs font-mono font-bold ${d.expected_pnl_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
            {d.expected_pnl_pct > 0 ? '+' : ''}{d.expected_pnl_pct}%
          </p>
          <p className="text-xs text-gray-600">{d.tp_probability}% TP</p>
        </div>
      ))}
    </div>
  );
}

// --- Backtest Section ---
function BacktestSection({ symbol, tp, sl }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [period, setPeriod] = useState('12mo');

  const run = () => {
    setLoading(true);
    fetch(`api/swing-backtest?symbol=${symbol}&tp_pct=${tp}&sl_pct=${sl}&period=${period}`)
      .then(r => r.json()).then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  };

  useEffect(() => { run(); }, [symbol]);

  return (
    <div className="bg-gray-900 rounded-xl p-6 border border-gray-800 mb-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-lg font-bold">📈 Historical Backtest — {symbol}</h2>
          <p className="text-xs text-gray-500">How would this strategy have performed on real data?</p>
        </div>
        <div className="flex gap-2">
          {['6mo', '12mo', '24mo'].map(p => (
            <button key={p} onClick={() => { setPeriod(p); setTimeout(run, 50); }}
              className={`text-xs px-3 py-1 rounded ${period === p ? 'bg-indigo-600 text-white' : 'bg-gray-800 text-gray-400'}`}>{p}</button>
          ))}
          <button onClick={run} disabled={loading}
            className="text-xs px-3 py-1 rounded bg-gray-800 text-gray-400 hover:bg-gray-700 disabled:opacity-50">
            {loading ? '...' : '↻'}
          </button>
        </div>
      </div>

      {data && !data.error ? (
        <>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4">
            <div className="bg-gray-800/40 rounded-lg p-3 text-center">
              <p className="text-xs text-gray-500">Swing Return</p>
              <p className={`font-mono text-xl font-bold ${(data.total_return_pct || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                {(data.total_return_pct || 0) > 0 ? '+' : ''}{(data.total_return_pct || 0).toFixed(1)}%
              </p>
            </div>
            <div className="bg-gray-800/40 rounded-lg p-3 text-center">
              <p className="text-xs text-gray-500">Buy & Hold</p>
              <p className={`font-mono text-xl font-bold ${(data.buy_hold_return_pct || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                {(data.buy_hold_return_pct || 0) > 0 ? '+' : ''}{(data.buy_hold_return_pct || 0).toFixed(1)}%
              </p>
            </div>
            <div className="bg-gray-800/40 rounded-lg p-3 text-center">
              <p className="text-xs text-gray-500">Trades</p>
              <p className="font-mono text-xl font-bold text-gray-300">{data.total_trades || 0}</p>
            </div>
            <div className="bg-gray-800/40 rounded-lg p-3 text-center">
              <p className="text-xs text-gray-500">Win Rate</p>
              <p className="font-mono text-xl font-bold text-amber-400">{(data.win_rate || 0).toFixed(0)}%</p>
            </div>
            <div className="bg-gray-800/40 rounded-lg p-3 text-center">
              <p className="text-xs text-gray-500">Max Drawdown</p>
              <p className="font-mono text-xl font-bold text-red-400">{(data.max_drawdown_pct || 0).toFixed(1)}%</p>
            </div>
          </div>

          {/* Verdict */}
          <div className={`text-center py-2 rounded-lg text-sm ${
            (data.total_return_pct || 0) > (data.buy_hold_return_pct || 0) ? 'bg-emerald-900/20 text-emerald-400' : 'bg-amber-900/20 text-amber-400'
          }`}>
            {(data.total_return_pct || 0) > (data.buy_hold_return_pct || 0)
              ? `✅ Swing outperformed B&H by ${((data.total_return_pct || 0) - (data.buy_hold_return_pct || 0)).toFixed(1)}pp`
              : `⚠️ B&H outperformed swing by ${((data.buy_hold_return_pct || 0) - (data.total_return_pct || 0)).toFixed(1)}pp — consider hybrid strategy`
            }
          </div>
        </>
      ) : data?.error ? (
        <p className="text-xs text-red-400">{data.error}</p>
      ) : null}
    </div>
  );
}

// --- Methodology ---
function Methodology() {
  const [open, setOpen] = useState(false);
  return (
    <div className="bg-gray-900 rounded-xl p-6 border border-gray-800">
      <button onClick={() => setOpen(!open)} className="flex items-center gap-2 text-gray-400 hover:text-white w-full">
        <span className="text-lg font-bold">📖 Methodology & Limitations</span>
        <span className="text-xs ml-auto">{open ? '▼' : '▶'}</span>
      </button>
      {open && (
        <div className="mt-4 text-sm text-gray-400 space-y-3">
          <div>
            <h4 className="text-white font-bold mb-1">Signal-Weighted GBM</h4>
            <p>Extends standard Geometric Brownian Motion with drift and volatility adjustments from 7 dashboard signals: score momentum, supply/demand balance, cross-asset regime, ETF flows, inventory levels, geopolitical risk, and options IV.</p>
          </div>
          <div>
            <h4 className="text-white font-bold mb-1">How Signals Modify the Model</h4>
            <p><strong>Drift adjustments</strong> shift the expected return up or down. A commodity supercycle adds +3% annualized drift (structural tailwind). Strong ETF outflows subtract -1% (short-term headwind). Score below 50 reduces drift proportionally.</p>
            <p className="mt-1"><strong>Volatility adjustments</strong> widen or narrow the distribution. Elevated geopolitical risk (+15% vol) and high options IV (+10% vol) create fatter tails — more extreme outcomes become more likely.</p>
          </div>
          <div>
            <h4 className="text-white font-bold mb-1">Limitations</h4>
            <ul className="list-disc list-inside space-y-1">
              <li>Signal weights are calibrated by domain knowledge, not backtested (yet)</li>
              <li>GBM assumes log-normal returns — real uranium has fatter tails</li>
              <li>No regime switching — a single drift/vol applies for the entire horizon</li>
              <li>Signals are point-in-time — they don't forecast their own changes</li>
              <li>Correlation between signals is not discounted (some are redundant)</li>
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}

// --- Main Page ---
export default function SimulationDashboard() {
  const [ticker, setTicker] = useState('URA');
  const [tp, setTp] = useState(25);
  const [sl, setSl] = useState(15);
  const [days, setDays] = useState(90);
  const [data, setData] = useState(null);
  const [basic, setBasic] = useState(null);
  const [loading, setLoading] = useState(false);
  const debounceRef = useRef(null);

  const runSim = useCallback(() => {
    setLoading(true);
    Promise.all([
      fetch(`api/monte-carlo-enhanced/${ticker}?tp=${tp}&sl=${sl}&days=${days}`).then(r => r.json()),
      fetch(`api/monte-carlo-tpsl/${ticker}?tp_pct=${tp}&sl_pct=${sl}&days=${days}`).then(r => r.json()),
    ]).then(([enh, bas]) => {
      setData(enh); setBasic(bas); setLoading(false);
    }).catch(() => setLoading(false));
  }, [ticker, tp, sl, days]);

  useEffect(() => { runSim(); }, [ticker]);

  const debouncedRun = () => {
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(runSim, 600);
  };

  const applyScenario = (s) => {
    setTp(s.tp); setSl(s.sl); setDays(s.days);
    setTimeout(runSim, 100);
  };

  const sigStyle = { FAVORABLE: 'bg-emerald-900/30 text-emerald-400 border-emerald-800/50', UNFAVORABLE: 'bg-red-900/30 text-red-400 border-red-800/50', NEUTRAL: 'bg-gray-800/50 text-gray-400 border-gray-700/50' };

  return (
    <div className="min-h-screen bg-black text-white">
      <div className="max-w-7xl mx-auto px-4 py-6">
        {/* Header */}
        <div className="mb-6">
          <Link to="/" className="text-xs text-indigo-400 hover:text-indigo-300 mb-2 inline-block">← Back to Dashboard</Link>
          <div className="flex items-center gap-3">
            <h1 className="text-3xl font-bold">🧠 Signal-Enhanced Monte Carlo</h1>
            {loading && <div className="w-4 h-4 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />}
          </div>
          <p className="text-gray-500 mt-1">5,000 simulations weighted by 7 dashboard signals. The Machine predicts using its own intelligence.</p>
        </div>

        {/* Ticker selector */}
        <div className="flex gap-2 mb-6 flex-wrap">
          {TICKERS.map(t => (
            <button key={t} onClick={() => setTicker(t)}
              className={`px-4 py-2 rounded-full text-sm font-mono font-bold transition-all ${
                ticker === t ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-500/20' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
              }`}>{t}</button>
          ))}
        </div>

        {/* Main content: Fan Chart + Waterfall sidebar */}
        {data && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
            {/* Fan Chart — 2/3 width */}
            <div className="lg:col-span-2 bg-gray-900 rounded-xl p-6 border border-gray-800">
              <div className="flex items-center justify-between mb-3">
                <h2 className="text-lg font-bold">{data.symbol} — Price Distribution</h2>
                <div className={`text-sm font-bold px-3 py-1 rounded-lg border ${sigStyle[data.signal] || ''}`}>
                  {data.signal === 'FAVORABLE' ? '✅' : data.signal === 'UNFAVORABLE' ? '❌' : '⚪'} {data.signal}
                </div>
              </div>
              <EnhancedFanChart data={data} />
              {/* Key stats row */}
              <div className="grid grid-cols-4 gap-3 mt-4">
                <div className="text-center bg-gray-800/40 rounded-lg p-2">
                  <p className="text-xs text-gray-500">TP Probability</p>
                  <p className="font-mono text-xl font-bold text-emerald-400">{data.tp_probability}%</p>
                </div>
                <div className="text-center bg-gray-800/40 rounded-lg p-2">
                  <p className="text-xs text-gray-500">SL Probability</p>
                  <p className="font-mono text-xl font-bold text-red-400">{data.sl_probability}%</p>
                </div>
                <div className="text-center bg-gray-800/40 rounded-lg p-2">
                  <p className="text-xs text-gray-500">Expected P&L</p>
                  <p className={`font-mono text-xl font-bold ${data.expected_pnl_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    {data.expected_pnl_pct > 0 ? '+' : ''}{data.expected_pnl_pct}%
                  </p>
                </div>
                <div className="text-center bg-gray-800/40 rounded-lg p-2">
                  <p className="text-xs text-gray-500">Median to TP</p>
                  <p className="font-mono text-xl font-bold text-gray-300">{data.median_days_to_tp ?? '—'}d</p>
                </div>
              </div>
            </div>

            {/* Waterfall + Confidence — 1/3 width */}
            <div className="space-y-4">
              <div className="bg-gray-900 rounded-xl p-5 border border-indigo-800/30">
                <WaterfallChart
                  adjustments={data.signal_adjustments}
                  baseDrift={data.base_drift_annual}
                  adjustedDrift={data.adjusted_drift_annual}
                  baseVol={data.base_vol}
                  adjustedVol={data.adjusted_vol}
                />
              </div>
              <div className="bg-gray-900 rounded-xl p-5 border border-gray-800">
                <ConfidenceMeter adjustments={data.signal_adjustments} />
              </div>
              {/* Enhanced vs Basic comparison */}
              {basic && (
                <div className="bg-gray-900 rounded-xl p-4 border border-gray-800">
                  <h4 className="text-xs font-bold text-gray-500 mb-2">vs Plain GBM</h4>
                  <div className="space-y-1 text-xs">
                    <div className="flex justify-between">
                      <span className="text-gray-500">TP prob</span>
                      <span><span className="text-indigo-400">{data.tp_probability}%</span> vs <span className="text-gray-400">{basic.tp_probability}%</span>
                        <span className={`ml-1 ${data.tp_probability > basic.tp_probability ? 'text-emerald-400' : 'text-red-400'}`}>
                          ({data.tp_probability > basic.tp_probability ? '+' : ''}{(data.tp_probability - basic.tp_probability).toFixed(1)}pp)
                        </span>
                      </span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-500">E[P&L]</span>
                      <span><span className="text-indigo-400">{data.expected_pnl_pct}%</span> vs <span className="text-gray-400">{basic.expected_pnl_pct}%</span></span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-gray-500">Drift</span>
                      <span><span className="text-indigo-400">{data.adjusted_drift_annual}%</span> vs <span className="text-gray-400">4.35%</span></span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Strategy Tester — sliders */}
        <div className="bg-gray-900 rounded-xl p-6 border border-gray-800 mb-6">
          <h2 className="text-lg font-bold mb-4">🎯 Strategy Tester</h2>

          {/* Scenario presets */}
          <div className="flex gap-2 mb-5 flex-wrap">
            {SCENARIOS.map(s => (
              <button key={s.label} onClick={() => applyScenario(s)}
                className="bg-gray-800 hover:bg-gray-700 text-xs px-3 py-1.5 rounded-lg transition-colors"
                title={s.desc}>
                {s.label}
              </button>
            ))}
          </div>

          {/* Sliders */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div>
              <div className="flex justify-between text-xs mb-1">
                <span className="text-emerald-400">Take Profit</span>
                <span className="font-mono text-white font-bold">+{tp}%</span>
              </div>
              <input type="range" min="5" max="50" value={tp}
                onChange={e => { setTp(Number(e.target.value)); debouncedRun(); }}
                className="w-full h-2 bg-gray-800 rounded-lg appearance-none cursor-pointer accent-emerald-500" />
              <div className="flex justify-between text-xs text-gray-600 mt-0.5"><span>5%</span><span>50%</span></div>
            </div>
            <div>
              <div className="flex justify-between text-xs mb-1">
                <span className="text-red-400">Stop Loss</span>
                <span className="font-mono text-white font-bold">-{sl}%</span>
              </div>
              <input type="range" min="5" max="40" value={sl}
                onChange={e => { setSl(Number(e.target.value)); debouncedRun(); }}
                className="w-full h-2 bg-gray-800 rounded-lg appearance-none cursor-pointer accent-red-500" />
              <div className="flex justify-between text-xs text-gray-600 mt-0.5"><span>5%</span><span>40%</span></div>
            </div>
            <div>
              <div className="flex justify-between text-xs mb-1">
                <span className="text-gray-400">Horizon</span>
                <span className="font-mono text-white font-bold">{days} days</span>
              </div>
              <input type="range" min="14" max="365" value={days}
                onChange={e => { setDays(Number(e.target.value)); debouncedRun(); }}
                className="w-full h-2 bg-gray-800 rounded-lg appearance-none cursor-pointer accent-indigo-500" />
              <div className="flex justify-between text-xs text-gray-600 mt-0.5"><span>14d</span><span>365d</span></div>
            </div>
          </div>
        </div>

        {/* Multi-ticker comparison */}
        <div className="bg-gray-900 rounded-xl p-6 border border-gray-800 mb-6">
          <h2 className="text-lg font-bold mb-1">📊 All Tickers — Signal-Enhanced Comparison</h2>
          <p className="text-xs text-gray-500 mb-4">+25% TP / -15% SL / 90d — ranked by expected P&L. All use live dashboard signals.</p>
          <MiniTickerComparison />
        </div>

        {/* Backtest */}
        <BacktestSection symbol={ticker} tp={tp} sl={sl} />

        {/* Methodology */}
        <Methodology />

        <div className="text-center text-xs text-gray-700 mt-8 pb-4">
          Uranium Thermometer • Signal-Enhanced Monte Carlo • Not financial advice
        </div>
      </div>
    </div>
  );
}
