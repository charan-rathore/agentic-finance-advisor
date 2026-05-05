import { useState, useEffect } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard, MessageCircle, Calculator, Globe, Activity,
  Sun, Moon, LogOut, TrendingUp, Menu,
} from 'lucide-react'
import { cn } from '../lib/utils'
import type { Profile } from '../lib/api'

interface Props {
  profile: Profile
  onLogout: () => Promise<void>
  children: React.ReactNode
}

const NAV_ITEMS = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/chat', icon: MessageCircle, label: 'AI Advisor' },
  { to: '/calculators', icon: Calculator, label: 'Calculators' },
  { to: '/global', icon: Globe, label: 'Global Markets' },
  { to: '/system', icon: Activity, label: 'System Health' },
]

export default function Layout({ profile, onLogout, children }: Props) {
  const navigate = useNavigate()
  const [isDark, setIsDark] = useState(() => {
    if (typeof window === 'undefined') return false
    return localStorage.getItem('theme') === 'dark' ||
      (!localStorage.getItem('theme') && window.matchMedia('(prefers-color-scheme: dark)').matches)
  })
  const [sidebarOpen, setSidebarOpen] = useState(false)

  useEffect(() => {
    const root = document.documentElement
    if (isDark) {
      root.classList.add('dark')
      localStorage.setItem('theme', 'dark')
    } else {
      root.classList.remove('dark')
      localStorage.setItem('theme', 'light')
    }
  }, [isDark])

  const handleLogout = async () => {
    await onLogout()
    navigate('/')
  }

  const Sidebar = ({ mobile = false }: { mobile?: boolean }) => (
    <div className={cn(
      'flex flex-col h-full',
      mobile ? 'w-64' : 'w-64'
    )}>
      {/* Logo */}
      <div className="flex items-center gap-2.5 px-5 py-5 border-b border-surface-200 dark:border-gray-700">
        <div className="w-8 h-8 bg-brand-600 rounded-lg flex items-center justify-center flex-shrink-0">
          <TrendingUp className="w-4.5 h-4.5 text-white" size={18} />
        </div>
        <div>
          <div className="font-bold text-gray-900 dark:text-white text-sm leading-tight">Finsight</div>
          <div className="text-xs text-gray-400 dark:text-gray-500">AI Investment Advisor</div>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto py-4 px-3">
        <div className="space-y-0.5">
          {NAV_ITEMS.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              onClick={() => setSidebarOpen(false)}
              className={({ isActive }) => cn(
                'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors',
                isActive
                  ? 'bg-brand-50 dark:bg-brand-900/30 text-brand-700 dark:text-brand-400'
                  : 'text-gray-600 dark:text-gray-400 hover:bg-surface-100 dark:hover:bg-gray-700/50 hover:text-gray-900 dark:hover:text-gray-100'
              )}
            >
              <Icon size={17} />
              {label}
            </NavLink>
          ))}
        </div>
      </nav>

      {/* Profile + controls at bottom */}
      <div className="border-t border-surface-200 dark:border-gray-700 p-4 space-y-3">
        {/* Profile card */}
        <div className="flex items-center gap-2.5 px-1">
          <div className="w-8 h-8 bg-brand-100 dark:bg-brand-900/40 rounded-full flex items-center justify-center flex-shrink-0">
            <span className="text-brand-700 dark:text-brand-400 text-xs font-bold uppercase">
              {profile.name.slice(0, 2)}
            </span>
          </div>
          <div className="min-w-0">
            <div className="text-sm font-medium text-gray-900 dark:text-white truncate">{profile.name}</div>
            <div className="text-xs text-gray-400 dark:text-gray-500 truncate capitalize">{profile.primary_goal}</div>
          </div>
        </div>

        {/* Dark mode + logout */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => setIsDark(!isDark)}
            className="flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg
                       border border-surface-200 dark:border-gray-600
                       bg-white dark:bg-gray-700 hover:bg-surface-50 dark:hover:bg-gray-600
                       text-gray-600 dark:text-gray-300 text-xs font-medium transition-colors"
            aria-label="Toggle dark mode"
          >
            {isDark ? <Sun size={14} /> : <Moon size={14} />}
            {isDark ? 'Light' : 'Dark'}
          </button>
          <button
            onClick={handleLogout}
            className="flex items-center justify-center w-9 h-9 rounded-lg
                       border border-surface-200 dark:border-gray-600
                       bg-white dark:bg-gray-700 hover:bg-red-50 dark:hover:bg-red-900/20
                       text-gray-400 hover:text-red-500 transition-colors"
            title="Reset profile"
          >
            <LogOut size={14} />
          </button>
        </div>
      </div>
    </div>
  )

  return (
    <div className="min-h-screen bg-surface-50 dark:bg-gray-950 flex">
      {/* Desktop sidebar */}
      <aside className="hidden lg:flex flex-col w-64 border-r border-surface-200 dark:border-gray-700 bg-white dark:bg-gray-900 fixed inset-y-0 left-0 z-30">
        <Sidebar />
      </aside>

      {/* Mobile sidebar overlay */}
      {sidebarOpen && (
        <div className="lg:hidden fixed inset-0 z-40 flex">
          <div
            className="fixed inset-0 bg-black/40 backdrop-blur-sm"
            onClick={() => setSidebarOpen(false)}
          />
          <aside className="relative flex flex-col w-64 bg-white dark:bg-gray-900 border-r border-surface-200 dark:border-gray-700">
            <Sidebar mobile />
          </aside>
        </div>
      )}

      {/* Main content */}
      <div className="flex-1 lg:ml-64 flex flex-col min-h-screen">
        {/* Top bar (mobile only) */}
        <header className="lg:hidden sticky top-0 z-20 flex items-center justify-between px-4 py-3 bg-white dark:bg-gray-900 border-b border-surface-200 dark:border-gray-700">
          <button
            onClick={() => setSidebarOpen(true)}
            className="p-2 rounded-lg text-gray-500 hover:bg-surface-100 dark:hover:bg-gray-700"
          >
            <Menu size={20} />
          </button>
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 bg-brand-600 rounded-md flex items-center justify-center">
              <TrendingUp size={14} className="text-white" />
            </div>
            <span className="font-bold text-sm dark:text-white">Finsight</span>
          </div>
          <button
            onClick={() => setIsDark(!isDark)}
            className="p-2 rounded-lg text-gray-500 hover:bg-surface-100 dark:hover:bg-gray-700 dark:text-gray-400"
          >
            {isDark ? <Sun size={18} /> : <Moon size={18} />}
          </button>
        </header>

        <main className="flex-1 overflow-y-auto">
          {children}
        </main>
      </div>
    </div>
  )
}
