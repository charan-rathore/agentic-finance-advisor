import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Globe, TrendingUp, TrendingDown, Minus, RefreshCw, ExternalLink,
  Newspaper, MessageCircle, Clock, BarChart3
} from 'lucide-react'
import { api, type StockPrice, type NewsArticle } from '../lib/api'
import { cn } from '../lib/utils'

export default function GlobalMarkets() {
  const navigate = useNavigate()
  const [prices, setPrices] = useState<StockPrice[]>([])
  const [news, setNews] = useState<NewsArticle[]>([])
  const [headlines, setHeadlines] = useState<Array<Record<string, string>>>([])
  const [insights, setInsights] = useState<Array<Record<string, unknown>>>([])
  const [loading, setLoading] = useState(true)
  const [newsLoading, setNewsLoading] = useState(false)
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)
  const [autoRefresh, setAutoRefresh] = useState(true)

  const loadData = useCallback(async (showNewsSpinner = false) => {
    if (showNewsSpinner) setNewsLoading(true)
    try {
      const [priceRes, newsRes, headlineRes, insightRes] = await Promise.all([
        api.getGlobalPrices(),
        api.getGlobalNews(),
        api.getGlobalHeadlines(),
        api.getGlobalInsights(),
      ])
      setPrices(priceRes.prices || [])
      setNews(newsRes.articles || [])
      setHeadlines(headlineRes.headlines || [])
      setInsights(insightRes.insights || [])
      setLastRefresh(new Date())
    } catch (err) {
      console.error('Global markets load error:', err)
    } finally {
      setLoading(false)
      setNewsLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  useEffect(() => {
    if (!autoRefresh) return
    const interval = setInterval(() => loadData(), 120_000)
    return () => clearInterval(interval)
  }, [autoRefresh, loadData])

  const avgChange = prices.length > 0
    ? prices.reduce((sum, p) => sum + (p.change_pct ?? 0), 0) / prices.filter(p => p.change_pct != null).length
    : 0

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-gray-900 flex items-center gap-2">
            <Globe className="w-5 h-5 text-brand-600" />
            Global Markets
          </h2>
          <p className="text-sm text-gray-500 mt-0.5">
            Live US stock prices, news from multiple sources, and AI-generated insights
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-2 text-xs text-gray-500">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="rounded border-gray-300"
            />
            Auto-refresh
          </label>
          <button
            onClick={() => loadData(true)}
            disabled={newsLoading}
            className="btn-secondary text-xs flex items-center gap-1.5 py-2"
          >
            <RefreshCw className={cn('w-3.5 h-3.5', newsLoading && 'animate-spin')} />
            Refresh
          </button>
          {lastRefresh && (
            <span className="text-[10px] text-gray-400 flex items-center gap-1">
              <Clock className="w-3 h-3" />
              {lastRefresh.toLocaleTimeString()}
            </span>
          )}
        </div>
      </div>

      {/* US Stock Prices */}
      <section>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-base font-bold text-gray-900">US Equities</h3>
          <span className={cn(
            'inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold',
            avgChange > 0.1 ? 'bg-emerald-50 text-emerald-700' :
            avgChange < -0.1 ? 'bg-red-50 text-red-700' : 'bg-gray-100 text-gray-600'
          )}>
            {avgChange > 0.1 ? <TrendingUp className="w-3 h-3" /> :
             avgChange < -0.1 ? <TrendingDown className="w-3 h-3" /> :
             <Minus className="w-3 h-3" />}
            Avg {avgChange >= 0 ? '+' : ''}{avgChange.toFixed(2)}%
          </span>
        </div>

        {loading ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="card p-4 animate-pulse">
                <div className="h-3 bg-surface-200 rounded w-16 mb-2" />
                <div className="h-5 bg-surface-200 rounded w-20" />
              </div>
            ))}
          </div>
        ) : prices.length > 0 ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
            {prices.map((stock) => (
              <div key={stock.symbol} className="card p-3.5 hover:shadow-md transition-shadow">
                <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide">{stock.symbol}</p>
                <p className="text-base font-bold text-gray-900 mt-1">${(stock.price ?? 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}</p>
                {stock.change_pct != null && (
                  <div className={cn(
                    'flex items-center gap-1 mt-1 text-xs font-semibold',
                    stock.change_pct > 0 ? 'text-emerald-600' : stock.change_pct < 0 ? 'text-red-600' : 'text-gray-500'
                  )}>
                    {stock.change_pct > 0 ? <TrendingUp className="w-3 h-3" /> : stock.change_pct < 0 ? <TrendingDown className="w-3 h-3" /> : <Minus className="w-3 h-3" />}
                    {stock.change_pct >= 0 ? '+' : ''}{stock.change_pct.toFixed(2)}%
                  </div>
                )}
                {stock.data_label && (
                  <span className={cn(
                    'inline-block mt-1.5 text-[10px] font-medium px-1.5 py-0.5 rounded',
                    stock.data_label === 'Live' ? 'bg-emerald-50 text-emerald-600' :
                    stock.data_label === 'Delayed' ? 'bg-amber-50 text-amber-600' : 'bg-gray-50 text-gray-500'
                  )}>
                    {stock.data_label}
                  </span>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="card p-6 text-center text-sm text-gray-500">
            No US price data yet. Start the ingest agent with <code className="bg-surface-100 px-1.5 py-0.5 rounded text-xs">python main.py</code>
          </div>
        )}
      </section>

      {/* News Section - Two column layout */}
      <div className="grid lg:grid-cols-5 gap-6">
        {/* Live News Feed - Takes 3 columns */}
        <section className="lg:col-span-3">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-base font-bold text-gray-900 flex items-center gap-2">
              <Newspaper className="w-4 h-4 text-brand-600" />
              Live Market News
            </h3>
            {newsLoading && <RefreshCw className="w-3.5 h-3.5 text-brand-500 animate-spin" />}
          </div>

          <div className="card divide-y divide-surface-200 max-h-[600px] overflow-y-auto scrollbar-thin">
            {news.length > 0 ? news.map((article, i) => (
              <a
                key={i}
                href={article.link}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-start gap-3 p-4 hover:bg-surface-50 transition-colors group"
              >
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-gray-900 group-hover:text-brand-700 transition-colors leading-snug">
                    {article.title}
                  </p>
                  <div className="flex items-center gap-2 mt-1.5">
                    <span className="text-[11px] font-semibold text-brand-600 bg-brand-50 px-2 py-0.5 rounded-full">
                      {article.source}
                    </span>
                    {article.published && (
                      <span className="text-[11px] text-gray-400">
                        {formatRelativeTime(article.published)}
                      </span>
                    )}
                  </div>
                </div>
                <ExternalLink className="w-4 h-4 text-gray-300 group-hover:text-brand-500 flex-shrink-0 mt-1 transition-colors" />
              </a>
            )) : (
              <div className="p-8 text-center text-sm text-gray-400">
                {loading ? 'Loading news...' : 'No news articles available. Check your network connection.'}
              </div>
            )}
          </div>
        </section>

        {/* Sidebar - Ingested Headlines + Insights */}
        <section className="lg:col-span-2 space-y-6">
          {/* Ingested DB Headlines */}
          {headlines.length > 0 && (
            <div>
              <h3 className="text-base font-bold text-gray-900 mb-3 flex items-center gap-2">
                <BarChart3 className="w-4 h-4 text-emerald-600" />
                Ingested Headlines
              </h3>
              <div className="card divide-y divide-surface-200 max-h-[280px] overflow-y-auto scrollbar-thin">
                {headlines.slice(0, 10).map((h, i) => (
                  <div key={i} className="p-3">
                    {h.url ? (
                      <a href={h.url} target="_blank" rel="noopener noreferrer" className="text-sm text-gray-800 hover:text-brand-700 transition-colors leading-snug block">
                        {h.headline}
                      </a>
                    ) : (
                      <p className="text-sm text-gray-800 leading-snug">{h.headline}</p>
                    )}
                    <span className="text-[10px] text-gray-400 mt-1 inline-block">{h.source}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* AI Insights */}
          {insights.length > 0 && (
            <div>
              <h3 className="text-base font-bold text-gray-900 mb-3">AI Insights</h3>
              <div className="space-y-3">
                {insights.slice(0, 3).map((insight, i) => (
                  <div key={i} className="card p-4">
                    <p className="text-xs text-gray-400 mb-1.5">
                      {(insight.generated_at as string)?.slice(0, 16)} · {insight.sentiment_summary as string}
                    </p>
                    <p className="text-sm text-gray-700 leading-relaxed line-clamp-4">
                      {insight.insight_text as string}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Ask global advisor CTA */}
          <button
            onClick={() => navigate('/chat', { state: { market: 'global' } })}
            className="card p-4 w-full text-left hover:border-brand-300 hover:shadow-md transition-all group"
          >
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-brand-50 text-brand-600 flex items-center justify-center group-hover:bg-brand-100 transition-colors">
                <MessageCircle className="w-5 h-5" />
              </div>
              <div>
                <p className="font-semibold text-gray-900 text-sm">Ask the global advisor</p>
                <p className="text-xs text-gray-500">ETFs, S&P 500, 401k, market analysis</p>
              </div>
            </div>
          </button>
        </section>
      </div>
    </div>
  )
}

function formatRelativeTime(dateStr: string): string {
  try {
    const date = new Date(dateStr)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffMins = Math.floor(diffMs / 60000)
    if (diffMins < 1) return 'Just now'
    if (diffMins < 60) return `${diffMins}m ago`
    const diffHours = Math.floor(diffMins / 60)
    if (diffHours < 24) return `${diffHours}h ago`
    const diffDays = Math.floor(diffHours / 24)
    return `${diffDays}d ago`
  } catch {
    return dateStr
  }
}
