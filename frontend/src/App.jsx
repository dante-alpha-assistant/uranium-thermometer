import { useState, useEffect } from 'react'
import Thermometer from './components/Thermometer'
import TickerGrid from './components/TickerGrid'
import SignalPanel from './components/SignalPanel'
import NewsFeed from './components/NewsFeed'
import TickerDetail from './components/TickerDetail'
import Methodology from './components/Methodology'
import ScoreHistory from './components/ScoreHistory'
import Verdict from './components/Verdict'
import MacroRegime from './components/MacroRegime'
import { Activity, RefreshCw, Atom } from 'lucide-react'

function App() {
  const [data, setData] = useState(null)
  const [signals, setSignals] = useState(null)
  const [news, setNews] = useState(null)
  const [selectedTicker, setSelectedTicker] = useState(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)

  const fetchData = async () => {
    try {
      const [therm, sig, n] = await Promise.all([
        fetch('api/thermometer').then(r => r.json()),
        fetch('api/signals').then(r => r.json()),
        fetch('api/news').then(r => r.json()),
      ])
      setData(therm)
      setSignals(sig)
      setNews(n)
    } catch (e) {
      console.error('Fetch error:', e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchData() }, [])

  // Auto-refresh every 5 min
  useEffect(() => {
    const iv = setInterval(fetchData, 300000)
    return () => clearInterval(iv)
  }, [])

  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      await fetch('api/refresh')
      await fetchData()
    } finally {
      setRefreshing(false)
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--bg)' }}>
        <div className="text-center">
          <Atom className="w-16 h-16 mx-auto mb-4 pulse-glow" style={{ color: 'var(--green)' }} />
          <p className="text-xl" style={{ color: 'var(--text-muted)' }}>Loading Uranium Thermometer...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen" style={{ background: 'var(--bg)' }}>
      {/* Header */}
      <header className="border-b px-6 py-4 flex items-center justify-between" style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}>
        <div className="flex items-center gap-3">
          <Atom className="w-8 h-8" style={{ color: 'var(--green)' }} />
          <div>
            <h1 className="text-xl font-bold tracking-tight">URANIUM THERMOMETER</h1>
            <p className="text-xs" style={{ color: 'var(--text-muted)' }}>Investment Dashboard • Real-Time Analysis</p>
          </div>
        </div>
        <div className="flex items-center gap-4">
          {data?.spot_uranium && (
            <div className="text-right hidden sm:block">
              <p className="text-xs" style={{ color: 'var(--text-muted)' }}>Spot U₃O₈</p>
              <p className="font-mono font-bold" style={{ color: 'var(--yellow)' }}>${data.spot_uranium.price}</p>
            </div>
          )}
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="p-2 rounded-lg hover:opacity-80 transition-opacity"
            style={{ background: 'var(--surface2)' }}
          >
            <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} style={{ color: 'var(--text-muted)' }} />
          </button>
          <div className="flex items-center gap-1">
            <Activity className="w-3 h-3" style={{ color: 'var(--green)' }} />
            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>LIVE</span>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-6 space-y-6">
        {/* Ticker Detail Modal */}
        {selectedTicker && (
          <TickerDetail symbol={selectedTicker} onClose={() => setSelectedTicker(null)} />
        )}

        {/* Verdict */}
        <Verdict verdict={data?.verdict} />

        {/* Hero: Thermometer + Macro + Signal Panel */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-6">
            <Thermometer ura={data?.ura} />
            <MacroRegime />
          </div>
          <div>
            <SignalPanel signals={signals?.signals} />
          </div>
        </div>

        {/* Ticker Grid */}
        <TickerGrid tickers={data?.tickers} onSelect={setSelectedTicker} />

        {/* Score History */}
        <ScoreHistory symbol="URA" />

        {/* News Feed */}
        <NewsFeed news={news?.articles} />

        {/* Methodology */}
        <Methodology methodology={data?.methodology} />
      </main>

      <footer className="text-center py-4 text-xs" style={{ color: 'var(--text-muted)' }}>
        Uranium Thermometer v1.0 • Data via Yahoo Finance • Not financial advice • Updated {data?.last_updated ? new Date(data.last_updated).toLocaleString() : 'N/A'}
      </footer>
    </div>
  )
}

export default App
