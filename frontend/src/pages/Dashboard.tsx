import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  TrendingUp, TrendingDown, RefreshCw, MessageCircle,
  Calculator, Target, Shield, Wallet, Zap,
} from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, ReferenceLine,
} from 'recharts'
import { api, type StockPrice, type Nudge } from '../lib/api'
import { cn, classifyDNA } from '../lib/utils'
import type { Profile } from '../lib/api'

interface Props {
  profile: Profile
}

function getGreeting(): string {
  const h = new Date().getHours()
  if (h < 12) return 'Good morning'
  if (h < 17) return 'Good afternoon'
  return 'Good evening'
}

function SnapshotStat({
  icon: Icon,
  label,
  value,
  sub,
  color = 'brand',
}: {
  icon: React.ElementType
  label: string
  value: string
  sub?: string
  color?: 'brand' | 'emerald' | 'violet' | 'amber'
}) {
  const colors = {
    brand: 'bg-brand-50 dark:bg-brand-900/20 text-brand-600 dark:text-brand-400',
    emerald: 'bg-emerald-50 dark:bg-emerald-900/20 text-emerald-600 dark:text-emerald-400',
    violet: 'bg-violet-50 dark:bg-violet-900/20 text-violet-600 dark:text-violet-400',
    amber: 'bg-amber-50 dark:bg-amber-900/20 text-amber-600 dark:text-amber-400',
  }
  return (
    <div className="flex items-start gap-3">
      <div className={cn('p-2 rounded-lg flex-shrink-0', colors[color])}>
        <Icon size={16} />
      </div>
      <div className="min-w-0">
        <div className="text-xs text-gray-500 dark:text-gray-400 font-medium">{label}</div>
        <div className="text-sm font-semibold text-gray-900 dark:text-white truncate">{value}</div>
        {sub && <div className="text-xs text-gray-400 dark:text-gray-500 truncate">{sub}</div>}
      </div>
    </div>
  )
}

