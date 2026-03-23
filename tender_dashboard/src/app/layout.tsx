// src/app/layout.tsx
// ─────────────────────────────────────────────────────────────────────────────
// KEY CONCEPT — Next.js App Router layout:
// In Next.js 14, layout.tsx is the "wrapper" for every page.
// Whatever you put here renders on EVERY page — nav, sidebar, etc.
// The {children} prop is where the actual page content appears.
//
// This layout gives us:
// - Top navigation bar with agent status indicator
// - Main content area with padding
// - Dark/light consistent background
// ─────────────────────────────────────────────────────────────────────────────

import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Tender Agent Dashboard',
  description: 'Automated tender discovery and tracking',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className="bg-gray-50 text-gray-900 min-h-screen">
        {children}
      </body>
    </html>
  )
}
