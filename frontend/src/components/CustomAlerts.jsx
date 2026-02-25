import { useState, useEffect } from 'react';

const TICKERS = ['URA', 'CCJ', 'UEC', 'UUUU', 'DNN', 'NXE', 'OKLO', 'LEU', 'KAP.IL', 'PDN.AX', 'U-UN.TO'];
const TYPES = ['price', 'score', 'daily_change', 'volume'];
const OPERATORS = ['above', 'below'];

export default function CustomAlerts() {
  const [alerts, setAlerts] = useState([]);
  const [form, setForm] = useState({ type: 'price', symbol: 'URA', operator: 'above', value: '', channel: 'both' });
  const [adding, setAdding] = useState(false);

  const load = () => fetch('api/alerts/custom').then(r => r.json()).then(d => setAlerts(d.alerts || [])).catch(() => {});
  useEffect(() => { load(); }, []);

  const add = async () => {
    if (!form.value) return;
    setAdding(true);
    await fetch('api/alerts/custom', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...form, value: parseFloat(form.value) }),
    });
    setForm(f => ({ ...f, value: '' }));
    setAdding(false);
    load();
  };

  const remove = async (id) => {
    await fetch(`api/alerts/custom/${id}`, { method: 'DELETE' });
    load();
  };

  const toggle = async (id, enabled) => {
    await fetch(`api/alerts/custom/${id}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: !enabled }),
    });
    load();
  };

  const typeLabel = { price: '$', score: 'pts', daily_change: '%', volume: '× avg' };

  return (
    <div className="u-card p-6">
      <h3 className="text-sm font-semibold text-zinc-200 mb-4">⚙️ Custom Alerts</h3>

      {/* Add form */}
      <div className="flex flex-wrap gap-2 mb-4">
        <select value={form.symbol} onChange={e => setForm(f => ({ ...f, symbol: e.target.value }))}
          className="bg-zinc-800 text-zinc-200 text-xs rounded px-2 py-1.5">
          {TICKERS.map(t => <option key={t} value={t}>{t}</option>)}
        </select>
        <select value={form.type} onChange={e => setForm(f => ({ ...f, type: e.target.value }))}
          className="bg-zinc-800 text-zinc-200 text-xs rounded px-2 py-1.5">
          {TYPES.map(t => <option key={t} value={t}>{t}</option>)}
        </select>
        <select value={form.operator} onChange={e => setForm(f => ({ ...f, operator: e.target.value }))}
          className="bg-zinc-800 text-zinc-200 text-xs rounded px-2 py-1.5">
          {OPERATORS.map(o => <option key={o} value={o}>{o}</option>)}
        </select>
        <input type="number" placeholder="Value" value={form.value}
          onChange={e => setForm(f => ({ ...f, value: e.target.value }))}
          className="bg-zinc-800 text-zinc-200 text-xs rounded px-2 py-1.5 w-20" />
        <select value={form.channel} onChange={e => setForm(f => ({ ...f, channel: e.target.value }))}
          className="bg-zinc-800 text-zinc-200 text-xs rounded px-2 py-1.5">
          <option value="both">Both</option>
          <option value="discord">Discord</option>
          <option value="telegram">Telegram</option>
        </select>
        <button onClick={add} disabled={adding || !form.value}
          className="bg-emerald-600 text-zinc-100 text-xs px-3 py-1.5 rounded hover:bg-emerald-700 disabled:opacity-50">
          + Add
        </button>
      </div>

      {/* Active alerts */}
      {alerts.length > 0 ? (
        <div className="space-y-1">
          {alerts.map(a => (
            <div key={a.id} className={`flex items-center justify-between p-2 rounded-lg ${a.enabled ? 'bg-zinc-800/30' : 'bg-zinc-800/20 opacity-50'}`}>
              <div className="flex items-center gap-2 text-xs">
                <span className="font-mono text-zinc-200">{a.symbol}</span>
                <span className="text-zinc-400">{a.type}</span>
                <span className={`px-1.5 py-0.5 rounded ${a.operator === 'above' ? 'bg-zinc-800/40 text-emerald-400/60' : 'bg-zinc-800/40 text-red-400/60'}`}>
                  {a.operator === 'above' ? '≥' : '≤'} {a.value}{typeLabel[a.type] || ''}
                </span>
                <span className="text-zinc-500">→ {a.channel}</span>
              </div>
              <div className="flex gap-1">
                <button onClick={() => toggle(a.id, a.enabled)}
                  className={`text-xs px-2 py-0.5 rounded ${a.enabled ? 'bg-zinc-800/40 text-emerald-400/60' : 'bg-gray-700 text-zinc-400'}`}>
                  {a.enabled ? 'ON' : 'OFF'}
                </button>
                <button onClick={() => remove(a.id)}
                  className="text-xs px-2 py-0.5 rounded bg-zinc-800/40 text-red-400 hover:bg-zinc-800/40">✕</button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-xs text-zinc-500">No custom alerts. Add one above — checks every 15 min during market hours.</p>
      )}
    </div>
  );
}
