import { useState, useEffect } from 'react'

const BOOT_LINES = [
  { text: '> URANIUM THERMOMETER v3.7', delay: 0, color: '#818cf8' },
  { text: '> Initializing anti-fragile investment protocol...', delay: 300 },
  { text: '  ├─ Connecting to market data feeds', delay: 600, check: true },
  { text: '  ├─ Loading uranium spot price (UxC)', delay: 1000, check: true },
  { text: '  ├─ Scanning 11 uranium tickers', delay: 1400, check: true },
  { text: '  ├─ Computing technical indicators (RSI, MACD, BB, SMA)', delay: 1800, check: true },
  { text: '  ├─ Analyzing macro regime (yield curve, DXY, S&P)', delay: 2200, check: true },
  { text: '  ├─ Evaluating fundamental signals (valuation, insiders)', delay: 2600, check: true },
  { text: '  ├─ Processing sentiment layer (ETF flows, options, institutions)', delay: 3000, check: true },
  { text: '  ├─ Running composite scoring engine (17 signals)', delay: 3400, check: true },
  { text: '  └─ Generating trading verdicts', delay: 3800, check: true },
  { text: '', delay: 4200 },
  { text: '> All systems operational.', delay: 4200, color: '#34d399' },
  { text: '> Loading dashboard...', delay: 4600, color: '#818cf8' },
]

function Spinner() {
  const [frame, setFrame] = useState(0)
  const chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
  useEffect(() => {
    const iv = setInterval(() => setFrame(f => (f + 1) % chars.length), 80)
    return () => clearInterval(iv)
  }, [])
  return <span style={{ color: '#818cf8' }}>{chars[frame]}</span>
}

export default function BootScreen() {
  const [visibleLines, setVisibleLines] = useState(0)
  const [completedLines, setCompletedLines] = useState(new Set())
  const [cursorVisible, setCursorVisible] = useState(true)

  useEffect(() => {
    const iv = setInterval(() => setCursorVisible(v => !v), 530)
    return () => clearInterval(iv)
  }, [])

  useEffect(() => {
    BOOT_LINES.forEach((line, i) => {
      setTimeout(() => setVisibleLines(i + 1), line.delay)
      if (line.check) {
        setTimeout(() => setCompletedLines(s => new Set([...s, i])), line.delay + 350)
      }
    })
  }, [])

  const progress = Math.min(100, (completedLines.size / BOOT_LINES.filter(l => l.check).length) * 100)
  const allDone = completedLines.size >= BOOT_LINES.filter(l => l.check).length

  return (
    <div className="min-h-screen flex items-center justify-center px-4" style={{ background: '#09090b' }}>
      <div className="w-full max-w-lg">
        {/* Header */}
        <div className="text-center mb-6">
          <div className="inline-flex items-center gap-2 mb-2">
            <div className="w-2 h-2 rounded-full animate-pulse" style={{ background: 'var(--accent)' }} />
            <span className="text-xs uppercase tracking-[0.2em] text-zinc-500 font-mono">Uranium Thermometer</span>
          </div>
        </div>

        {/* Terminal window */}
        <div className="rounded-xl border overflow-hidden" style={{
          background: 'rgba(255,255,255,0.02)',
          borderColor: 'rgba(129,140,248,0.15)',
          boxShadow: '0 0 60px rgba(129,140,248,0.05), inset 0 1px 0 rgba(255,255,255,0.02)',
        }}>
          {/* Title bar */}
          <div className="flex items-center gap-2 px-4 py-2.5 border-b" style={{ borderColor: 'rgba(255,255,255,0.04)' }}>
            <div className="flex gap-1.5">
              <div className="w-2.5 h-2.5 rounded-full" style={{ background: '#ef4444', opacity: 0.5 }} />
              <div className="w-2.5 h-2.5 rounded-full" style={{ background: '#eab308', opacity: 0.5 }} />
              <div className="w-2.5 h-2.5 rounded-full" style={{ background: '#22c55e', opacity: 0.5 }} />
            </div>
            <span className="text-[10px] font-mono text-zinc-600 ml-2">uranium-thermometer — boot</span>
          </div>

          {/* Terminal content */}
          <div className="p-4 sm:p-5 font-mono text-xs sm:text-[13px] leading-relaxed min-h-[280px]">
            {BOOT_LINES.slice(0, visibleLines).map((line, i) => {
              if (!line.text) return <div key={i} className="h-3" />
              const done = completedLines.has(i)
              const isActive = i === visibleLines - 1 && !done && line.check
              return (
                <div key={i} className="flex items-center gap-2 boot-line" style={{ animationDelay: `${i * 30}ms` }}>
                  <span className="flex-1 break-all sm:break-normal" style={{ color: line.color || (done ? '#71717a' : '#a1a1aa') }}>
                    {line.text}
                    {isActive && (
                      <span style={{ opacity: cursorVisible ? 1 : 0, color: '#818cf8', marginLeft: 2 }}>▋</span>
                    )}
                  </span>
                  {line.check && (
                    <span className="w-5 text-right flex-shrink-0">
                      {done ? <span className="text-emerald-400/80 check-pop">✓</span> : isActive ? <Spinner /> : null}
                    </span>
                  )}
                </div>
              )
            })}
          </div>

          {/* Progress bar */}
          <div className="px-4 sm:px-5 pb-4">
            <div className="h-[2px] rounded-full overflow-hidden" style={{ background: 'rgba(255,255,255,0.04)' }}>
              <div className="h-full rounded-full transition-all duration-500 ease-out"
                style={{
                  width: `${progress}%`,
                  background: allDone ? 'linear-gradient(90deg, #34d399, #10b981)' : 'linear-gradient(90deg, #818cf8, #6366f1)',
                  boxShadow: allDone ? '0 0 8px rgba(52,211,153,0.4)' : '0 0 8px rgba(129,140,248,0.4)',
                }} />
            </div>
            <div className="flex justify-between mt-2 text-[10px] font-mono text-zinc-600">
              <span>{Math.round(progress)}%</span>
              <span>{allDone ? 'READY' : 'INITIALIZING...'}</span>
            </div>
          </div>
        </div>

        <p className="text-center text-[10px] text-zinc-600 mt-4 font-mono">
          ANTI-FRAGILE INVESTMENT PROTOCOL
        </p>
      </div>

      <style>{`
        .boot-line { animation: lineIn 0.25s ease-out both; }
        @keyframes lineIn { from { opacity: 0; transform: translateX(-8px); } to { opacity: 1; transform: translateX(0); } }
        .check-pop { animation: pop 0.3s cubic-bezier(0.34, 1.56, 0.64, 1) both; }
        @keyframes pop { from { transform: scale(0); opacity: 0; } to { transform: scale(1); opacity: 1; } }
      `}</style>
    </div>
  )
}
