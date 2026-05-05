import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function formatINR(amount: number): string {
  if (amount >= 10_000_000) return `₹${(amount / 10_000_000).toFixed(2)} Cr`
  if (amount >= 100_000) return `₹${(amount / 100_000).toFixed(2)} L`
  return `₹${amount.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
}

export function formatPrice(price: number | null | undefined): string {
  if (price == null) return 'N/A'
  if (price >= 10000) return `₹${(price / 1000).toFixed(1)}K`
  if (price >= 1000) return `₹${price.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`
  return `₹${price.toFixed(2)}`
}

export function classifyDNA(profile: { risk_tolerance?: string; horizon_pref?: string }): string {
  if (profile.risk_tolerance === 'low' || profile.horizon_pref === 'short') return 'Conservative Starter'
  if (profile.risk_tolerance === 'high' && profile.horizon_pref === 'long') return 'Bold Grower'
  return 'Balanced Builder'
}

export function confidenceLabel(score: number): { label: string; color: string } {
  if (score >= 0.75) return { label: 'Grounded', color: 'text-emerald-700 bg-emerald-50 border-emerald-200' }
  if (score >= 0.5) return { label: 'Partial', color: 'text-amber-700 bg-amber-50 border-amber-200' }
  return { label: 'Limited', color: 'text-red-700 bg-red-50 border-red-200' }
}
