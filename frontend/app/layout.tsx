import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'AutoGenie',
  description: 'Create and enhance Databricks Genie Spaces',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
