import { Routes, Route, Navigate } from 'react-router-dom'
import { useState, useEffect, useCallback } from 'react'
import { api, type Profile } from './lib/api'
import Layout from './components/Layout'
import Onboarding from './pages/Onboarding'
import Dashboard from './pages/Dashboard'
import Chat from './pages/Chat'
import Calculators from './pages/Calculators'
import GlobalMarkets from './pages/GlobalMarkets'
import SystemHealth from './pages/SystemHealth'

export default function App() {
  const [profile, setProfile] = useState<Profile | null | undefined>(undefined)
  const [loading, setLoading] = useState(true)

  const loadProfile = useCallback(async () => {
    try {
      const res = await api.getProfile()
      setProfile(res.profile)
    } catch {
      setProfile(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadProfile()
  }, [loadProfile])

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-surface-50">
        <div className="text-center">
          <div className="w-10 h-10 border-3 border-brand-600 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
          <p className="text-gray-500 font-medium">Loading Finsight...</p>
        </div>
      </div>
    )
  }

  if (!profile) {
    return <Onboarding onComplete={loadProfile} />
  }

  return (
    <Layout profile={profile} onLogout={async () => { await api.deleteProfile(); setProfile(null) }}>
      <Routes>
        <Route path="/" element={<Dashboard profile={profile} />} />
        <Route path="/chat" element={<Chat profile={profile} />} />
        <Route path="/calculators" element={<Calculators profile={profile} />} />
        <Route path="/global" element={<GlobalMarkets />} />
        <Route path="/system" element={<SystemHealth />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  )
}
