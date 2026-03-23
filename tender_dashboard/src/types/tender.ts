// src/types/tender.ts
// Mirrors the Python Tender model exactly — 26 sheet columns + internal fields

export interface Tender {
  id: number
  category: 'Consulting' | 'IT' | 'Medical Oxygen' | 'Training and Skill'
  source_site: string

  // Sheet columns 1-19
  agency: string | null
  tender_title: string | null
  link: string | null
  area: string | null
  submission_deadline_date: string | null
  submission_deadline_time: string | null
  date_scouted_on: string | null
  company_eligibility: string | null
  personnel_eligibility: string | null
  language_requirement: string | null
  financial_eligibility: string | null
  currency_for_proposal: string | null
  pre_bid_meeting_date: string | null
  location: string | null
  travel_required: string | null
  tax_inclusive_exclusive: string | null
  jv_consortium_allowed: string | null
  brief_specification: string | null

  // Sheet columns 20-26 (new fields)
  relevance: 'Relevant' | 'Not relevant' | 'Info not fetched' | null
  relevance_reason: string | null
  issues_faced: string | null
  contact_name: string | null
  contact_email: string | null
  contact_phone: string | null
  important_links: string | null

  // Internal tracking
  status: 'pending' | 'approved' | 'rejected' | 'reconsidering'
  written_to_excel: boolean
  created_at: string
}

export interface TendersResponse {
  total: number
  offset: number
  limit: number
  tenders: Tender[]
}

export interface Stats {
  total_tenders: number
  by_category: Record<string, number>
  by_status: Record<string, number>
  written_to_excel: number
  pending_excel_write: number
}

export interface TenderFilters {
  category: string
  status: string
  source: string
  relevance: string
  search: string
}
