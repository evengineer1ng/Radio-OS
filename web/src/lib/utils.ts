/** Utility helpers */

export function formatCurrency(amount: number): string {
  if (amount >= 1_000_000) return `$${(amount / 1_000_000).toFixed(1)}M`
  if (amount >= 1_000) return `$${(amount / 1_000).toFixed(0)}K`
  return `$${Math.round(amount)}`
}

export function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`
}

export function formatStat(value: number, max: number = 100): string {
  return `${Math.round(value)}/${max}`
}

export function statColor(value: number, max: number = 100): string {
  const pct = value / max
  if (pct >= 0.8) return 'var(--c-success)'
  if (pct >= 0.5) return 'var(--c-warning)'
  return 'var(--c-danger)'
}

export function truncate(s: string, len: number = 60): string {
  return s.length > len ? s.slice(0, len) + '…' : s
}

export function timeAgo(ts: number): string {
  const diff = (Date.now() / 1000) - ts
  if (diff < 60) return 'just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}