export default function Dashboard({ profile }: Props) {
  const navigate = useNavigate()
  const [prices, setPrices] = useState<StockPrice[]>([])
  const [rbi, setRbi] = useState<Record<string, unknown> | null>(null)
  const [nudges, setNudges] = useState<Nudge[]>([])
  const [loading, setLoading] = useState(true)
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null)

  const loadData = useCallback(async () => {
    try {
      const [priceRes, rbiRes, nudgeRes] = await Promise.all([
        api.getIndiaPrices(),
        api.getIndiaRBI(),
        api.getNudges([], undefined),
      ])
      setPrices(priceRes.prices || [])
      setRbi(rbiRes.rates || null)
      setNudges(nudgeRes.nudges || [])
      setLastRefresh(new Date())
    } catch (err) {
      console.error('Dashboard load error:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadData() }, [loadData])

  const dna = classifyDNA(profile)
  const chartData = [...prices]
    .filter((p) => p.change_pct != null)
    .sort((a, b) => (b.change_pct ?? 0) - (a.change_pct ?? 0))
    .slice(0, 8)
    .map((p) => ({
      name: p.symbol.replace('.NS', ''),
      change: Number((p.change_pct ?? 0).toFixed(2)),
    }))

  return (
    <div className="p-4 lg:p-6 space-y-5 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-gray-900 dark:text-white">
            {getGreeting()}, {profile.name.split(' ')[0]} 👋
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
            Here's your financial snapshot for today
          </p>
        </div>
        <button
          onClick={loadData}
          className="p-2 rounded-lg border border-surface-200 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-500 hover:bg-surface-50 dark:hover:bg-gray-700 transition-colors"
          title="Refresh"
        >
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
        </button>
      </div>

      {/* Profile snapshot */}
      <div className="card p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold text-gray-900 dark:text-white text-sm">Your Financial Profile</h2>
          <span className="badge bg-brand-50 dark:bg-brand-900/30 text-brand-700 dark:text-brand-400 border border-brand-200 dark:border-brand-800">
            {dna}
          </span>
        </div>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <SnapshotStat
            icon={Wallet}
            label="Monthly Income"
            value={profile.monthly_income}
            color="brand"
          />
          <SnapshotStat
            icon={Target}
            label="SIP Budget"
            value={profile.monthly_sip_budget}
            color="emerald"
          />
          <SnapshotStat
            icon={Zap}
            label="Primary Goal"
            value={profile.primary_goal}
            sub={profile.horizon_pref + ' horizon'}
            color="violet"
          />
          <SnapshotStat
            icon={Shield}
            label="Risk Tolerance"
            value={profile.risk_tolerance.charAt(0).toUpperCase() + profile.risk_tolerance.slice(1)}
            sub={`Tax bracket: ${profile.tax_bracket_pct}%`}
            color="amber"
          />
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Market bar chart */}
        <div className="lg:col-span-2 card p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-gray-900 dark:text-white text-sm">India Market Performance</h2>
            {lastRefresh && (
              <span className="text-xs text-gray-400">
                {lastRefresh.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}
              </span>
            )}
          </div>
          {loading ? (
            <div className="h-44 flex items-center justify-center">
              <div className="w-6 h-6 border-2 border-brand-500 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : chartData.length > 0 ? (
            <ResponsiveContainer width="100%" height={176}>
              <BarChart data={chartData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
                <XAxis dataKey="name" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={(v) => `${v}%`} />
                <Tooltip
                  formatter={(v: unknown) => [`${Number(v ?? 0).toFixed(2)}%`, 'Change']}
                  contentStyle={{
                    background: 'var(--tooltip-bg, #fff)',
                    border: '1px solid #e2e8f0',
                    borderRadius: '8px',
                    fontSize: '12px',
                  }}
                />
                <ReferenceLine y={0} stroke="#94a3b8" strokeDasharray="3 3" />
                <Bar dataKey="change" radius={[4, 4, 0, 0]}>
                  {chartData.map((d, i) => (
                    <Cell key={i} fill={d.change >= 0 ? '#10b981' : '#ef4444'} fillOpacity={0.85} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-44 flex items-center justify-center text-sm text-gray-400">
              No price data yet — agents are fetching...
            </div>
          )}
        </div>

        {/* RBI Rates */}
        <div className="card p-5">
          <h2 className="font-semibold text-gray-900 dark:text-white text-sm mb-4">RBI Policy Rates</h2>
          {rbi ? (
            <div className="space-y-3">
              {[
                { label: 'Repo Rate', key: 'repo_rate_pct' },
                { label: 'Reverse Repo', key: 'reverse_repo_rate_pct' },
                { label: 'CRR', key: 'crr_pct' },
                { label: 'SLR', key: 'slr_pct' },
              ].map(({ label, key }) => (
                <div key={key} className="flex items-center justify-between">
                  <span className="text-xs text-gray-500 dark:text-gray-400">{label}</span>
                  <span className="text-sm font-semibold text-gray-900 dark:text-white">
                    {rbi[key] != null ? `${rbi[key]}%` : '—'}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-xs text-gray-400 text-center py-8">
              Loading rates...
            </div>
          )}
        </div>
      </div>

      {/* India stock grid */}
      {prices.length > 0 && (
        <div className="card p-5">
          <h2 className="font-semibold text-gray-900 dark:text-white text-sm mb-4">Live Prices</h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
            {prices.map((p) => (
              <div
                key={p.symbol}
                className="rounded-lg border border-surface-200 dark:border-gray-700 p-3 bg-surface-50 dark:bg-gray-800/50"
              >
                <div className="flex items-start justify-between gap-1 mb-1">
                  <span className="text-xs font-semibold text-gray-800 dark:text-gray-200 truncate">
                    {p.symbol.replace('.NS', '')}
                  </span>
                  {p.change_pct != null && (
                    <div className={cn(
                      'flex-shrink-0 text-xs font-medium flex items-center gap-0.5',
                      p.change_pct >= 0 ? 'text-emerald-600' : 'text-red-500'
                    )}>
                      {p.change_pct >= 0 ? <TrendingUp size={10} /> : <TrendingDown size={10} />}
                      {Math.abs(p.change_pct).toFixed(1)}%
                    </div>
                  )}
                </div>
                <div className="text-sm font-bold text-gray-900 dark:text-white">
                  {p.price_inr != null ? `₹${p.price_inr.toLocaleString('en-IN', { maximumFractionDigits: 1 })}` : '—'}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Nudges */}
      {nudges.length > 0 && (
        <div className="card p-5">
          <h2 className="font-semibold text-gray-900 dark:text-white text-sm mb-3">Smart Insights</h2>
          <div className="space-y-2">
            {nudges.slice(0, 3).map((n, i) => (
              <div
                key={i}
                className="flex items-start gap-3 p-3 rounded-lg bg-surface-50 dark:bg-gray-800/50 border border-surface-200 dark:border-gray-700"
              >
                <span className="text-lg flex-shrink-0">{n.icon}</span>
                <div>
                  <div className="text-sm font-medium text-gray-800 dark:text-gray-200">{n.title}</div>
                  <div className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{n.body}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Quick actions */}
      <div className="grid grid-cols-2 gap-3">
        <button
          onClick={() => navigate('/chat')}
          className="btn-primary flex items-center justify-center gap-2 py-3"
        >
          <MessageCircle size={16} />
          Ask AI Advisor
        </button>
        <button
          onClick={() => navigate('/calculators')}
          className="btn-secondary flex items-center justify-center gap-2 py-3"
        >
          <Calculator size={16} />
          Calculators
        </button>
      </div>
    </div>
  )
}
