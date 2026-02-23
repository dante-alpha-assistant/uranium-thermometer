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
import VolumeAnomalies from './components/VolumeAnomalies'
import RelativeStrength from './components/RelativeStrength'
import CorrelationHeatmap from './components/CorrelationHeatmap'
import ShortInterest from './components/ShortInterest'
import Seasonality from './components/Seasonality'
import EarningsCalendar from './components/EarningsCalendar'
import MonteCarlo from './components/MonteCarlo'
import AnalystRatings from './components/AnalystRatings'
import InsiderTrades from './components/InsiderTrades'
import CrossAssetRegime from './components/CrossAssetRegime'
import InstitutionalOwnership from './components/InstitutionalOwnership'
import SupplyDemand from './components/SupplyDemand'
import PolicyTracker from './components/PolicyTracker'
import MinePipeline from './components/MinePipeline'
import EnrichmentCapacity from './components/EnrichmentCapacity'
import InventoryLevels from './components/InventoryLevels'
import ContractCoverage from './components/ContractCoverage'
import OptionsIV from './components/OptionsIV'
import SwingRules from './components/SwingRules'
import Portfolio from './components/Portfolio'
import CustomAlerts from './components/CustomAlerts'
import EtfFlows from './components/EtfFlows'
import MinerValuations from './components/MinerValuations'
import GeopoliticalRisk from './components/GeopoliticalRisk'
import CorrelationRegime from './components/CorrelationRegime'
import TermSpread from './components/TermSpread'
import Divergences from './components/Divergences'
import MonteCarloTPSL from './components/MonteCarloTPSL'
import ReactorPipeline from './components/ReactorPipeline'
import AIAnalysis from './components/AIAnalysis'
import AntifragilePanel from './components/AntifragilePanel'
import EtfHoldings from './components/EtfHoldings'
import { Activity, RefreshCw, Atom, Download, ChevronDown, ChevronRight } from 'lucide-react'
import { SkeletonCard, SkeletonGrid } from './components/Skeleton'

function Section({ title, icon, defaultOpen = true, children, badge }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <section className="space-y-4">
      <button onClick={() => setOpen(!open)}
        className="flex items-center gap-2 w-full text-left group">
        {open ? <ChevronDown className="w-4 h-4 text-gray-500" /> : <ChevronRight className="w-4 h-4 text-gray-500" />}
        <span className="text-sm font-semibold uppercase tracking-wider text-gray-400 group-hover:text-gray-200 transition-colors">
          {icon} {title}
        </span>
        {badge && <span className="text-xs px-2 py-0.5 rounded-full bg-gray-800 text-gray-500 font-mono">{badge}</span>}
      </button>
      {open && <div className="space-y-6">{children}</div>}
    </section>
  )
}

