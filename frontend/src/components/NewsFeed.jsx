import { useState } from 'react'
import { Newspaper, ExternalLink } from 'lucide-react'

const CATEGORIES = ['all', 'nuclear approvals', 'AI energy demand', 'US/EU policy', 'utility contracts', 'supply/mining', 'general']

export default function NewsFeed({ news }) {
  const [filter, setFilter] = useState('all')

  if (!news || news.length === 0) return null

  const filtered = filter === 'all' ? news : news.filter(n => n.category === filter)

  return (
    <div className="rounded-xl p-5" style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
      <div className="flex items-center gap-2 mb-4">
        <Newspaper className="w-4 h-4" style={{ color: 'var(--yellow)' }} />
        <h2 className="text-lg font-bold tracking-wide">MACRO NEWS</h2>
      </div>

      {/* Category filters */}
      <div className="flex flex-wrap gap-2 mb-4">
        {CATEGORIES.map(cat => (
          <button
            key={cat}
            onClick={() => setFilter(cat)}
            className="text-xs px-3 py-1 rounded-full transition-all"
            style={{
              background: filter === cat ? 'var(--yellow)' + '33' : 'var(--surface2)',
              color: filter === cat ? 'var(--yellow)' : 'var(--text-muted)',
              border: `1px solid ${filter === cat ? 'var(--yellow)' + '55' : 'var(--border)'}`,
            }}
          >
            {cat}
          </button>
        ))}
      </div>

      {/* News list */}
      <div className="space-y-3 max-h-96 overflow-y-auto pr-2">
        {filtered.slice(0, 30).map((article, i) => {
          const sentColor = article.sentiment === 'bullish' ? 'var(--green)' : article.sentiment === 'bearish' ? 'var(--red)' : 'var(--text-muted)'
          return (
            <a
              key={i}
              href={article.url}
              target="_blank"
              rel="noopener noreferrer"
              className="block p-3 rounded-lg hover:opacity-80 transition-all"
              style={{ background: 'var(--surface2)' }}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1">
                  <p className="text-sm font-medium leading-snug">{article.title}</p>
                  {article.summary && (
                    <p className="text-xs mt-1 line-clamp-2" style={{ color: 'var(--text-muted)' }}>{article.summary}</p>
                  )}
                  <div className="flex items-center gap-2 mt-2">
                    <span className="text-[10px] px-2 py-0.5 rounded-full font-bold" style={{ background: sentColor + '22', color: sentColor }}>
                      {article.sentiment?.toUpperCase()}
                    </span>
                    <span className="text-[10px] px-2 py-0.5 rounded-full" style={{ background: 'var(--border)', color: 'var(--text-muted)' }}>
                      {article.category}
                    </span>
                    <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
                      {article.source}
                    </span>
                  </div>
                </div>
                <ExternalLink className="w-3 h-3 flex-shrink-0 mt-1" style={{ color: 'var(--text-muted)' }} />
              </div>
            </a>
          )
        })}
      </div>
    </div>
  )
}
