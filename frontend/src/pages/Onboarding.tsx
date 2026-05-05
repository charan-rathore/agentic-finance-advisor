import { useState } from 'react'
import { api } from '../lib/api'
import { TrendingUp, ArrowRight, Check } from 'lucide-react'
import { cn } from '../lib/utils'

interface Props {
  onComplete: () => Promise<void>
}

const INCOME_BRACKETS = [
  'Below ₹25K',
  '₹25K – ₹50K',
  '₹50K – ₹1L',
  '₹1L – ₹2L',
  'Above ₹2L',
]

const SIP_BRACKETS = [
  'Below ₹1K',
  '₹1K – ₹5K',
  '₹5K – ₹10K',
  '₹10K – ₹25K',
  '₹25K – ₹50K',
  'Above ₹50K',
]

const GOALS = [
  'Build emergency fund',
  'Save tax (80C)',
  'Grow wealth (SIP)',
  'Retirement planning',
  'Child education',
  'Buy a house',
  'Just learning',
]

const RISK_OPTIONS = [
  { value: 'low', label: 'Conservative', desc: 'I prefer safety over higher returns' },
  { value: 'medium', label: 'Moderate', desc: 'I can handle normal market swings' },
  { value: 'high', label: 'Aggressive', desc: 'I can hold through 30%+ drawdowns' },
]

const HORIZON_OPTIONS = [
  { value: 'short', label: '< 1 year' },
  { value: 'intermediate', label: '2 – 5 years' },
  { value: 'long', label: '5+ years' },
]

