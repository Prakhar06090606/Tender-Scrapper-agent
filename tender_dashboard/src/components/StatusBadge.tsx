// src/components/StatusBadge.tsx
'use client'
import { clsx } from 'clsx'

type Props = {
  type: 'status' | 'category' | 'source' | 'relevance'
  value: string
}

const STATUS_COLORS: Record<string, string> = {
  pending:       'bg-amber-100 text-amber-800 border-amber-200',
  approved:      'bg-green-100 text-green-800 border-green-200',
  rejected:      'bg-red-100 text-red-800 border-red-200',
  reconsidering: 'bg-blue-100 text-blue-800 border-blue-200',
}
const CATEGORY_COLORS: Record<string, string> = {
  'Consulting':          'bg-indigo-100 text-indigo-800 border-indigo-200',
  'IT':                  'bg-purple-100 text-purple-800 border-purple-200',
  'Medical Oxygen':      'bg-sky-100 text-sky-800 border-sky-200',
  'Training and Skill':  'bg-teal-100 text-teal-800 border-teal-200',
}
const SOURCE_COLORS: Record<string, string> = {
  'UNGM':    'bg-blue-50 text-blue-700 border-blue-200',
  'GeM':     'bg-orange-50 text-orange-700 border-orange-200',
  'eProcure':'bg-green-50 text-green-700 border-green-200',
  'DefProc': 'bg-red-50 text-red-700 border-red-200',
  'Google':  'bg-gray-50 text-gray-700 border-gray-200',
}
const RELEVANCE_COLORS: Record<string, string> = {
  'Relevant':     'bg-green-100 text-green-800 border-green-300',
  'Not relevant': 'bg-red-100 text-red-700 border-red-200',
}

export default function StatusBadge({ type, value }: Props) {
  let color = 'bg-gray-100 text-gray-600 border-gray-200'
  if (type === 'status')    color = STATUS_COLORS[value]    ?? color
  if (type === 'category')  color = CATEGORY_COLORS[value]  ?? color
  if (type === 'source')    color = SOURCE_COLORS[value]     ?? color
  if (type === 'relevance') color = RELEVANCE_COLORS[value]  ?? color
  return (
    <span className={clsx('inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border', color)}>
      {value}
    </span>
  )
}
