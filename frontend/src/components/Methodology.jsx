import { BookOpen } from 'lucide-react'

export default function Methodology({ methodology }) {
  if (!methodology) return null

  return (
    <div className="rounded-xl p-5" style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
      <div className="flex items-center gap-2 mb-4">
        <BookOpen className="w-4 h-4" style={{ color: 'var(--text-muted)' }} />
        <h2 className="text-lg font-bold tracking-wide">METHODOLOGY</h2>
      </div>
      
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Zone Classification */}
        <div className="rounded-lg p-4" style={{ background: 'var(--surface2)' }}>
          <h3 className="font-bold text-sm mb-3">Zone Classification</h3>
          <div className="space-y-2 text-xs">
            {Object.entries(methodology.zone_classification).map(([zone, desc]) => {
              const color = zone === 'GREEN' ? 'var(--green)' : zone === 'RED' ? 'var(--red)' : 'var(--yellow)'
              return (
                <div key={zone} className="flex gap-2">
                  <span className="font-mono font-bold flex-shrink-0" style={{ color, minWidth: '55px' }}>{zone}</span>
                  <span style={{ color: 'var(--text-muted)' }}>{desc}</span>
                </div>
              )
            })}
          </div>
        </div>

        {/* Signal Score */}
        <div className="rounded-lg p-4" style={{ background: 'var(--surface2)' }}>
          <h3 className="font-bold text-sm mb-3">Signal Score</h3>
          <p className="text-xs leading-relaxed" style={{ color: 'var(--text-muted)' }}>
            {methodology.signal_score}
          </p>
          <div className="mt-3 space-y-1 text-xs">
            <div className="flex justify-between"><span>70–100</span><span style={{ color: 'var(--green)' }}>Strong Buy</span></div>
            <div className="flex justify-between"><span>55–70</span><span style={{ color: 'var(--green)' }}>Buy</span></div>
            <div className="flex justify-between"><span>45–55</span><span style={{ color: 'var(--yellow)' }}>Hold</span></div>
            <div className="flex justify-between"><span>30–45</span><span style={{ color: 'var(--red)' }}>Sell</span></div>
            <div className="flex justify-between"><span>0–30</span><span style={{ color: 'var(--red)' }}>Strong Sell</span></div>
          </div>
        </div>

        {/* Technical Indicators */}
        <div className="rounded-lg p-4" style={{ background: 'var(--surface2)' }}>
          <h3 className="font-bold text-sm mb-3">Technical Indicators</h3>
          <div className="space-y-2 text-xs">
            {Object.entries(methodology.technical_indicators).map(([ind, desc]) => (
              <div key={ind}>
                <span className="font-mono font-bold" style={{ color: 'var(--yellow)' }}>{ind}</span>
                <p style={{ color: 'var(--text-muted)' }}>{desc}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
