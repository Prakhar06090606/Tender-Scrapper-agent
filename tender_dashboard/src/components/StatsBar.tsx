// src/components/StatsBar.tsx
'use client'
import { useState, useEffect, useCallback } from 'react'
import { fetchStats } from '@/lib/api'
import type { Stats } from '@/types/tender'
import { FileSpreadsheet, Clock, CheckCircle, RefreshCw, ThumbsUp } from 'lucide-react'

interface Props { onRefresh?: () => void }

export default function StatsBar({ onRefresh }: Props) {
  const [stats, setStats]     = useState<Stats | null>(null)
  const [loading, setLoading] = useState(true)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)

  const load = useCallback(async () => {
    try {
      setStats(await fetchStats())
      setLastUpdated(new Date())
    } catch (e) { console.error(e) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => {
    load()
    const i = setInterval(load, 10_000)   // Every 10s for near-real-time stats
    return () => clearInterval(i)
  }, [load])

  if (loading && !stats) return (
    <div className="grid grid-cols-2 lg:grid-cols-5 gap-4 mb-6">
      {[...Array(5)].map((_, i) => (
        <div key={i} className="bg-white rounded-xl border border-gray-200 p-4 animate-pulse">
          <div className="h-3 bg-gray-200 rounded w-24 mb-3" />
          <div className="h-8 bg-gray-200 rounded w-16" />
        </div>
      ))}
    </div>
  )

  const relevant = Object.values(stats?.by_status ?? {}).reduce((a, b) => a + b, 0)

  return (
    <div className="mb-6">
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4 mb-3">
        <Card icon={<FileSpreadsheet className="w-4 h-4" />} label="Total found"   value={stats?.total_tenders ?? 0}     color="indigo" />
        <Card icon={<CheckCircle className="w-4 h-4" />}     label="In Sheet"      value={stats?.written_to_excel ?? 0}   color="green"  />
        <Card icon={<Clock className="w-4 h-4" />}           label="Pending review" value={stats?.by_status?.pending ?? 0} color="amber"  />
        <Card icon={<ThumbsUp className="w-4 h-4" />}        label="Approved"      value={stats?.by_status?.approved ?? 0} color="teal"  />
        <Card icon={<RefreshCw className="w-4 h-4" />}       label="Queued write"  value={stats?.pending_excel_write ?? 0} color="purple" />
      </div>
      <div className="flex items-center justify-between">
        <div className="flex flex-wrap gap-2">
          {stats?.by_category && Object.entries(stats.by_category).map(([cat, count]) => (
            <span key={cat} className="text-xs bg-white border border-gray-200 rounded-full px-3 py-1 text-gray-600">
              {cat}: <span className="font-semibold text-gray-900">{count}</span>
            </span>
          ))}
        </div>
        <div className="flex items-center gap-3 text-xs text-gray-400">
          {lastUpdated && <span>Updated {lastUpdated.toLocaleTimeString()}</span>}
          <button onClick={() => { load(); onRefresh?.() }}
            className="flex items-center gap-1 text-gray-500 hover:text-indigo-600 transition-colors">
            <RefreshCw className="w-3 h-3" /> Refresh
          </button>
        </div>
      </div>
    </div>
  )
}

const COLOR_MAP = {
  indigo: { bg: 'bg-indigo-50', text: 'text-indigo-600', num: 'text-indigo-700' },
  green:  { bg: 'bg-green-50',  text: 'text-green-600',  num: 'text-green-700'  },
  amber:  { bg: 'bg-amber-50',  text: 'text-amber-600',  num: 'text-amber-700'  },
  purple: { bg: 'bg-purple-50', text: 'text-purple-600', num: 'text-purple-700' },
  teal:   { bg: 'bg-teal-50',   text: 'text-teal-600',   num: 'text-teal-700'   },
} as const

function Card({ icon, label, value, color }: {
  icon: React.ReactNode; label: string; value: number; color: keyof typeof COLOR_MAP
}) {
  const c = COLOR_MAP[color]
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4">
      <div className="flex items-center gap-2 mb-2">
        <div className={`${c.bg} ${c.text} p-1.5 rounded-lg`}>{icon}</div>
        <span className="text-xs text-gray-500 font-medium">{label}</span>
      </div>
      <p className={`text-2xl font-semibold ${c.num}`}>{value.toLocaleString()}</p>
    </div>
  )
}
