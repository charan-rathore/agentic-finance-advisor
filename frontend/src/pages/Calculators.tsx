import { useState } from 'react'
import {
  TrendingUp, Target, Leaf, Shield, ChevronDown, ChevronUp,
} from 'lucide-react'
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, Legend,
} from 'recharts'
import { api } from '../lib/api'
import { formatINR } from '../lib/utils'
import type { Profile } from '../lib/api'

interface Props {
  profile: Profile
}

function buildSIPChartData(monthly: number, returnPct: number, years: number) {
  const data: Array<{ year: string; invested: number; value: number }> = []
  const r = returnPct / 100 / 12
  for (let y = 1; y <= years; y++) {
    const n = y * 12
    const invested = monthly * n
    const value = r > 0 ? monthly * ((Math.pow(1 + r, n) - 1) / r) * (1 + r) : invested
    data.push({ year: `Y${y}`, invested: Math.round(invested), value: Math.round(value) })
  }
  return data
}

function buildGoalChartData(target: number, returnPct: number, years: number) {
  const r = returnPct / 100 / 12
  const n = years * 12
  const monthly = r > 0 ? target / (((Math.pow(1 + r, n) - 1) / r) * (1 + r)) : target / n
  return buildSIPChartData(Math.round(monthly), returnPct, years)
}

type CalcKey = 'sip' | 'goal' | 'elss' | 'emergency'

interface SectionProps {
  id: CalcKey
  active: CalcKey
  setActive: (k: CalcKey) => void
  icon: React.ElementType
  title: string
  subtitle: string
  children: React.ReactNode
}

function Section({ id, active, setActive, icon: Icon, title, subtitle, children }: SectionProps) {
  const isOpen = active === id
  return (
    <div className="card overflow-hidden">
      <button
        className="w-full flex items-center gap-3 p-5 text-left hover:bg-surface-50 dark:hover:bg-gray-700/30 transition-colors"
        onClick={() => setActive(isOpen ? ('' as CalcKey) : id)}
      >
        <div className="p-2 bg-brand-50 dark:bg-brand-900/20 rounded-lg flex-shrink-0">
          <Icon size={16} className="text-brand-600 dark:text-brand-400" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="font-semibold text-sm text-gray-900 dark:text-white">{title}</div>
          <div className="text-xs text-gray-500 dark:text-gray-400">{subtitle}</div>
        </div>
        {isOpen ? <ChevronUp size={16} className="text-gray-400" /> : <ChevronDown size={16} className="text-gray-400" />}
      </button>
      {isOpen && <div className="border-t border-surface-200 dark:border-gray-700 p-5">{children}</div>}
    </div>
  )
}

