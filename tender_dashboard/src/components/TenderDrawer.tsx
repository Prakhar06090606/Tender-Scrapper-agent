// src/components/TenderDrawer.tsx — full detail panel with all 26 fields
'use client'

import { useState, useEffect } from 'react'
import { updateStatus } from '@/lib/api'
import type { Tender } from '@/types/tender'
import StatusBadge from './StatusBadge'
import {
  X, ExternalLink, CheckCircle, XCircle, RefreshCw,
  Calendar, MapPin, Users, Building2, Globe, DollarSign,
  FileText, Plane, Receipt, Handshake, ClipboardList,
  AlertTriangle, Phone, Mail, User, Link2
} from 'lucide-react'

interface Props {
  tender: Tender | null
  onClose: () => void
  onStatusChange: (id: number, status: string) => void
}

export default function TenderDrawer({ tender, onClose, onStatusChange }: Props) {
  const [currentStatus, setCurrentStatus] = useState(tender?.status)
  const [updating, setUpdating] = useState(false)

  useEffect(() => {
    setCurrentStatus(tender?.status)
  }, [tender?.id])

  if (!tender) return null

  const handleStatus = async (status: 'approved' | 'rejected' | 'reconsidering') => {
    setUpdating(true)
    const prev = currentStatus
    setCurrentStatus(status)
    onStatusChange(tender.id, status)
    try {
      await updateStatus(tender.id, status)
    } catch {
      setCurrentStatus(prev)
      onStatusChange(tender.id, prev ?? 'pending')
    } finally { setUpdating(false) }
  }

  const isExpired = (() => {
    if (!tender.submission_deadline_date || tender.submission_deadline_date === 'Info not fetched') return false
    const d = new Date(tender.submission_deadline_date)
    return !isNaN(d.getTime()) && d < new Date()
  })()

  // Parse important_links into array of {label, url}
  const parsedLinks = (() => {
    if (!tender.important_links || tender.important_links === 'Info not fetched') return []
    return tender.important_links.split('|').map(part => {
      const colonIdx = part.indexOf(': ')
      if (colonIdx === -1) return { label: 'Link', url: part.trim() }
      return { label: part.slice(0, colonIdx).trim(), url: part.slice(colonIdx + 2).trim() }
    }).filter(l => l.url.startsWith('http'))
  })()

  return (
    <>
      <div className="fixed inset-0 bg-black/30 z-40" onClick={onClose} />
      <div className="fixed right-0 top-0 h-full w-full max-w-2xl bg-white shadow-2xl z-50 flex flex-col overflow-hidden">

        {/* Header */}
        <div className="flex items-start justify-between p-5 border-b border-gray-100 flex-shrink-0">
          <div className="flex-1 pr-4">
            <div className="flex items-center gap-2 mb-2 flex-wrap">
              <StatusBadge type="category" value={tender.category} />
              <StatusBadge type="source" value={tender.source_site} />
              {tender.relevance && tender.relevance !== 'Info not fetched' &&
                <StatusBadge type="relevance" value={tender.relevance} />}
              <StatusBadge type="status" value={(currentStatus ?? 'pending') as any} />
              {isExpired && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700 border border-red-200">
                  <AlertTriangle className="w-3 h-3" /> Expired
                </span>
              )}
            </div>
            <h2 className="text-base font-semibold text-gray-900 leading-snug">
              {tender.tender_title ?? 'Untitled Tender'}
            </h2>
            {tender.link && tender.link !== 'Info not fetched' && (
              <a href={tender.link} target="_blank" rel="noopener noreferrer"
                className="text-xs text-indigo-500 hover:text-indigo-700 flex items-center gap-1 mt-1">
                <ExternalLink className="w-3 h-3" /> View original tender
              </a>
            )}
          </div>
          <button onClick={onClose} className="p-2 hover:bg-gray-100 rounded-lg">
            <X className="w-5 h-5 text-gray-500" />
          </button>
        </div>

        {/* Action buttons */}
        <div className="px-5 py-3 bg-gray-50 border-b border-gray-100 flex-shrink-0">
          <p className="text-xs text-gray-500 mb-2 font-medium uppercase tracking-wide">Your decision</p>
          <div className="flex gap-2">
            {[
              { s: 'approved' as const,     color: 'green', icon: <CheckCircle className="w-4 h-4" />, label: 'Approve' },
              { s: 'reconsidering' as const, color: 'blue',  icon: <RefreshCw className="w-4 h-4" />,   label: 'Reconsider' },
              { s: 'rejected' as const,      color: 'red',   icon: <XCircle className="w-4 h-4" />,     label: 'Reject' },
            ].map(({ s, color, icon, label }) => (
              <button key={s}
                onClick={() => handleStatus(s)}
                disabled={updating}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium border transition-all disabled:opacity-50
                  ${currentStatus === s
                    ? `bg-${color}-600 text-white border-${color}-600`
                    : `bg-white text-${color}-700 border-${color}-300 hover:bg-${color}-50`}`}>
                {icon}{label}
              </button>
            ))}
          </div>
        </div>

        {/* All fields */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4">

          {/* Key info grid */}
          <div className="grid grid-cols-2 gap-3">
            <Field icon={<Building2 className="w-4 h-4" />} label="Agency" value={tender.agency} />
            <Field icon={<MapPin className="w-4 h-4" />} label="Area" value={tender.area} />
            <Field icon={<Calendar className="w-4 h-4" />} label="Deadline date"
              value={tender.submission_deadline_date}
              highlight={isExpired ? 'red' : undefined} />
            <Field icon={<Calendar className="w-4 h-4" />} label="Deadline time" value={tender.submission_deadline_time} />
            <Field icon={<MapPin className="w-4 h-4" />} label="Location" value={tender.location} />
            <Field icon={<Globe className="w-4 h-4" />} label="Language" value={tender.language_requirement} />
            <Field icon={<DollarSign className="w-4 h-4" />} label="Currency" value={tender.currency_for_proposal} />
            <Field icon={<Plane className="w-4 h-4" />} label="Travel required" value={tender.travel_required} />
            <Field icon={<Receipt className="w-4 h-4" />} label="Tax" value={tender.tax_inclusive_exclusive} />
            <Field icon={<Handshake className="w-4 h-4" />} label="JV / Consortium" value={tender.jv_consortium_allowed} />
            <Field icon={<Calendar className="w-4 h-4" />} label="Pre-bid meeting" value={tender.pre_bid_meeting_date} />
            <Field icon={<Calendar className="w-4 h-4" />} label="Date scouted" value={tender.date_scouted_on} />
          </div>

          {/* Long text fields */}
          <Field icon={<FileText className="w-4 h-4" />} label="Brief specification" value={tender.brief_specification} scrollable />
          <Field icon={<Building2 className="w-4 h-4" />} label="Company eligibility" value={tender.company_eligibility} scrollable />
          <Field icon={<Users className="w-4 h-4" />} label="Personnel eligibility" value={tender.personnel_eligibility} scrollable />
          <Field icon={<DollarSign className="w-4 h-4" />} label="Financial eligibility" value={tender.financial_eligibility} scrollable />

          {/* Relevance section */}
          <div className="rounded-lg border border-gray-100 bg-green-50/50 p-3">
            <div className="flex items-center gap-2 mb-2">
              <ClipboardList className="w-4 h-4 text-green-600" />
              <span className="text-xs font-medium text-gray-500">Relevance assessment</span>
              {tender.relevance && tender.relevance !== 'Info not fetched' &&
                <StatusBadge type="relevance" value={tender.relevance} />}
            </div>
            <p className="text-sm text-gray-700 leading-relaxed">
              {tender.relevance_reason ?? <span className="text-gray-300 italic text-xs">Not assessed</span>}
            </p>
          </div>

          {/* Issues section */}
          {tender.issues_faced && tender.issues_faced !== 'Info not fetched' && (
            <div className="rounded-lg border border-amber-200 bg-amber-50/50 p-3">
              <div className="flex items-center gap-2 mb-2">
                <AlertTriangle className="w-4 h-4 text-amber-500" />
                <span className="text-xs font-medium text-gray-500">Issues which might be faced</span>
              </div>
              <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-line">
                {tender.issues_faced}
              </p>
            </div>
          )}

          {/* Contact section */}
          {(tender.contact_name || tender.contact_email || tender.contact_phone) && (
            <div className="rounded-lg border border-gray-100 bg-gray-50/60 p-3">
              <p className="text-xs font-medium text-gray-500 mb-2">Contact</p>
              <div className="space-y-1.5">
                {tender.contact_name && tender.contact_name !== 'Info not fetched' && (
                  <div className="flex items-center gap-2 text-sm text-gray-700">
                    <User className="w-3.5 h-3.5 text-gray-400" />{tender.contact_name}
                  </div>
                )}
                {tender.contact_email && tender.contact_email !== 'Info not fetched' && (
                  <div className="flex items-center gap-2 text-sm">
                    <Mail className="w-3.5 h-3.5 text-gray-400" />
                    <a href={`mailto:${tender.contact_email}`} className="text-indigo-600 hover:underline">
                      {tender.contact_email}
                    </a>
                  </div>
                )}
                {tender.contact_phone && tender.contact_phone !== 'Info not fetched' && (
                  <div className="flex items-center gap-2 text-sm text-gray-700">
                    <Phone className="w-3.5 h-3.5 text-gray-400" />{tender.contact_phone}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Important links */}
          {parsedLinks.length > 0 && (
            <div className="rounded-lg border border-gray-100 bg-gray-50/60 p-3">
              <div className="flex items-center gap-2 mb-2">
                <Link2 className="w-4 h-4 text-gray-400" />
                <p className="text-xs font-medium text-gray-500">Important links</p>
              </div>
              <div className="space-y-1.5">
                {parsedLinks.map((l, i) => (
                  <a key={i} href={l.url} target="_blank" rel="noopener noreferrer"
                    className="flex items-center gap-2 text-sm text-indigo-600 hover:text-indigo-800 hover:underline">
                    <ExternalLink className="w-3 h-3 flex-shrink-0" />
                    {l.label}
                  </a>
                ))}
              </div>
            </div>
          )}

          {/* Internal metadata */}
          <div className="pt-4 border-t border-gray-100">
            <p className="text-xs text-gray-400 mb-2 font-medium uppercase tracking-wide">Internal</p>
            <div className="grid grid-cols-2 gap-2 text-xs text-gray-500">
              <span>ID: #{tender.id}</span>
              <span>Source: {tender.source_site}</span>
              <span>Added: {new Date(tender.created_at).toLocaleString()}</span>
              <span>Sheet: {tender.written_to_excel ? '✓ Written' : '○ Pending'}</span>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}

function Field({ icon, label, value, scrollable, highlight }: {
  icon: React.ReactNode; label: string; value: string | null | undefined
  scrollable?: boolean; highlight?: 'red'
}) {
  const display = value && value !== 'Info not fetched' && value !== 'null'
  return (
    <div className={`rounded-lg border p-3 ${highlight === 'red' ? 'border-red-200 bg-red-50/50' : 'border-gray-100 bg-gray-50/60'}`}>
      <div className="flex items-center gap-1.5 mb-1.5">
        <span className="text-gray-400">{icon}</span>
        <span className="text-xs font-medium text-gray-500">{label}</span>
      </div>
      <div className={`text-sm leading-relaxed ${scrollable ? 'max-h-28 overflow-y-auto scrollbar-thin' : ''} ${highlight === 'red' ? 'text-red-700 font-medium' : 'text-gray-800'}`}>
        {display ? value : <span className="text-gray-300 italic text-xs">Info not fetched</span>}
      </div>
    </div>
  )
}
