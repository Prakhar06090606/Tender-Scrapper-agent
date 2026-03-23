// src/app/page.tsx
'use client'
import { useState, useCallback } from 'react'
import type { Tender } from '@/types/tender'
import StatsBar from '@/components/StatsBar'
import TenderTable from '@/components/TenderTable'
import TenderDrawer from '@/components/TenderDrawer'
import AgentControls from '@/components/AgentControls'

export default function DashboardPage() {
  const [selected, setSelected]   = useState<Tender | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)

  const refresh = useCallback(() => setRefreshKey(k => k + 1), [])

  const handleStatusChange = useCallback((id: number, status: string) => {
    setSelected(prev => prev?.id === id ? { ...prev, status: status as any } : prev)
    refresh()
  }, [refresh])

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200 sticky top-0 z-30">
        <div className="max-w-screen-2xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-7 h-7 bg-indigo-600 rounded-lg flex items-center justify-center">
              <span className="text-white text-xs font-bold">T</span>
            </div>
            <div>
              <h1 className="text-sm font-semibold text-gray-900">Tender Agent — EduBild</h1>
              <p className="text-xs text-gray-400 hidden sm:block">UNGM · GeM · eProcure · DefProc · Google</p>
            </div>
          </div>
          <AgentControls onRunComplete={refresh} />
        </div>
      </header>

      <main className="max-w-screen-2xl mx-auto px-4 sm:px-6 py-6">
        <StatsBar onRefresh={refresh} />
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-base font-semibold text-gray-900">All tenders</h2>
            <p className="text-xs text-gray-400 mt-0.5">
              🟢 Relevant &nbsp;·&nbsp; 🟡 Deadline ≤2 days &nbsp;·&nbsp; 🔴 Expired &nbsp;·&nbsp; ⚠️ Has issues
            </p>
          </div>
        </div>
        <TenderTable onSelectTender={setSelected} refreshKey={refreshKey} />
      </main>

      <TenderDrawer
        tender={selected}
        onClose={() => setSelected(null)}
        onStatusChange={handleStatusChange}
      />
    </div>
  )
}
