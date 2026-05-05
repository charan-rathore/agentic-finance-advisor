const isCapacitor = typeof (window as unknown as Record<string, unknown>).Capacitor !== 'undefined'
const BASE = isCapacitor ? 'http://10.0.2.2:8000' : ''

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`API error ${res.status}: ${text}`)
  }
  return res.json()
}

export interface Profile {
  id?: number
  name: string
  monthly_income: string
  monthly_sip_budget: string
  risk_tolerance: string
  tax_bracket_pct: number
  primary_goal: string
  horizon_pref: string
  created_at?: string
}

export interface ProfileResponse {
  profile: Profile | null
}

export interface ChatResponse {
  answer: string
  sources: string[]
  confidence: number
  fast_path: string | null
  calculator?: Record<string, unknown> | null
  error?: string
}

export interface StockPrice {
  symbol: string
  price_inr?: number
  price?: number
  change_pct: number | null
  data_label?: string
  fetched_at?: string
}

export interface Nudge {
  icon: string
  title: string
  body: string
  priority: number
  rule: string
}

export interface NewsArticle {
  title: string
  link: string
  published: string
  source: string
  summary?: string
}

export interface MutualFundNAV {
  scheme_code: number
  friendly_name: string
  fund_house: string
  scheme_name: string
  scheme_category: string
  scheme_type: string
  nav: number
  nav_date: string
  fetched_at: string
}

export interface RBIRates {
  repo_rate_pct: number | null
  reverse_repo_rate_pct: number | null
  crr_pct: number | null
  slr_pct: number | null
  source: string
  fetched_at?: string
  note?: string
}

export interface SystemHealth {
  wiki: {
    total_pages: number
    fresh_count: number
    stale_count: number
    missing_frontmatter: number
    by_type: Record<string, number>
    stale: Array<Record<string, unknown>>
    fresh: Array<Record<string, unknown>>
    latest_lint_report: Record<string, unknown> | null
  }
  raw_data: Record<string, unknown>
}

export const api = {
  getProfile: () => request<ProfileResponse>('/api/profile'),

  createProfile: (data: Omit<Profile, 'id' | 'created_at'>) =>
    request<ProfileResponse>('/api/profile', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  deleteProfile: () => request<{ status: string }>('/api/profile', { method: 'DELETE' }),

  chat: (question: string, hindi = false, market = 'india') =>
    request<ChatResponse>('/api/chat', {
      method: 'POST',
      body: JSON.stringify({ question, hindi, market }),
    }),

  getIndiaPrices: () => request<{ prices: StockPrice[] }>('/api/market/india/prices'),
  getIndiaNav: () => request<{ nav: unknown[] }>('/api/market/india/nav'),
  getIndiaRBI: () => request<{ rates: Record<string, unknown> }>('/api/market/india/rbi'),
  getGlobalPrices: () => request<{ prices: StockPrice[] }>('/api/market/global/prices'),
  getGlobalHeadlines: () => request<{ headlines: Array<Record<string, string>> }>('/api/market/global/headlines'),
  getGlobalInsights: () => request<{ insights: Array<Record<string, unknown>> }>('/api/market/global/insights'),

  getGlobalNews: () => request<{ articles: NewsArticle[]; fetched_at: string }>('/api/market/global/news'),
  getIndiaNews: () => request<{ articles: NewsArticle[]; fetched_at: string }>('/api/market/india/news'),
  getGlobalSentiment: () => request<{ sentiment: Record<string, unknown> | null }>('/api/market/global/sentiment'),

  getNudges: (recentQuestions: string[] = [], market?: Record<string, unknown>) =>
    request<{ nudges: Nudge[] }>('/api/nudges', {
      method: 'POST',
      body: JSON.stringify({ recent_questions: recentQuestions, market }),
    }),

  getSources: () => request<{ sources: Array<Record<string, unknown>> }>('/api/sources'),
  getWikiHistory: (pageName: string) => request<{ history: Array<Record<string, unknown>> }>(`/api/wiki/history/${pageName}`),
  getSystemHealth: () => request<SystemHealth>('/api/system/health'),

  calcSIP: (monthly: number, returnPct: number, years: number) =>
    request<Record<string, unknown>>('/api/calc/sip', {
      method: 'POST',
      body: JSON.stringify({ monthly, annual_return_pct: returnPct, years }),
    }),

  calcGoal: (target: number, returnPct: number, years: number) =>
    request<Record<string, unknown>>('/api/calc/goal', {
      method: 'POST',
      body: JSON.stringify({ target, annual_return_pct: returnPct, years }),
    }),

  calcELSS: (annualInvested: number, taxBracket: number) =>
    request<Record<string, unknown>>('/api/calc/elss', {
      method: 'POST',
      body: JSON.stringify({ annual_invested: annualInvested, tax_bracket_pct: taxBracket }),
    }),

  calcEmergency: (monthlyExpenses: number, months = 6) =>
    request<Record<string, unknown>>('/api/calc/emergency', {
      method: 'POST',
      body: JSON.stringify({ monthly_expenses: monthlyExpenses, months }),
    }),
}