export default function Onboarding({ onComplete }: Props) {
  const [step, setStep] = useState(0)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [data, setData] = useState({
    name: '',
    monthly_income: '',
    monthly_sip_budget: '',
    risk_tolerance: '',
    primary_goal: '',
    horizon_pref: '',
    tax_bracket_pct: 30,
  })

  const totalSteps = 4

  const canProceed = (): boolean => {
    switch (step) {
      case 0: return data.name.trim().length > 0
      case 1: return data.monthly_income !== '' && data.monthly_sip_budget !== ''
      case 2: return data.risk_tolerance !== '' && data.horizon_pref !== ''
      case 3: return data.primary_goal !== ''
      default: return false
    }
  }

  const handleNext = async () => {
    if (step < totalSteps - 1) {
      setError('')
      setStep(step + 1)
    } else {
      setSaving(true)
      setError('')
      try {
        await api.createProfile({
          name: data.name.trim(),
          monthly_income: data.monthly_income,
          monthly_sip_budget: data.monthly_sip_budget,
          risk_tolerance: data.risk_tolerance,
          tax_bracket_pct: data.tax_bracket_pct,
          primary_goal: data.primary_goal,
          horizon_pref: data.horizon_pref,
        })
        await onComplete()
      } catch (err) {
        console.error('Failed to save profile:', err)
        setError('Could not connect to the backend. Make sure the API server is running on port 8000.')
      } finally {
        setSaving(false)
      }
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-brand-900 via-brand-800 to-brand-700 flex items-center justify-center p-4">
      <div className="w-full max-w-lg">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-2.5 mb-3">
            <div className="w-10 h-10 bg-white/10 backdrop-blur rounded-xl flex items-center justify-center">
              <TrendingUp className="w-6 h-6 text-white" />
            </div>
            <h1 className="text-2xl font-bold text-white">Finsight</h1>
          </div>
          <p className="text-blue-200 text-sm">AI-powered investment intelligence for Indian investors</p>
        </div>

        {/* Progress */}
        <div className="flex gap-2 mb-6">
          {Array.from({ length: totalSteps }).map((_, i) => (
            <div
              key={i}
              className={cn(
                'h-1.5 flex-1 rounded-full transition-all duration-300',
                i <= step ? 'bg-white' : 'bg-white/20'
              )}
            />
          ))}
        </div>

        {/* Card */}
        <div className="bg-white rounded-2xl shadow-2xl p-6 sm:p-8 animate-fade-in">
          {step === 0 && (
            <div>
              <h2 className="text-xl font-bold text-gray-900 mb-1">What should we call you?</h2>
              <p className="text-sm text-gray-500 mb-6">We'll personalize insights based on your profile.</p>
              <input
                type="text"
                className="input-field text-lg"
                placeholder="e.g. Priya"
                value={data.name}
                onChange={(e) => setData({ ...data, name: e.target.value })}
                autoFocus
              />
            </div>
          )}

          {step === 1 && (
            <div>
              <h2 className="text-xl font-bold text-gray-900 mb-1">Your financial snapshot</h2>
              <p className="text-sm text-gray-500 mb-6">Helps us suggest suitable investment amounts.</p>

              <label className="block text-sm font-medium text-gray-700 mb-2">Monthly take-home income</label>
              <div className="grid grid-cols-2 gap-2 mb-5">
                {INCOME_BRACKETS.map((b) => (
                  <button
                    key={b}
                    onClick={() => setData({ ...data, monthly_income: b })}
                    className={cn(
                      'px-3 py-2.5 rounded-lg border text-sm font-medium transition-all',
                      data.monthly_income === b
                        ? 'border-brand-500 bg-brand-50 text-brand-700'
                        : 'border-surface-200 text-gray-600 hover:border-gray-300'
                    )}
                  >
                    {b}
                  </button>
                ))}
              </div>

              <label className="block text-sm font-medium text-gray-700 mb-2">Comfortable monthly investment</label>
              <div className="grid grid-cols-2 gap-2">
                {SIP_BRACKETS.map((b) => (
                  <button
                    key={b}
                    onClick={() => setData({ ...data, monthly_sip_budget: b })}
                    className={cn(
                      'px-3 py-2.5 rounded-lg border text-sm font-medium transition-all',
                      data.monthly_sip_budget === b
                        ? 'border-brand-500 bg-brand-50 text-brand-700'
                        : 'border-surface-200 text-gray-600 hover:border-gray-300'
                    )}
                  >
                    {b}
                  </button>
                ))}
              </div>
            </div>
          )}

          {step === 2 && (
            <div>
              <h2 className="text-xl font-bold text-gray-900 mb-1">Risk & time horizon</h2>
              <p className="text-sm text-gray-500 mb-6">We'll match our suggestions to your comfort level.</p>

              <label className="block text-sm font-medium text-gray-700 mb-2">Risk tolerance</label>
              <div className="space-y-2 mb-5">
                {RISK_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    onClick={() => setData({ ...data, risk_tolerance: opt.value })}
                    className={cn(
                      'w-full flex items-center gap-3 px-4 py-3 rounded-lg border text-left transition-all',
                      data.risk_tolerance === opt.value
                        ? 'border-brand-500 bg-brand-50'
                        : 'border-surface-200 hover:border-gray-300'
                    )}
                  >
                    <div className={cn(
                      'w-5 h-5 rounded-full border-2 flex items-center justify-center flex-shrink-0',
                      data.risk_tolerance === opt.value ? 'border-brand-600 bg-brand-600' : 'border-gray-300'
                    )}>
                      {data.risk_tolerance === opt.value && <Check className="w-3 h-3 text-white" />}
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-gray-900">{opt.label}</p>
                      <p className="text-xs text-gray-500">{opt.desc}</p>
                    </div>
                  </button>
                ))}
              </div>

              <label className="block text-sm font-medium text-gray-700 mb-2">Investment horizon</label>
              <div className="grid grid-cols-3 gap-2">
                {HORIZON_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    onClick={() => setData({ ...data, horizon_pref: opt.value })}
                    className={cn(
                      'px-3 py-2.5 rounded-lg border text-sm font-medium text-center transition-all',
                      data.horizon_pref === opt.value
                        ? 'border-brand-500 bg-brand-50 text-brand-700'
                        : 'border-surface-200 text-gray-600 hover:border-gray-300'
                    )}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {step === 3 && (
            <div>
              <h2 className="text-xl font-bold text-gray-900 mb-1">Your primary goal</h2>
              <p className="text-sm text-gray-500 mb-6">We'll prioritize advice around this objective.</p>

              <div className="grid grid-cols-1 gap-2">
                {GOALS.map((g) => (
                  <button
                    key={g}
                    onClick={() => setData({ ...data, primary_goal: g })}
                    className={cn(
                      'flex items-center gap-3 px-4 py-3 rounded-lg border text-left text-sm font-medium transition-all',
                      data.primary_goal === g
                        ? 'border-brand-500 bg-brand-50 text-brand-700'
                        : 'border-surface-200 text-gray-600 hover:border-gray-300'
                    )}
                  >
                    <div className={cn(
                      'w-5 h-5 rounded-full border-2 flex items-center justify-center flex-shrink-0',
                      data.primary_goal === g ? 'border-brand-600 bg-brand-600' : 'border-gray-300'
                    )}>
                      {data.primary_goal === g && <Check className="w-3 h-3 text-white" />}
                    </div>
                    {g}
                  </button>
                ))}
              </div>

              <div className="mt-5">
                <label className="block text-sm font-medium text-gray-700 mb-2">Tax slab (for ELSS/NPS suggestions)</label>
                <select
                  className="input-field"
                  value={data.tax_bracket_pct}
                  onChange={(e) => setData({ ...data, tax_bracket_pct: Number(e.target.value) })}
                >
                  <option value={0}>0% (New regime / no tax)</option>
                  <option value={5}>5%</option>
                  <option value={20}>20%</option>
                  <option value={30}>30%</option>
                </select>
              </div>
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="mt-5 px-4 py-3 rounded-lg bg-red-50 border border-red-200 text-sm text-red-700">
              {error}
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center justify-between mt-8">
            {step > 0 ? (
              <button onClick={() => setStep(step - 1)} className="btn-secondary text-sm">
                Back
              </button>
            ) : (
              <div />
            )}
            <button
              onClick={handleNext}
              disabled={!canProceed() || saving}
              className="btn-primary flex items-center gap-2 text-sm"
            >
              {step === totalSteps - 1 ? (saving ? 'Saving...' : 'Start exploring') : 'Continue'}
              {!saving && <ArrowRight className="w-4 h-4" />}
            </button>
          </div>
        </div>

        <p className="text-center text-blue-200/60 text-xs mt-6">
          Step {step + 1} of {totalSteps} · Takes about a minute
        </p>
      </div>
    </div>
  )
}