function App() {
  const [data, setData] = useState(null)
  const [signals, setSignals] = useState(null)
  const [news, setNews] = useState(null)
  const [selectedTicker, setSelectedTicker] = useState(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [sparkline, setSparkline] = useState([])
  const [spotPrice, setSpotPrice] = useState(null)

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

  useEffect(() => {
    fetchData()
    fetch('api/spot-history?days=30').then(r=>r.json()).then(d=>setSparkline(d.history||[])).catch(()=>{})
    fetch('api/spot-price').then(r=>r.json()).then(setSpotPrice).catch(()=>{})
  }, [])

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
      <div className="min-h-screen p-6" style={{ background: 'var(--bg)' }}>
        <div className="max-w-7xl mx-auto space-y-6">
          <div className="flex items-center gap-3 mb-6">
            <Atom className="w-8 h-8 animate-pulse" style={{ color: 'var(--green)' }} />
            <div className="h-6 bg-gray-800 rounded w-48 animate-pulse"></div>
          </div>
          <SkeletonCard height="h-48" />
          <SkeletonGrid count={7} />
          <SkeletonCard height="h-64" />
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
            <p className="text-xs" style={{ color: 'var(--text-muted)' }}>Anti-Fragile Investment Protocol</p>
          </div>
        </div>
        <div className="flex items-center gap-4">
          {(spotPrice?.price || data?.spot_uranium) && (
            <div className="text-right hidden sm:block">
              <p className="text-xs" style={{ color: 'var(--text-muted)' }}>Spot U₃O₈</p>
              <div className="flex items-center gap-2 justify-end">
                <p className="font-mono font-bold" style={{ color: 'var(--yellow)' }}>${spotPrice?.price || data?.spot_uranium?.price}</p>
                {spotPrice?.weekly_change_pct != null && (
                  <span className={`text-xs font-mono px-1.5 py-0.5 rounded ${spotPrice.weekly_change_pct >= 0 ? 'bg-emerald-900/50 text-emerald-400' : 'bg-red-900/50 text-red-400'}`}>
                    {spotPrice.weekly_change_pct >= 0 ? '▲' : '▼'} {Math.abs(spotPrice.weekly_change_pct)}%
                  </span>
                )}
              </div>
              {spotPrice?.sparkline_30d?.length > 5 && (() => {
                const prices = spotPrice.sparkline_30d;
                const min = Math.min(...prices), max = Math.max(...prices);
                const range = max - min || 1;
                const w = 60, h = 20;
                const pts = prices.map((p, i) => `${(i / (prices.length - 1)) * w},${h - ((p - min) / range) * h}`).join(' ');
                const color = prices[prices.length - 1] >= prices[0] ? '#10b981' : '#ef4444';
                return <svg width={w} height={h} className="ml-1"><polyline points={pts} fill="none" stroke={color} strokeWidth="1.5" /></svg>;
              })()}
            </div>
          )}
          <a href="api/export/csv" download className="p-2 rounded-lg hover:opacity-80" style={{ background: 'var(--surface2)' }} title="Export CSV">
            <Download className="w-4 h-4" style={{ color: 'var(--text-muted)' }} />
          </a>
          <button onClick={handleRefresh} disabled={refreshing} className="p-2 rounded-lg hover:opacity-80" style={{ background: 'var(--surface2)' }}>
            <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} style={{ color: 'var(--text-muted)' }} />
          </button>
          <div className="flex items-center gap-1">
            <Activity className="w-3 h-3" style={{ color: 'var(--green)' }} />
            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>LIVE</span>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 py-6 space-y-8">
        {selectedTicker && <TickerDetail symbol={selectedTicker} onClose={() => setSelectedTicker(null)} />}

        {/* ═══════ SECTION 1: THE VERDICT — "Should I trade?" ═══════ */}
        <Section title="The Verdict" icon="⚡" defaultOpen={true} badge="Decision">
          <Verdict verdict={data?.verdict} />
          <AIAnalysis />
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2">
              <Thermometer ura={data?.ura} />
            </div>
            <div>
              <MacroRegime />
            </div>
          </div>
          <CrossAssetRegime />
          <Divergences />
        </Section>

        {/* ═══════ SECTION 1.5: ANTI-FRAGILE THESIS — "Why uranium?" ═══════ */}
        <Section title="Anti-Fragile Thesis" icon="🛡️" defaultOpen={true} badge="All-Weather">
          <AntifragilePanel />
        </Section>

        {/* ═══════ SECTION 2: THE PORTFOLIO — "What and when?" ═══════ */}
        <Section title="Portfolio & Execution" icon="💼" defaultOpen={true} badge="Action">
          <Portfolio />
          <TickerGrid tickers={data?.tickers} onSelect={setSelectedTicker} />
          <ScoreHistory symbol="URA" />
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <SwingRules />
            <CustomAlerts />
          </div>
        </Section>

        {/* ═══════ SECTION 3: THESIS VALIDATION — "Why?" ═══════ */}
        <Section title="Thesis Validation" icon="🔬" defaultOpen={true} badge="Fundamentals">
          <EtfHoldings />
          {/* Supply-side */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <SupplyDemand />
            <TermSpread />
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <InventoryLevels />
            <ContractCoverage />
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <EnrichmentCapacity />
            <GeopoliticalRisk />
          </div>
          {/* Demand-side */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <ReactorPipeline />
            <PolicyTracker />
          </div>
          <MinePipeline />
        </Section>

        {/* ═══════ SECTION 4: MARKET SIGNALS — "What's the market saying?" ═══════ */}
        <Section title="Market Signals" icon="📡" defaultOpen={false} badge="Sentiment">
          <SignalPanel signals={signals?.signals} />
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <AnalystRatings />
            <InsiderTrades />
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <EtfFlows />
            <OptionsIV />
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <ShortInterest />
            <InstitutionalOwnership symbol="URA" />
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Seasonality symbol="URA" />
            <EarningsCalendar />
          </div>
          <VolumeAnomalies />
        </Section>

        {/* ═══════ SECTION 5: SIMULATION — "What could happen?" ═══════ */}
        <Section title="Simulation & Risk" icon="🎲" defaultOpen={false} badge="Models">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <MonteCarlo symbol="URA" />
            <MonteCarloTPSL />
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <MinerValuations />
            <RelativeStrength />
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <CorrelationHeatmap />
            <CorrelationRegime />
          </div>
          <div className="bg-gray-900/50 rounded-xl p-4 border border-gray-800 text-center">
            <a href="#/simulation/dashboard" className="text-indigo-400 hover:text-indigo-300 font-semibold">
              🎯 Full Simulation Dashboard → Signal-Enhanced Monte Carlo, Backtest, Optimizer
            </a>
          </div>
        </Section>

        {/* ═══════ SECTION 6: CONTEXT — News + Methodology ═══════ */}
        <Section title="News & Context" icon="📰" defaultOpen={false} badge="Reference">
          <NewsFeed news={news?.articles} />
          <Methodology methodology={data?.methodology} />
        </Section>
      </main>

      <footer className="text-center py-4 text-xs" style={{ color: 'var(--text-muted)' }}>
        Uranium Thermometer v2.1 • Anti-Fragile Investment Protocol • Not financial advice
      </footer>
    </div>
  )
}

export default App