function SIPCalculator({ profile }: { profile: Profile }) {
  const [monthly, setMonthly] = useState(5000)
  const [returnPct, setReturnPct] = useState(12)
  const [years, setYears] = useState(10)
  const [result, setResult] = useState<Record<string, unknown> | null>(null)
  const [loading, setLoading] = useState(false)

  const calculate = async () => {
    setLoading(true)
    try {
      const res = await api.calcSIP(monthly, returnPct, years)
      setResult(res)
    } finally {
      setLoading(false)
    }
  }

  const chartData = result ? buildSIPChartData(monthly, returnPct, years) : []

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div>
          <label className="text-xs font-medium text-gray-600 dark:text-gray-400 block mb-1">Monthly SIP (₹)</label>
          <input
            type="number"
            className="input-field"
            value={monthly}
            onChange={(e) => setMonthly(Number(e.target.value))}
            min={500}
          />
        </div>
        <div>
          <label className="text-xs font-medium text-gray-600 dark:text-gray-400 block mb-1">Expected Return (%)</label>
          <input
            type="number"
            className="input-field"
            value={returnPct}
            onChange={(e) => setReturnPct(Number(e.target.value))}
            min={1}
            max={30}
          />
        </div>
        <div>
          <label className="text-xs font-medium text-gray-600 dark:text-gray-400 block mb-1">Duration (years)</label>
          <input
            type="number"
            className="input-field"
            value={years}
            onChange={(e) => setYears(Number(e.target.value))}
            min={1}
            max={40}
          />
        </div>
      </div>
      <button onClick={calculate} disabled={loading} className="btn-primary w-full">
        {loading ? 'Calculating...' : 'Calculate SIP Returns'}
      </button>
      {result && (
        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-3">
            {[
              { label: 'Total Invested', key: 'total_invested' },
              { label: 'Estimated Value', key: 'future_value' },
              { label: 'Wealth Gained', key: 'wealth_gain' },
            ].map(({ label, key }) => (
              <div key={key} className="rounded-lg bg-surface-50 dark:bg-gray-800/50 border border-surface-200 dark:border-gray-700 p-3 text-center">
                <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">{label}</div>
                <div className="text-sm font-bold text-gray-900 dark:text-white">
                  {formatINR(Number(result[key] ?? 0))}
                </div>
              </div>
            ))}
          </div>
          {chartData.length > 0 && (
            <ResponsiveContainer width="100%" height={200}>
              <AreaChart data={chartData} margin={{ top: 4, right: 4, left: -10, bottom: 0 }}>
                <defs>
                  <linearGradient id="gradInvested" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#94a3b8" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#94a3b8" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="gradValue" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#0284c7" stopOpacity={0.5} />
                    <stop offset="95%" stopColor="#0284c7" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="year" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={(v) => formatINR(v)} />
                <Tooltip
                  formatter={(v: unknown, name: unknown) => [formatINR(Number(v ?? 0)), String(name)]}
                  contentStyle={{ borderRadius: '8px', fontSize: '12px', border: '1px solid #e2e8f0' }}
                />
                <Legend iconType="circle" wrapperStyle={{ fontSize: '11px' }} />
                <Area type="monotone" dataKey="invested" name="Invested" stroke="#94a3b8" fill="url(#gradInvested)" strokeWidth={2} />
                <Area type="monotone" dataKey="value" name="Est. Value" stroke="#0284c7" fill="url(#gradValue)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>
      )}
    </div>
  )
}

function GoalCalculator({ profile }: { profile: Profile }) {
  const [target, setTarget] = useState(1000000)
  const [returnPct, setReturnPct] = useState(12)
  const [years, setYears] = useState(10)
  const [result, setResult] = useState<Record<string, unknown> | null>(null)
  const [loading, setLoading] = useState(false)

  const calculate = async () => {
    setLoading(true)
    try {
      const res = await api.calcGoal(target, returnPct, years)
      setResult(res)
    } finally {
      setLoading(false)
    }
  }

  const chartData = result ? buildGoalChartData(target, returnPct, years) : []

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div>
          <label className="text-xs font-medium text-gray-600 dark:text-gray-400 block mb-1">Target Amount (₹)</label>
          <input type="number" className="input-field" value={target} onChange={(e) => setTarget(Number(e.target.value))} min={10000} />
        </div>
        <div>
          <label className="text-xs font-medium text-gray-600 dark:text-gray-400 block mb-1">Expected Return (%)</label>
          <input type="number" className="input-field" value={returnPct} onChange={(e) => setReturnPct(Number(e.target.value))} min={1} max={30} />
        </div>
        <div>
          <label className="text-xs font-medium text-gray-600 dark:text-gray-400 block mb-1">Duration (years)</label>
          <input type="number" className="input-field" value={years} onChange={(e) => setYears(Number(e.target.value))} min={1} max={40} />
        </div>
      </div>
      <button onClick={calculate} disabled={loading} className="btn-primary w-full">
        {loading ? 'Calculating...' : 'Calculate Monthly SIP Needed'}
      </button>
      {result && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              { label: 'Monthly SIP', key: 'monthly_sip' },
              { label: 'Total Invested', key: 'total_invested' },
              { label: 'Goal Amount', key: 'target_amount' },
              { label: 'Wealth Gain', key: 'wealth_gain' },
            ].map(({ label, key }) => (
              <div key={key} className="rounded-lg bg-surface-50 dark:bg-gray-800/50 border border-surface-200 dark:border-gray-700 p-3 text-center">
                <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">{label}</div>
                <div className="text-sm font-bold text-gray-900 dark:text-white">{formatINR(Number(result[key] ?? 0))}</div>
              </div>
            ))}
          </div>
          {chartData.length > 0 && (
            <ResponsiveContainer width="100%" height={200}>
              <AreaChart data={chartData} margin={{ top: 4, right: 4, left: -10, bottom: 0 }}>
                <defs>
                  <linearGradient id="gradInvested2" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#94a3b8" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#94a3b8" stopOpacity={0} />
                  </linearGradient>
                  <linearGradient id="gradValue2" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.5} />
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="year" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={(v) => formatINR(v)} />
                <Tooltip formatter={(v: unknown, name: unknown) => [formatINR(Number(v ?? 0)), String(name)]} contentStyle={{ borderRadius: '8px', fontSize: '12px' }} />
                <Legend iconType="circle" wrapperStyle={{ fontSize: '11px' }} />
                <Area type="monotone" dataKey="invested" name="Invested" stroke="#94a3b8" fill="url(#gradInvested2)" strokeWidth={2} />
                <Area type="monotone" dataKey="value" name="Goal Progress" stroke="#10b981" fill="url(#gradValue2)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </div>
      )}
    </div>
  )
}

