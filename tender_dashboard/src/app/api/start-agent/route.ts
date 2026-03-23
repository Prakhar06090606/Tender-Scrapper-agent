import { NextResponse } from 'next/server'
import { spawn, execSync } from 'child_process'
import path from 'path'
import fs from 'fs'

const AGENT_PATH = process.env.AGENT_PATH ||
  path.join(process.cwd(), '..', 'tender_agent')

let agentPid: number | null = null

export async function POST() {
  try {
    // Already running?
    try {
      const check = await fetch('http://localhost:8000/', {
        signal: AbortSignal.timeout(2000)
      })
      if (check.ok) {
        return NextResponse.json({ message: 'Agent already running', pid: agentPid })
      }
    } catch {}

    if (!fs.existsSync(AGENT_PATH)) {
      return NextResponse.json(
        { error: `Agent folder not found: ${AGENT_PATH}\nSet AGENT_PATH in .env.local` },
        { status: 500 }
      )
    }

    const logPath = path.join(AGENT_PATH, 'agent.log')

    // Write a launcher batch file — avoids all path-with-spaces issues
    // The batch file handles venv activation + running python correctly
    const batContent = [
      '@echo off',
      `cd /d "${AGENT_PATH}"`,
      `call "${path.join(AGENT_PATH, 'venv', 'Scripts', 'activate.bat')}"`,
      `py run.py >> "${logPath}" 2>&1`,
    ].join('\r\n')

    const batPath = path.join(AGENT_PATH, '_start_agent.bat')
    fs.writeFileSync(batPath, batContent)
    fs.writeFileSync(logPath, `=== Agent starting at ${new Date().toISOString()} ===\n`)

    console.log(`🚀 Starting agent: ${AGENT_PATH}`)
    console.log(`📝 Logging to: ${logPath}`)

    // Use cmd.exe to run the batch file — most reliable on Windows
    const child = spawn('cmd.exe', ['/c', batPath], {
      detached: true,
      stdio: 'ignore',   // batch file handles its own output to log
      windowsHide: false,
      shell: false,
    })

    child.on('error', (err) => {
      console.error('Spawn error:', err)
      fs.appendFileSync(logPath, `SPAWN ERROR: ${err.message}\n`)
    })

    agentPid = child.pid ?? null
    child.unref()

    console.log(`✅ Agent launched via batch, PID: ${agentPid}`)

    return NextResponse.json({
      message: 'Agent starting — check agent.log if it stays offline',
      pid: agentPid,
      logFile: logPath,
    })

  } catch (error) {
    return NextResponse.json({ error: `Failed to start: ${error}` }, { status: 500 })
  }
}

export async function GET() {
  try {
    const check = await fetch('http://localhost:8000/', {
      signal: AbortSignal.timeout(2000)
    })
    if (check.ok) return NextResponse.json({ running: true, pid: agentPid })
  } catch {}
  return NextResponse.json({ running: false, pid: null })
}
