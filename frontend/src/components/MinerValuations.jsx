import { useState, useEffect } from 'react';

const sigStyle = { CHEAP: 'bg-zinc-800/40 text-emerald-400/60', EXPENSIVE: 'bg-zinc-800/40 text-red-400/60', FAIR: 'bg-zinc-800 text-zinc-300' };

export default function MinerValuations() {
  const [data, setData] = useState(null);
  useEffect(() => { fetch('api/miner-valuations').then(r => r.json()).then(setData).catch(() => {}); }, []);
  if (!data?.miners?.length) return null;

  const maxEv = Math.max(...data.miners.map(m => m.ev_per_lb));

  return (
    <div className="u-card p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-zinc-200">💎 Miner Valuations (EV/lb)</h3>
        <span className="text-xs font-mono px-2 py-1 rounded bg-zinc-800 text-zinc-300">
          Avg: ${data.avg_ev_per_lb}/lb
        </span>
      </div>

      <div className="space-y-2">
        {data.miners.map(m => (
          <div key={m.symbol} className="flex items-center gap-3">
            <span className="font-mono text-sm text-zinc-200 w-12">{m.symbol}</span>
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-0.5">
                <div className="flex-1 h-4 bg-zinc-800 rounded-full overflow-hidden">
                  <div className={`h-full rounded-full ${m.signal === 'CHEAP' ? 'bg-emerald-600' : m.signal === 'EXPENSIVE' ? 'bg-red-500' : 'bg-amber-500'}`}
                    style={{ width: `${(m.ev_per_lb / maxEv) * 100}%` }} />
                </div>
                <span className="font-mono text-xs text-zinc-100 font-bold w-16 text-right">${m.ev_per_lb}</span>
                <span className={`text-xs px-1.5 py-0.5 rounded w-20 text-center ${sigStyle[m.signal]}`}>{m.signal}</span>
              </div>
              <div className="flex justify-between text-xs text-zinc-500">
                <span>{m.type} • {m.key_asset}</span>
                <span>MCap: ${m.market_cap}B • {m.resources_mlbs}M lbs</span>
              </div>
            </div>
          </div>
        ))}
      </div>

      <p className="text-xs text-zinc-500 mt-3">
        EV/lb = market cap ÷ total resources. Lower = cheaper per pound of uranium in the ground.
        Cheapest: {data.cheapest} • Most expensive: {data.most_expensive}
      </p>
    </div>
  );
}
