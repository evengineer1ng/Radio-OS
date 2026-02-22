const TEAM_KEYS = [
  'team',
  'team_name',
  'player_team',
  'player_team_name',
  'from_team',
  'to_team',
  'old_team',
  'new_team',
  'replaced_team',
  'target_team',
]

function asNumber(v: any, fallback: number = 0): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : fallback
}

function asText(v: any): string {
  if (v === null || v === undefined) return ''
  return String(v).trim()
}

function isJsonLikeText(v: string): boolean {
  const s = asText(v)
  if (!s) return false
  if ((s.startsWith('{') && s.endsWith('}')) || (s.startsWith('[') && s.endsWith(']'))) {
    try {
      JSON.parse(s)
      return true
    } catch {
      return false
    }
  }
  return false
}

function isMeaningfulText(v: any): boolean {
  const s = asText(v)
  if (!s) return false
  if (s === '[object Object]') return false
  if (isJsonLikeText(s)) return false
  return true
}

function humanizeToken(v: any, fallback: string = 'Event'): string {
  const raw = asText(v)
  if (!raw) return fallback
  return raw
    .replace(/_/g, ' ')
    .split(' ')
    .filter(Boolean)
    .map((p: string) => p[0].toUpperCase() + p.slice(1))
    .join(' ')
}

function money(v: any): string {
  const n = asNumber(v, NaN)
  if (!Number.isFinite(n)) return '$0'
  return `$${Math.round(n).toLocaleString()}`
}

function pct(v: any): string {
  const n = asNumber(v, NaN)
  if (!Number.isFinite(n)) return '0%'
  return `${n.toFixed(1)}%`
}

function mult(v: any): string {
  const n = asNumber(v, NaN)
  if (!Number.isFinite(n)) return '1.00x'
  return `${n.toFixed(2)}x`
}

function teamRefsFromStandings(standings: any): string[] {
  if (!Array.isArray(standings)) return []
  const out: string[] = []
  for (const row of standings) {
    if (Array.isArray(row) && row.length > 0) {
      const team = asText(row[0])
      if (team) out.push(team)
      continue
    }
    if (row && typeof row === 'object') {
      const team = asText((row as any).team || (row as any).team_name || (row as any).name)
      if (team) out.push(team)
    }
  }
  return out
}

export function extractEventTeams(evt: any): string[] {
  const data = evt?.data || {}
  const refs: string[] = []

  for (const key of TEAM_KEYS) {
    const val = asText(data?.[key])
    if (val) refs.push(val)
  }

  refs.push(...teamRefsFromStandings(data?.standings))
  return refs
}

export function isPlayerTeamEvent(evt: any, playerTeamName: string): boolean {
  const target = asText(playerTeamName).toLowerCase()
  if (!target) return false
  return extractEventTeams(evt).some((team: string) => asText(team).toLowerCase() === target)
}

export function formatEventSummary(evt: any): string {
  if (typeof evt === 'string') {
    const plain = asText(evt)
    return plain || 'Event'
  }

  const data = evt?.data || {}
  const category = asText(evt?.category).toLowerCase()

  const textCandidates = [
    evt?.description,
    evt?.text,
    data?.message,
    data?.description,
  ]
  for (const candidate of textCandidates) {
    if (isMeaningfulText(candidate)) return asText(candidate)
  }

  if (category === 'race_result') {
    const driver = asText(data?.driver) || 'Unknown driver'
    const team = asText(data?.team) || asText(data?.team_name) || 'Unknown team'
    const pos = asNumber(data?.position, 0)
    const pts = asNumber(data?.points, 0)
    const track = asText(data?.track_name)
    const status = asText(data?.status) || 'finished'
    const trackChunk = track ? ` at ${track}` : ''
    return `${driver} (${team}) finished P${pos > 0 ? pos : '—'}${trackChunk} (${pts} pts, ${status})`
  }

  if (category === 'sponsor_payment') {
    const sponsor = asText(data?.sponsor_name) || 'Sponsor'
    const team = asText(data?.team) || asText(data?.team_name)
    const amount = money(data?.amount)
    const base = data?.base_amount !== undefined ? money(data?.base_amount) : ''
    const confidence = data?.confidence !== undefined ? pct(data?.confidence) : ''
    const multiplier = data?.multiplier !== undefined ? mult(data?.multiplier) : ''
    const teamChunk = team ? ` for ${team}` : ''
    const detail = [base ? `base ${base}` : '', multiplier, confidence].filter(Boolean).join(', ')
    return `${sponsor} payment${teamChunk}: ${amount}${detail ? ` (${detail})` : ''}`
  }

  if (category === 'staff_change') {
    const who = asText(data?.entity) || asText(data?.entity_name) || 'Staff'
    const role = asText(data?.type) || 'staff'
    const action = asText(data?.action) || 'updated'
    const team = asText(data?.team) || asText(data?.team_name) || 'team'
    return `${role} ${who} was ${action} by ${team}`
  }

  if (category === 'team_fold') {
    const team = asText(data?.team) || 'Team'
    const reason = asText(data?.fold_reason) || 'financial collapse'
    return `${team} folded (${reason})`
  }

  if (category === 'team_spawned') {
    const team = asText(data?.team_name) || 'New team'
    const tier = asNumber(data?.tier, 0)
    const replaced = asText(data?.replaced_team)
    const tierLabel = tier > 0 ? `Tier ${tier}` : 'new tier'
    const replacedChunk = replaced ? ` replacing ${replaced}` : ''
    return `${team} entered ${tierLabel}${replacedChunk}`
  }

  const fallbackFields: string[] = []
  const simpleKeys = [
    'team', 'driver', 'entity', 'sponsor_name', 'track_name',
    'position', 'points', 'amount', 'status', 'league_name',
  ]
  for (const key of simpleKeys) {
    if (data?.[key] === undefined || data?.[key] === null || data?.[key] === '') continue
    const label = key.replace(/_/g, ' ')
    const value = key === 'amount' ? money(data[key]) : asText(data[key])
    fallbackFields.push(`${label}: ${value}`)
  }

  const label = humanizeToken(evt?.category || evt?.type, 'Event')
  if (fallbackFields.length > 0) {
    return `${label} • ${fallbackFields.join(' • ')}`
  }
  return label
}
