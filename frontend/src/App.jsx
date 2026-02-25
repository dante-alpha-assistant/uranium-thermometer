import { useState, useEffect } from 'react'
import BootScreen from './components/BootScreen'
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
import FundFlows from './components/FundFlows'
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
import ScoreDecomposition from './components/ScoreDecomposition'
import SignalHistory from './components/SignalHistory'
import Backtester from './components/Backtester'
import DailyDigest from './components/DailyDigest'
import TradeTickets from './components/TradeTickets'
import PortfolioPerformance from './components/PortfolioPerformance'
import MacroDashboard from './components/MacroDashboard'
import { Activity, RefreshCw, Download, ChevronDown, ChevronRight, BarChart3, Brain, TrendingUp, Globe, MessageCircle, Briefcase, Zap, Menu, X } from 'lucide-react'
import { SkeletonCard, SkeletonGrid } from './components/Skeleton'

// Decision funnel: big picture → analysis → context → positions → action
const NAV_ITEMS = [
  { id: 'overview',   label: 'Overview',   icon: BarChart3,     desc: 'Should I care?' },
  { id: 'analysis',   label: 'AI Analysis', icon: Brain,        desc: 'What does AI think?' },
  { id: 'technicals', label: 'Technicals',  icon: TrendingUp,   desc: 'What\'s price doing?' },
  { id: 'macro',      label: 'Macro',       icon: Globe,        desc: 'What\'s the world doing?' },
  { id: 'sentiment',  label: 'Sentiment',   icon: MessageCircle, desc: 'What are others doing?' },
  { id: 'portfolio',  label: 'Portfolio',   icon: Briefcase,    desc: 'What am I holding?' },
  { id: 'execute',    label: 'Execute',     icon: Zap,          desc: 'What should I do?' },
]

