import { useState, useEffect } from 'react'
import { Activity, Database, FileText, AlertTriangle, CheckCircle, RefreshCw } from 'lucide-react'
import { api, type SystemHealth as HealthData } from '../lib/api'
import { cn } from '../lib/utils'

export default function SystemHealth() {
  const [health, setHealth] = useState<HealthData | null>(null)
  const [sources, setSources] = useState<Array<Record<string, unknown>>>([])
  const [loading, setLoading] = useState(true)
  const [linting, setLinting] = useState(false)

  useEffect(() => {
    async function load() {
      try {
        const [h, s] = await Promise.all([
          api.getSystemHealth(),
          api.getSources(),
        ])
        setHealth(h)
        setSources(s.sources || [])
      } catch (err) {
        console.error('Health load error:', err)
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  const runLint = async () => {
    setLinting(true)
    try {
      await api.getSystemHealth() // re-fetch after lint in real impl
    } catch (err) {
      console.error(err)
    } finally {
      setLinting(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <RefreshCw className="w-6 h-6 text-brand-600 animate-spin" />
      </div>
    )
  }

  const wiki = health?.wiki

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold text-gray-900">System Health</h2>
          <p className="text-sm text-gray-500">Wiki freshness, data sources, and audit trail</p>
        </div>
        <button
          onClick={runLint}
          disabled={linting}
          className="btn-secondary text-sm flex items-center gap-2"
        >
          <RefreshCw className={cn('w-4 h-4', linting && 'animate-spin')} />
          Run lint
        </button>
      </div>

      {/* Stats */}
      {wiki && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <StatCard icon={FileText} label="Wiki Pages" value={wiki.total_pages} color="brand" />
          <StatCard icon={CheckCircle} label="Fresh" value={wiki.fresh_count} color="emerald" />
          <StatCard icon={AlertTriangle} label="Stale" value={wiki.stale_count} color="amber" />
          <StatCard icon={Database} label="Missing Meta" value={wiki.missing_frontmatter} color="red" />
        </div>
      )}

      {/* By type */}
      {wiki?.by_type && Object.keys(wiki.by_type).length > 0 && (
        <div className="card p-4">
          <h3 className="text-sm font-semibold text-gray-900 mb-3">Pages by Type</h3>
          <div className="flex flex-wrap gap-2">
            {Object.entries(wiki.by_type).map(([type, count]) => (
              <span key={type} className="px-2.5 py-1 rounded-full bg-surface-100 text-xs font-medium text-gray-600">
                {type}: {count}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Stale pages */}
      {wiki?.stale && wiki.stale.length > 0 && (
        <div className="card overflow-hidden">
          <div className="px-4 py-3 border-b border-surface-200 bg-amber-50">
            <h3 className="text-sm font-semibold text-amber-800 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4" />
              Stale Pages ({wiki.stale.length})
            </h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-surface-50 text-left">
                <tr>
                  <th className="px-4 py-2 font-medium text-gray-500">Path</th>
                  <th className="px-4 py-2 font-medium text-gray-500">Type</th>
                  <th className="px-4 py-2 font-medium text-gray-500">Age (h)</th>
                  <th className="px-4 py-2 font-medium text-gray-500">TTL (h)</th>
                  <th className="px-4 py-2 font-medium text-gray-500">Overdue (h)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-200">
                {wiki.stale.slice(0, 10).map((page, i) => (
                  <tr key={i} className="hover:bg-surface-50">
                    <td className="px-4 py-2 font-mono text-xs text-gray-700">{page.path as string}</td>
                    <td className="px-4 py-2 text-gray-600">{page.page_type as string}</td>
                    <td className="px-4 py-2 text-gray-600">{(page.age_hours as number)?.toFixed(1)}</td>
                    <td className="px-4 py-2 text-gray-600">{page.ttl_hours as number}</td>
                    <td className="px-4 py-2 text-amber-600 font-medium">{(page.overdue_hours as number)?.toFixed(1)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Sources */}
      {sources.length > 0 && (
        <div className="card overflow-hidden">
          <div className="px-4 py-3 border-b border-surface-200">
            <h3 className="text-sm font-semibold text-gray-900 flex items-center gap-2">
              <Database className="w-4 h-4 text-brand-600" />
              Data Sources ({sources.length})
            </h3>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-surface-50 text-left">
                <tr>
                  <th className="px-4 py-2 font-medium text-gray-500">Name</th>
                  <th className="px-4 py-2 font-medium text-gray-500">Domain</th>
                  <th className="px-4 py-2 font-medium text-gray-500">Trusted</th>
                  <th className="px-4 py-2 font-medium text-gray-500">Reachable</th>
                  <th className="px-4 py-2 font-medium text-gray-500">Fetches</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-200">
                {sources.slice(0, 20).map((s, i) => (
                  <tr key={i} className="hover:bg-surface-50">
                    <td className="px-4 py-2 text-gray-700 font-medium">{s.source_name as string}</td>
                    <td className="px-4 py-2 text-gray-500 font-mono text-xs">{s.domain as string}</td>
                    <td className="px-4 py-2">
                      <StatusBadge ok={s.is_trusted as boolean} />
                    </td>
                    <td className="px-4 py-2">
                      <StatusBadge ok={s.is_reachable as boolean} />
                    </td>
                    <td className="px-4 py-2 text-gray-600">{s.fetch_count as number}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Raw data */}
      {health?.raw_data && (
        <div className="card p-4">
          <h3 className="text-sm font-semibold text-gray-900 mb-3 flex items-center gap-2">
            <Activity className="w-4 h-4 text-brand-600" />
            Raw Data Freshness
          </h3>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {Object.entries(((health.raw_data as Record<string, unknown>).sources ?? {}) as Record<string, Record<string, unknown>>).map(([name, info]) => (
              <div key={name} className="bg-surface-50 rounded-lg p-3 border border-surface-200">
                <p className="text-sm font-semibold text-gray-900">{name}</p>
                <p className="text-xs text-gray-500 mt-1">
                  {String(info.file_count ?? 0)} files · {Number(info.total_mb ?? 0).toFixed(2)} MB
                </p>
                {info.latest_iso ? (
                  <p className="text-[11px] text-gray-400 mt-0.5">
                    Latest: {String(info.latest_iso).slice(0, 16)}
                  </p>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function StatCard({ icon: Icon, label, value, color }: {
  icon: typeof Activity
  label: string
  value: number
  color: string
}) {
  const colorMap: Record<string, string> = {
    brand: 'bg-brand-50 text-brand-600',
    emerald: 'bg-emerald-50 text-emerald-600',
    amber: 'bg-amber-50 text-amber-600',
    red: 'bg-red-50 text-red-600',
  }
  return (
    <div className="card p-4">
      <div className={cn('w-9 h-9 rounded-lg flex items-center justify-center mb-2', colorMap[color])}>
        <Icon className="w-4.5 h-4.5" />
      </div>
      <p className="text-2xl font-bold text-gray-900">{value}</p>
      <p className="text-xs text-gray-500">{label}</p>
    </div>
  )
}

function StatusBadge({ ok }: { ok: boolean }) {
  return (
    <span className={cn(
      'inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium',
      ok ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-700'
    )}>
      {ok ? 'Yes' : 'No'}
    </span>
  )
}