function ELSSCalculator({ profile }: { profile: Profile }) {
  const [annual, setAnnual] = useState(150000)
  const [bracket, setBracket] = useState(profile.tax_bracket_pct || 30)
  const [result, setResult] = useState<Record<string, unknown> | null>(null)
  const [loading, setLoading] = useState(false)

  const calculate = async () => {
    setLoading(true)
    try {
      const res = await api.calcELSS(annual, bracket)
      setResult(res)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label className="text-xs font-medium text-gray-600 dark:text-gray-400 block mb-1">Annual Investment (₹)</label>
          <input type="number" className="input-field" value={annual} onChange={(e) => setAnnual(Number(e.target.value))} max={150000} />
          <p className="text-xs text-gray-400 mt-1">Max ₹1.5L qualifies for 80C deduction</p>
        </div>
        <div>
          <label className="text-xs font-medium text-gray-600 dark:text-gray-400 block mb-1">Tax Bracket (%)</label>
          <select className="input-field" value={bracket} onChange={(e) => setBracket(Number(e.target.value))}>
            <option value={5}>5%</option>
            <option value={10}>10%</option>
            <option value={15}>15%</option>
            <option value={20}>20%</option>
            <option value={30}>30%</option>
          </select>
        </div>
      </div>
      <button onClick={calculate} disabled={loading} className="btn-primary w-full">
        {loading ? 'Calculating...' : 'Calculate Tax Savings'}
      </button>
      {result && (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {[
            { label: 'Tax Saved', key: 'tax_saved' },
            { label: 'Effective Cost', key: 'effective_cost' },
            { label: 'Deduction Limit', key: 'deduction_limit' },
          ].map(({ label, key }) => (
            <div key={key} className="rounded-lg bg-surface-50 dark:bg-gray-800/50 border border-surface-200 dark:border-gray-700 p-3 text-center">
              <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">{label}</div>
              <div className="text-sm font-bold text-gray-900 dark:text-white">{formatINR(Number(result[key] ?? 0))}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function EmergencyCalculator() {
  const [expenses, setExpenses] = useState(30000)
  const [months, setMonths] = useState(6)
  const [result, setResult] = useState<Record<string, unknown> | null>(null)
  const [loading, setLoading] = useState(false)

  const calculate = async () => {
    setLoading(true)
    try {
      const res = await api.calcEmergency(expenses, months)
      setResult(res)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div>
          <label className="text-xs font-medium text-gray-600 dark:text-gray-400 block mb-1">Monthly Expenses (₹)</label>
          <input type="number" className="input-field" value={expenses} onChange={(e) => setExpenses(Number(e.target.value))} min={1000} />
        </div>
        <div>
          <label className="text-xs font-medium text-gray-600 dark:text-gray-400 block mb-1">Coverage (months)</label>
          <select className="input-field" value={months} onChange={(e) => setMonths(Number(e.target.value))}>
            <option value={3}>3 months (minimum)</option>
            <option value={6}>6 months (recommended)</option>
            <option value={12}>12 months (conservative)</option>
          </select>
        </div>
      </div>
      <button onClick={calculate} disabled={loading} className="btn-primary w-full">
        {loading ? 'Calculating...' : 'Calculate Emergency Fund'}
      </button>
      {result && (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {[
            { label: 'Fund Target', key: 'emergency_fund_target' },
            { label: 'Monthly Expenses', key: 'monthly_expenses' },
            { label: 'Months Coverage', key: 'months' },
          ].map(({ label, key }) => (
            <div key={key} className="rounded-lg bg-surface-50 dark:bg-gray-800/50 border border-surface-200 dark:border-gray-700 p-3 text-center">
              <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">{label}</div>
              <div className="text-sm font-bold text-gray-900 dark:text-white">
                {key === 'months' ? String(result[key] ?? '—') : formatINR(Number(result[key] ?? 0))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function Calculators({ profile }: Props) {
  const [active, setActive] = useState<CalcKey>('sip')

  return (
    <div className="p-4 lg:p-6 space-y-4 max-w-3xl mx-auto">
      <div>
        <h1 className="text-xl font-bold text-gray-900 dark:text-white">Financial Calculators</h1>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">Plan your financial future with precision</p>
      </div>

      <Section
        id="sip"
        active={active}
        setActive={setActive}
        icon={TrendingUp}
        title="SIP Calculator"
        subtitle="See how your SIP grows over time with compounding"
      >
        <SIPCalculator profile={profile} />
      </Section>

      <Section
        id="goal"
        active={active}
        setActive={setActive}
        icon={Target}
        title="Goal Planner"
        subtitle="Find the monthly SIP needed to reach your goal"
      >
        <GoalCalculator profile={profile} />
      </Section>

      <Section
        id="elss"
        active={active}
        setActive={setActive}
        icon={Leaf}
        title="ELSS Tax Saver"
        subtitle="Calculate your Section 80C tax savings"
      >
        <ELSSCalculator profile={profile} />
      </Section>

      <Section
        id="emergency"
        active={active}
        setActive={setActive}
        icon={Shield}
        title="Emergency Fund"
        subtitle="How much should you keep as safety net?"
      >
        <EmergencyCalculator />
      </Section>
    </div>
  )
}