function Section({ id, title, subtitle, icon: Icon, defaultOpen = true, children }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <section id={id} className="animate-fade-in scroll-mt-8">
      <button onClick={() => setOpen(!open)}
        className="flex items-center gap-3.5 w-full text-left group mb-8">
        <div className="flex items-center justify-center w-9 h-9 rounded-xl" style={{ background: 'var(--accent-dim)' }}>
          {Icon && <Icon className="w-[18px] h-[18px]" style={{ color: 'var(--accent)' }} />}
        </div>
        <div className="flex-1 min-w-0">
          <h2 className="text-lg font-bold text-zinc-100 group-hover:text-white transition-colors tracking-tight">
            {title}
          </h2>
          {subtitle && <p className="text-xs text-zinc-400 mt-0.5">{subtitle}</p>}
        </div>
        {open ? <ChevronDown className="w-4 h-4 text-zinc-700" /> : <ChevronRight className="w-4 h-4 text-zinc-700" />}
      </button>
      {open && <div className="space-y-8">{children}</div>}
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
  const [spotPrice, setSpotPrice] = useState(null)
  const [activeNav, setActiveNav] = useState('overview')
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

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
    fetch('api/spot-price').then(r => r.json()).then(setSpotPrice).catch(() => {})
  }, [])

  useEffect(() => {
    const iv = setInterval(fetchData, 300000)
    return () => clearInterval(iv)
  }, [])

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) setActiveNav(entry.target.id)
        })
      },
      { rootMargin: '-20% 0px -70% 0px' }
    )
    NAV_ITEMS.forEach(item => {
      const el = document.getElementById(item.id)
      if (el) observer.observe(el)
    })
    return () => observer.disconnect()
  }, [loading])

  const handleRefresh = async () => {
    setRefreshing(true)
    try {
      await fetch('api/refresh')
      await fetchData()
    } finally {
      setRefreshing(false)
    }
  }

  const scrollTo = (id) => {
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' })
    setMobileMenuOpen(false)
  }

  if (loading) {
    return <BootScreen />
  }

  return (
    <div className="min-h-screen flex" style={{ background: 'var(--bg)' }}>
      {/* ═══ Sidebar — desktop ═══ */}
      <aside className="hidden lg:flex flex-col w-56 fixed inset-y-0 left-0 z-30 border-r" style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}>
        {/* Spot price — hero, starts the sidebar */}
        {spotPrice?.price && (
          <div className="px-5 pt-5 pb-4 border-b" style={{ borderColor: 'var(--border)' }}>
            <p className="text-[10px] font-medium text-zinc-500 tracking-wider uppercase mb-3">Uranium Thermometer</p>
            <p className="text-[10px] uppercase tracking-widest text-zinc-400 mb-2">Spot U₃O₈ (Commodity)</p>
            <p className="text-2xl font-bold font-mono text-white">${spotPrice.price}<span className="text-xs text-zinc-600 font-normal ml-1">/lb</span></p>
            <div className="flex items-center gap-2 mt-1">
              {spotPrice.monthly_change_pct != null && (
                <span className={`text-xs font-mono ${spotPrice.monthly_change_pct >= 0 ? 'text-emerald-400/70' : 'text-red-400/70'}`}>
                  {spotPrice.monthly_change_pct >= 0 ? '+' : ''}{spotPrice.monthly_change_pct}% /mo
                </span>
              )}
            </div>
            <p className="text-[10px] text-zinc-500 mt-1">{spotPrice.source || 'UxC/Cameco'}</p>
            {data?.ura?.current_price && (
              <div className="mt-3 pt-3 border-t" style={{ borderColor: 'var(--border)' }}>
                <p className="text-xs uppercase tracking-wider text-zinc-400 mb-1">URA ETF</p>
                <p className="text-lg font-bold font-mono text-white">${data.ura.current_price}</p>
              </div>
            )}
          </div>
        )}

        {/* Nav — decision funnel */}
        <nav className="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto">
          <p className="text-[9px] uppercase tracking-[0.15em] text-zinc-500 px-3 mb-2">Decision Flow</p>
          {NAV_ITEMS.map((item, i) => {
            const Icon = item.icon
            const active = activeNav === item.id
            return (
              <button key={item.id} onClick={() => scrollTo(item.id)}
                className={`w-full flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-sm transition-all ${
                  active ? 'text-white font-medium' : 'text-zinc-500 hover:text-zinc-300 hover:bg-white/[0.03]'
                }`}
                style={active ? { background: 'var(--accent-dim)', color: 'var(--accent)' } : {}}
              >
                <span className="text-[10px] font-mono text-zinc-700 w-3">{i + 1}</span>
                <Icon className="w-4 h-4" />
                <span>{item.label}</span>
              </button>
            )
          })}
        </nav>

        {/* Actions */}
        <div className="px-3 py-3 border-t flex items-center gap-2" style={{ borderColor: 'var(--border)' }}>
          <a href="api/export/csv" download
            className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
            style={{ background: 'var(--surface2)' }}>
            <Download className="w-3.5 h-3.5" /> CSV
          </a>
          <button onClick={handleRefresh} disabled={refreshing}
            className="flex-1 flex items-center justify-center gap-1.5 py-1.5 rounded-lg text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
            style={{ background: 'var(--surface2)' }}>
            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} /> Refresh
          </button>
        </div>

        <div className="px-5 py-3 border-t flex items-center gap-1.5" style={{ borderColor: 'var(--border)' }}>
          <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
          <span className="text-[10px] text-zinc-600">Live · v2.2</span>
        </div>
      </aside>

      {/* ═══ Mobile header ═══ */}
      <header className="lg:hidden fixed top-0 left-0 right-0 z-40 border-b px-4 py-3 flex items-center justify-between"
        style={{ background: 'var(--surface)', borderColor: 'var(--border)', backdropFilter: 'blur(12px)' }}>
        <div className="flex items-center gap-2">
          <span className="text-lg">☢️</span>
          <span className="text-sm font-semibold text-white">Uranium Thermometer</span>
        </div>
        <button onClick={() => setMobileMenuOpen(!mobileMenuOpen)} className="p-1.5 rounded-lg" style={{ background: 'var(--surface2)' }}>
          {mobileMenuOpen ? <X className="w-4 h-4 text-zinc-400" /> : <Menu className="w-4 h-4 text-zinc-400" />}
        </button>
      </header>

      {mobileMenuOpen && (
        <div className="lg:hidden fixed inset-0 z-30 bg-black/60" onClick={() => setMobileMenuOpen(false)}>
          <div className="absolute top-14 left-0 right-0 border-b py-2 px-3 space-y-0.5"
            style={{ background: 'var(--surface)', borderColor: 'var(--border)' }}
            onClick={e => e.stopPropagation()}>
            {NAV_ITEMS.map((item, i) => {
              const Icon = item.icon
              return (
                <button key={item.id} onClick={() => scrollTo(item.id)}
                  className="w-full flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-sm text-zinc-400 hover:text-white hover:bg-white/[0.03] transition-colors">
                  <span className="text-[10px] font-mono text-zinc-700 w-3">{i + 1}</span>
                  <Icon className="w-4 h-4" />
                  <span>{item.label}</span>
                </button>
              )
            })}
          </div>
        </div>
      )}

      {/* ═══ Main content ═══ */}
      <main className="flex-1 lg:ml-56 pt-16 lg:pt-0">
        <div className="max-w-6xl mx-auto px-3 sm:px-5 lg:px-10 py-6 sm:py-8 lg:py-12 space-y-10 sm:space-y-16">
          {/* ─── 1. OVERVIEW: "Should I care right now?" ─── */}
          <Section id="overview" title="Overview" subtitle="Should I care right now?" icon={BarChart3} defaultOpen={true}>
            <DailyDigest />
            <Verdict verdict={data?.verdict} />
            <Thermometer ura={data?.ura} />
            <ScoreDecomposition symbol="URA" />
            <SignalHistory />
            <AntifragilePanel />
          </Section>

          {/* ─── 2. AI ANALYSIS: "What does the AI think?" ─── */}
          <Section id="analysis" title="AI Analysis" subtitle="What does the AI think?" icon={Brain} defaultOpen={true}>
            <AIAnalysis />
          </Section>

          {/* ─── 3. TECHNICALS: "What's the price doing?" ─── */}
          <Section id="technicals" title="Technicals" subtitle="What's the price doing?" icon={TrendingUp} defaultOpen={true}>
            <TickerGrid tickers={data?.tickers} onSelect={setSelectedTicker} />
            <ScoreHistory symbol="URA" />
            <Divergences />
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
            <VolumeAnomalies />
            <Backtester />
          </Section>

          {/* ─── 4. MACRO: "What's the world doing?" ─── */}
          <Section id="macro" title="Macro" subtitle="What's the world doing?" icon={Globe} defaultOpen={true}>
            <MacroDashboard />
            <MacroRegime />
            <CrossAssetRegime />
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
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <ReactorPipeline />
              <PolicyTracker />
            </div>
            <MinePipeline />
            <EtfHoldings />
          </Section>

          {/* ─── 5. SENTIMENT: "What are others doing?" ─── */}
          <Section id="sentiment" title="Sentiment" subtitle="What are others doing?" icon={MessageCircle} defaultOpen={true}>
            <SignalPanel signals={signals?.signals} />
            <NewsFeed news={news?.articles} />
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <AnalystRatings />
              <InsiderTrades />
            </div>
            <FundFlows />
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
          </Section>

          {/* ─── 6. PORTFOLIO: "What am I holding?" ─── */}
          <Section id="portfolio" title="Portfolio" subtitle="What am I holding?" icon={Briefcase} defaultOpen={true}>
            <PortfolioPerformance />
            <Portfolio />
          </Section>

          {/* ─── 7. EXECUTE: "What should I do next?" ─── */}
          <Section id="execute" title="Execute" subtitle="What should I do next?" icon={Zap} defaultOpen={true}>
            <TradeTickets />
            <SwingRules />
            <CustomAlerts />
            <Methodology methodology={data?.methodology} />
          </Section>
        </div>

        <footer className="text-center py-8 text-[11px] text-zinc-700">
          Uranium Thermometer v2.2 · Anti-Fragile Investment Protocol · Not financial advice
        </footer>
      </main>

      {selectedTicker && <TickerDetail symbol={selectedTicker} onClose={() => setSelectedTicker(null)} />}
    </div>
  )
}

export default App
