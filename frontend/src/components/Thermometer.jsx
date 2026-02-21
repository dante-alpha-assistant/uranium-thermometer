import { TrendingUp, TrendingDown, Minus } from 'lucide-react'

export default function Thermometer({ ura }) {
  if (!ura) return null

  const pct = ura.zone_pct || 50
  const zone = ura.zone || 'YELLOW'
  const zoneColor = zone === 'GREEN' ? 'var(--green)' : zone === 'RED' ? 'var(--red)' : 'var(--yellow)'

  // SVG thermometer gauge
  const gaugeWidth = 600
  const gaugeHeight = 40
  const fillWidth = (pct / 100) * gaugeWidth

  return (
    <div className="rounded-xl p-6" style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-lg font-bold tracking-wide">URA ETF THERMOMETER</h2>
          <p className="text-sm" style={{ color: 'var(--text-muted)' }}>{ura.name}</p>
        </div>
        <div className="text-right">
          <p className="text-3xl font-mono font-bold" style={{ color: zoneColor }}>
            ${ura.current_price}
          </p>
          <p className={`text-sm font-mono flex items-center justify-end gap-1`} style={{ color: ura.change_pct >= 0 ? 'var(--green)' : 'var(--red)' }}>
            {ura.change_pct >= 0 ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
            {ura.change_pct >= 0 ? '+' : ''}{ura.change_pct}%
          </p>
        </div>
      </div>

      {/* Thermometer Gauge */}
      <div className="my-6">
        <svg viewBox={`0 0 ${gaugeWidth} ${gaugeHeight + 40}`} className="w-full" style={{ maxHeight: '80px' }}>
          {/* Background segments */}
          <defs>
            <linearGradient id="gaugeGrad" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="var(--green)" />
              <stop offset="20%" stopColor="var(--green)" />
              <stop offset="25%" stopColor="var(--yellow)" />
              <stop offset="75%" stopColor="var(--yellow)" />
              <stop offset="80%" stopColor="var(--red)" />
              <stop offset="100%" stopColor="var(--red)" />
            </linearGradient>
            <filter id="glow">
              <feGaussianBlur stdDeviation="3" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
          </defs>
          
          {/* Track */}
          <rect x="0" y="10" width={gaugeWidth} height={gaugeHeight} rx="6" fill="var(--surface2)" />
          
          {/* Gradient fill */}
          <rect x="0" y="10" width={gaugeWidth} height={gaugeHeight} rx="6" fill="url(#gaugeGrad)" opacity="0.2" />
          
          {/* Active fill */}
          <rect x="0" y="10" width={fillWidth} height={gaugeHeight} rx="6" fill={zoneColor} opacity="0.6" />
          
          {/* Zone markers */}
          <line x1={gaugeWidth * 0.2} y1="8" x2={gaugeWidth * 0.2} y2={gaugeHeight + 12} stroke="var(--text-muted)" strokeWidth="1" strokeDasharray="3,3" />
          <line x1={gaugeWidth * 0.8} y1="8" x2={gaugeWidth * 0.8} y2={gaugeHeight + 12} stroke="var(--text-muted)" strokeWidth="1" strokeDasharray="3,3" />
          
          {/* Current position indicator */}
          <circle cx={fillWidth} cy={10 + gaugeHeight / 2} r="10" fill={zoneColor} filter="url(#glow)" />
          <circle cx={fillWidth} cy={10 + gaugeHeight / 2} r="5" fill="white" />
          
          {/* Labels */}
          <text x={gaugeWidth * 0.1} y={gaugeHeight + 30} textAnchor="middle" fill="var(--green)" fontSize="11" fontWeight="bold">BUY</text>
          <text x={gaugeWidth * 0.5} y={gaugeHeight + 30} textAnchor="middle" fill="var(--yellow)" fontSize="11" fontWeight="bold">HOLD</text>
          <text x={gaugeWidth * 0.9} y={gaugeHeight + 30} textAnchor="middle" fill="var(--red)" fontSize="11" fontWeight="bold">SELL</text>
          
          {/* Price labels */}
          <text x="0" y="7" fill="var(--text-muted)" fontSize="9">${ura.range_low}</text>
          <text x={gaugeWidth} y="7" textAnchor="end" fill="var(--text-muted)" fontSize="9">${ura.range_high}</text>
        </svg>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-center">
        <Stat label="Zone" value={zone} color={zoneColor} />
        <Stat label="Signal" value={`${ura.signal_score}/100`} sublabel={ura.signal_label} color={ura.signal_score >= 55 ? 'var(--green)' : ura.signal_score <= 45 ? 'var(--red)' : 'var(--yellow)'} />
        <Stat label="RSI (14)" value={ura.rsi || '—'} color={ura.rsi < 30 ? 'var(--green)' : ura.rsi > 70 ? 'var(--red)' : 'var(--text)'} />
        <Stat label="6M Range" value={`$${ura.range_low} – $${ura.range_high}`} />
      </div>
    </div>
  )
}

function Stat({ label, value, sublabel, color }) {
  return (
    <div className="rounded-lg p-3" style={{ background: 'var(--surface2)' }}>
      <p className="text-xs mb-1" style={{ color: 'var(--text-muted)' }}>{label}</p>
      <p className="font-mono font-bold text-sm" style={{ color: color || 'var(--text)' }}>{value}</p>
      {sublabel && <p className="text-xs mt-0.5" style={{ color: 'var(--text-muted)' }}>{sublabel}</p>}
    </div>
  )
}
