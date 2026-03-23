// src/lib/api.ts — all backend calls in one place

import axios from 'axios'
import type { Tender, TendersResponse, Stats, TenderFilters } from '@/types/tender'

const client = axios.create({ baseURL: '/api', timeout: 15000 })

export async function fetchTenders(
  filters: Partial<TenderFilters> = {},
  page = 0,
  limit = 50
): Promise<TendersResponse> {
  const params: Record<string, string | number> = { offset: page * limit, limit }
  if (filters.category) params.category = filters.category
  if (filters.status)   params.status   = filters.status
  if (filters.source)   params.source   = filters.source
  if (filters.relevance) params.relevance = filters.relevance
  const { data } = await client.get<TendersResponse>('/tenders', { params })
  return data
}

export async function fetchTender(id: number): Promise<Tender> {
  const { data } = await client.get<Tender>(`/tenders/${id}`)
  return data
}

export async function updateStatus(id: number, status: string): Promise<void> {
  await client.patch(`/tenders/${id}/status`, null, { params: { status } })
}

export async function fetchStats(): Promise<Stats> {
  const { data } = await client.get<Stats>('/stats')
  return data
}

export async function triggerRun(): Promise<{ message: string }> {
  const { data } = await client.post('/run-now')
  return data
}

export async function checkHealth(): Promise<boolean> {
  try {
    await client.get('/', { timeout: 3000 })
    return true
  } catch { return false }
}
