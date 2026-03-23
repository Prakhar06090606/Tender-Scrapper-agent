'use client'

import { useState, useEffect, useCallback, useRef } from 'react'
import { fetchTenders } from '@/lib/api'
import type { Tender, TenderFilters } from '@/types/tender'
import StatusBadge from './StatusBadge'
import { Search, ChevronLeft, ChevronRight, ExternalLink, Filter, AlertTriangle, Clock } from 'lucide-react'

interface Props {
  onSelectTender: (tender: Tender) => void
  refreshKey: number
}

const CATEGORIES = ['All', 'Consulting', 'IT', 'Medical Oxygen', 'Training and Skill']
const STATUSES   = ['All', 'pending', 'approved', 'rejected', 'reconsidering']
const SOURCES    = ['All', 'UNGM', 'GeM', 'eProcure', 'DefProc', 'Google']
const RELEVANCES = ['All', 'Relevant', 'Not relevant']

export default function TenderTable({ onSelectTender, refreshKey }: Props) {
  const [tenders, setTenders]           = useState<Tender[]>([])
  const [total, setTotal]               = useState(0)
  const [page, setPage]                 = useState(0)
  const [loading, setLoading]           = useState(true)
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [filters, setFilters]           = useState<TenderFilters>({
    category: '', status: '', source: '', relevance: '', search: '',
  })

  // Debounce search input
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(filters.search), 400)
    return () => clearTimeout(t)
  }, [filters.search])

  // Reset to page 0 when filters change
  useEffect(() => {
    setPage(0)
  }, [filters.category, filters.status, filters.source, filters.relevance, debouncedSearch])

  // Core data fetch — stable ref so interval doesn't recreate
  const filtersRef = useRef(filters)
  const pageRef    = useRef(page)
  filtersRef.current = filters
  pageRef.current    = page

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const f = filtersRef.current
      const resp = await fetchTenders({
        category:  f.category  || undefined,
        status:    f.status    || undefined,
        source:    f.source    || undefined,
        relevance: f.relevance || undefined,
      }, pageRef.current, 50)
      setTenders(resp.tenders)
      setTotal(resp.total)
    } catch (e) {
      console.error('Failed to fetch tenders:', e)
    } finally {
      setLoading(false)
    }
  }, []) // stable — reads latest values via refs

  // Fetch when filters/page/refreshKey change
  useEffect(() => {
    load()
  }, [filters.category, filters.status, filters.source, filters.relevance, page, refreshKey, load])

  // Auto-refresh every 15s
  useEffect(() => {
    const interval = setInterval(load, 15_000)
    return () => clearInterval(interval)
  }, [load])

  const displayed = debouncedSearch
    ? tenders.filter(t =>
        t.tender_title?.toLowerCase().includes(debouncedSearch.toLowerCase()) ||
        t.agency?.toLowerCase().includes(debouncedSearch.toLowerCase()) ||
        t.brief_specification?.toLowerCase().includes(debouncedSearch.toLowerCase())
      )
    : tenders

  const totalPages = Math.ceil(total / 50)

  const setFilter = (key: keyof TenderFilters, value: string) =>
    setFilters(prev => ({ ...prev, [key]: value === 'All' ? '' : value }))

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">

      {/* Filter bar */}
      <div className="p-4 border-b border-gray-100 flex flex-wrap gap-3 items-center">
        <div className="relative flex-1 min-w-48">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search tenders, agencies..."
            value={filters.search}
            onChange={e => setFilter('search', e.target.value)}
            className="w-full pl-9 pr-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-300"
          />
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <Filter className="w-4 h-4 text-gray-400" />
          {([
            { key: 'category'  as const, opts: CATEGORIES },
            { key: 'status'    as const, opts: STATUSES   },
            { key: 'source'    as const, opts: SOURCES    },
            { key: 'relevance' as const, opts: RELEVANCES },
          ]).map(({ key, opts }) => (
            <select
              key={key}
              value={filters[key] || 'All'}
              onChange={e => setFilter(key, e.target.value)}
              className="text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-300 bg-white capitalize"
            >
              {opts.map(o => <option key={o}>{o}</option>)}
            </select>
          ))}
        </div>

        <span className="text-xs text-gray-400 ml-auto">{displayed.length} of {total}</span>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50">
            <tr>
              {['Agency','Tender Title','Category','Source','Deadline','Relevance','Issues','Status','Sheet'].map(h => (
                <th key={h} className="text-left text-xs font-semibold text-gray-500 uppercase tracking-wider px-4 py-3 border-b border-gray-100">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {loading && [...Array(8)].map((_, i) => (
              <tr key={i} className="animate-pulse">
                {[...Array(9)].map((_, j) => (
                  <td key={j} className="px-4 py-3">
                    <div className="h-3 bg-gray-100 rounded w-20" />
                  </td>
                ))}
              </tr>
            ))}

            {!loading && displayed.length === 0 && (
              <tr>
                <td colSpan={9} className="text-center py-16 text-gray-400">
                  <p className="text-base mb-1">No tenders found</p>
                  <p className="text-xs">The agent is searching — check back in a few minutes</p>
                </td>
              </tr>
            )}

            {!loading && displayed.map(t => (
              <TenderRow key={t.id} tender={t} onClick={() => onSelectTender(t)} />
            ))}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between px-4 py-3 border-t border-gray-100">
          <span className="text-xs text-gray-500">Page {page + 1} of {totalPages}</span>
          <div className="flex gap-2">
            <button
              onClick={() => setPage(p => Math.max(0, p - 1))}
              disabled={page === 0}
              className="p-1.5 rounded-lg border border-gray-200 disabled:opacity-40 hover:bg-gray-50"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button
              onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
              className="p-1.5 rounded-lg border border-gray-200 disabled:opacity-40 hover:bg-gray-50"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function TenderRow({ tender: t, onClick }: { tender: Tender; onClick: () => void }) {
  const today = new Date()
  today.setHours(0, 0, 0, 0)

  const deadlineStatus = (() => {
    if (!t.submission_deadline_date || t.submission_deadline_date === 'Info not fetched') return 'unknown'
    const d = new Date(t.submission_deadline_date)
    if (isNaN(d.getTime())) return 'unknown'
    const diff = (d.getTime() - today.getTime()) / (1000 * 60 * 60 * 24)
    if (diff < 0)  return 'expired'
    if (diff <= 2) return 'urgent'
    return 'ok'
  })()

  const rowBg = deadlineStatus === 'expired'
    ? 'bg-red-50 hover:bg-red-100'
    : deadlineStatus === 'urgent'
    ? 'bg-yellow-50 hover:bg-yellow-100'
    : t.relevance === 'Relevant'
    ? 'bg-green-50 hover:bg-green-100'
    : 'hover:bg-indigo-50/40'

  const deadlineDisplay = () => {
    if (!t.submission_deadline_date || t.submission_deadline_date === 'Info not fetched')
      return <span className="text-gray-300">—</span>
    if (deadlineStatus === 'expired')
      return <span className="text-red-600 font-medium flex items-center gap-1"><AlertTriangle className="w-3 h-3" />{t.submission_deadline_date}</span>
    if (deadlineStatus === 'urgent')
      return <span className="text-amber-600 font-medium flex items-center gap-1"><Clock className="w-3 h-3" />{t.submission_deadline_date}</span>
    return <span className="text-gray-600">{t.submission_deadline_date}</span>
  }

  const hasIssues = t.issues_faced && t.issues_faced !== 'Info not fetched'

  return (
    <tr onClick={onClick} className={`cursor-pointer transition-colors ${rowBg}`}>
      <td className="px-4 py-3 font-medium text-gray-900 whitespace-nowrap max-w-28 truncate">{t.agency ?? '—'}</td>
      <td className="px-4 py-3 max-w-xs">
        <div className="flex items-start gap-1.5">
          <span className="line-clamp-2 text-gray-800 leading-snug text-xs" title={t.tender_title ?? ''}>
            {t.tender_title ?? 'Untitled'}
          </span>
          {t.link && t.link !== 'Info not fetched' && (
            <a href={t.link} target="_blank" rel="noopener noreferrer"
              onClick={e => e.stopPropagation()}
              className="text-indigo-400 hover:text-indigo-600 flex-shrink-0 mt-0.5">
              <ExternalLink className="w-3 h-3" />
            </a>
          )}
        </div>
      </td>
      <td className="px-4 py-3 whitespace-nowrap"><StatusBadge type="category" value={t.category} /></td>
      <td className="px-4 py-3 whitespace-nowrap"><StatusBadge type="source" value={t.source_site} /></td>
      <td className="px-4 py-3 text-xs whitespace-nowrap">{deadlineDisplay()}</td>
      <td className="px-4 py-3 whitespace-nowrap">
        {t.relevance && t.relevance !== 'Info not fetched'
          ? <StatusBadge type="relevance" value={t.relevance} />
          : <span className="text-gray-300 text-xs">—</span>}
      </td>
      <td className="px-4 py-3 text-center">
        {hasIssues
          ? <span title={t.issues_faced!} className="text-amber-500 text-sm">⚠️</span>
          : <span className="text-gray-200 text-sm">—</span>}
      </td>
      <td className="px-4 py-3 whitespace-nowrap"><StatusBadge type="status" value={t.status} /></td>
      <td className="px-4 py-3 text-center">
        {t.written_to_excel
          ? <span className="text-green-500">✓</span>
          : <span className="text-gray-300">○</span>}
      </td>
    </tr>
  )
}
