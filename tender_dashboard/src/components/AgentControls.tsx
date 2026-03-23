'use client'

import { useState, useEffect, useRef } from 'react'
import { checkHealth, triggerRun } from '@/lib/api'
import { Play, Power, Loader2 } from 'lucide-react'

interface Props { onRunComplete: () => void }

export default function AgentControls({ onRunComplete }: Props) {
  const [online, setOnline]     = useState<boolean | null>(null)
  const [running, setRunning]   = useState(false)
  const [starting, setStarting] = useState(false)
  const [msg, setMsg]           = useState('')
  const pollRef                 = useRef<ReturnType<typeof setInterval> | null>(null)

  // Track consecutive failures before flipping to offline
  // WHY: During scraping, FastAPI may miss 1-2 health checks.
  // We only show "offline" after 3 consecutive failures — not on the first miss.
  const failCount = useRef(0)
  const MAX_FAILS = 3

  useEffect(() => {
    const check = async () => {
      const healthy = await checkHealth()
      if (healthy) {
        failCount.current = 0
        setOnline(true)
      } else {
        failCount.current += 1
        // Only flip to offline after MAX_FAILS consecutive failures
        if (failCount.current >= MAX_FAILS) {
          setOnline(false)
        }
        // Between 1-2 failures: keep showing online (agent is just busy scraping)
      }
    }
    check()
    const i = setInterval(check, 10_000)
    return () => clearInterval(i)
  }, [])

  const startFastPoll = () => {
    if (pollRef.current) clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      const healthy = await checkHealth()
      if (healthy) {
        failCount.current = 0
        setOnline(true)
        setStarting(false)
        setMsg('Agent is online!')
        setTimeout(() => setMsg(''), 3000)
        if (pollRef.current) clearInterval(pollRef.current)
      }
    }, 2000)
  }

  const handleStart = async () => {
    setStarting(true)
    setMsg('Starting agent...')
    try {
      const res  = await fetch('/api/start-agent', { method: 'POST' })
      const data = await res.json()
      if (!res.ok) {
        setMsg(data.error || 'Failed to start')
        setStarting(false)
        return
      }
      setMsg('Starting — connecting...')
      startFastPoll()
    } catch {
      setMsg('Could not start agent')
      setStarting(false)
    }
  }

  const handleRun = async () => {
    if (running || !online) return
    setRunning(true)
    setMsg('Scraping started...')
    try {
      await triggerRun()
      setMsg('Running in background — results appear soon')
      setTimeout(() => { onRunComplete(); setRunning(false); setMsg('') }, 8000)
    } catch {
      setMsg('Failed to trigger run')
      setRunning(false)
    }
  }

  // Determine display state
  // "scraping" = online but was briefly unresponsive (1-2 failed checks)
  const isScraping = online === true && failCount.current > 0 && failCount.current < MAX_FAILS

  return (
    <div className="flex items-center gap-3">

      {/* Status indicator */}
      <div className="flex items-center gap-2">
        {online === null || starting ? (
          <Loader2 className="w-3 h-3 text-gray-400 animate-spin" />
        ) : online ? (
          <>
            <span className={`w-2 h-2 rounded-full ${isScraping ? 'bg-amber-400' : 'bg-green-500'} animate-pulse`} />
            <span className={`text-xs font-medium hidden sm:inline ${isScraping ? 'text-amber-600' : 'text-green-700'}`}>
              {isScraping ? 'Scraping...' : 'Online'}
            </span>
          </>
        ) : (
          <>
            <span className="w-2 h-2 rounded-full bg-red-500" />
            <span className="text-red-600 text-xs font-medium hidden sm:inline">Offline</span>
          </>
        )}
      </div>

      {/* Message */}
      {msg && (
        <span className="text-xs text-indigo-600 max-w-52 truncate hidden sm:inline">{msg}</span>
      )}

      {/* Start Agent — when offline */}
      {!online && !starting && (
        <button onClick={handleStart}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium border bg-green-600 text-white border-green-600 hover:bg-green-700 transition-all">
          <Power className="w-3.5 h-3.5" />
          Start Agent
        </button>
      )}

      {/* Starting spinner */}
      {starting && (
        <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium border bg-gray-100 text-gray-500 border-gray-200">
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
          Starting...
        </div>
      )}

      {/* Run now — when online */}
      {online && !starting && (
        <button onClick={handleRun} disabled={running}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium border transition-all
            ${running
              ? 'bg-gray-100 text-gray-400 border-gray-200 cursor-not-allowed'
              : 'bg-indigo-600 text-white border-indigo-600 hover:bg-indigo-700'}`}>
          <Play className={`w-3.5 h-3.5 ${running ? 'animate-pulse' : ''}`} />
          {running ? 'Running...' : 'Run now'}
        </button>
      )}
    </div>
  )
}
