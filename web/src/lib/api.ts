/**
 * REST API helpers for FTB web server.
 */
import { gameState } from './stores'

const BASE = ''  // Same origin — proxied in dev by Vite

export async function fetchState(): Promise<any> {
  try {
    const res = await fetch(`${BASE}/api/state`)
    let data: any
    try {
      data = await res.json()
    } catch {
      // Non-JSON response (e.g. HTML error page)
      return { status: 'no_controller' }
    }
    // Normalise error / unavailable responses so callers always see a status field
    if (!res.ok && !data.status) {
      return { status: 'no_controller' }
    }
    return data
  } catch {
    // Network error / fetch failed entirely
    return { status: 'no_controller' }
  }
}

export async function fetchFullState(): Promise<any> {
  try {
    const res = await fetch(`${BASE}/api/full_state`)
    let data: any
    try {
      data = await res.json()
    } catch {
      // Non-JSON response (e.g. HTML error page)
      return { status: 'no_controller' }
    }
    if (!res.ok && !data.status) {
      return { status: 'no_controller' }
    }
    return data
  } catch {
    // Backward-compatible fallback if /api/full_state is unavailable
    return fetchState()
  }
}

function isRunningPayload(data: any): boolean {
  return Boolean(
    data &&
    data.status === 'running' &&
    (data.player_team || data.team_state)
  )
}

/**
 * Global refresh path for web UI.
 * Pulls the unified full state payload and updates the shared store only when
 * a real running state is returned.
 */
export async function globalRefresh(): Promise<any> {
  const data = await fetchFullState()
  if (isRunningPayload(data)) {
    gameState.set(data)
  }
  return data
}

/**
 * Fetch state and update the gameState store ONLY if the response contains
 * real game data.  Skips "busy" (lock contended) and error responses so that
 * the UI never gets wiped with a stub object.
 */
export async function safeRefreshState(): Promise<void> {
  await globalRefresh()
}

export async function fetchSubtitle(): Promise<string> {
  const res = await fetch(`${BASE}/api/subtitle`)
  const data = await res.json()
  return data.text || ''
}

export async function fetchSnapshot(): Promise<any> {
  const res = await fetch(`${BASE}/api/snapshot`)
  return res.json()
}

export async function sendCommand(cmd: Record<string, any>): Promise<any> {
  const res = await fetch(`${BASE}/api/command`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(cmd),
  })
  return res.json()
}

export async function sendUiCommand(action: string, payload: any = {}): Promise<any> {
  const res = await fetch(`${BASE}/api/ui_command`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action, payload }),
  })
  return res.json()
}

export async function fetchSaves(): Promise<any[]> {
  const res = await fetch(`${BASE}/api/saves`)
  const data = await res.json()
  return data.saves || []
}

export async function checkAutosave(): Promise<{ exists: boolean; path?: string; mtime?: number; size?: number }> {
  const res = await fetch(`${BASE}/api/check_autosave`)
  return res.json()
}

export async function fetchNotifications(): Promise<any[]> {
  const res = await fetch(`${BASE}/api/notifications`)
  const data = await res.json()
  return data.notifications || []
}

export async function healthCheck(): Promise<boolean> {
  try {
    const res = await fetch(`${BASE}/api/health`)
    const data = await res.json()
    return data.status === 'ok'
  } catch {
    return false
  }
}

// ─── Race Day ───
export async function fetchRaceDay(): Promise<any> {
  const res = await fetch(`${BASE}/api/race_day`)
  return res.json()
}

export async function raceDayRespond(watchLive: boolean): Promise<any> {
  const res = await fetch(`${BASE}/api/race_day/respond`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ watch_live: watchLive }),
  })
  return res.json()
}

export async function raceDayStartLive(speed: number = 10): Promise<any> {
  const res = await fetch(`${BASE}/api/race_day/start_live`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ speed }),
  })
  return res.json()
}

export async function raceDayPause(): Promise<any> {
  const res = await fetch(`${BASE}/api/race_day/pause`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ paused: true }),
  })
  return res.json()
}

export async function raceDayResume(): Promise<any> {
  const res = await fetch(`${BASE}/api/race_day/pause`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ paused: false }),
  })
  return res.json()
}

export async function raceDayComplete(): Promise<any> {
  const res = await fetch(`${BASE}/api/race_day/complete`, { method: 'POST' })
  return res.json()
}

// ─── Sponsors ───
export async function acceptSponsor(offerIndex: number): Promise<any> {
  const res = await fetch(`${BASE}/api/sponsor/accept`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ offer_index: offerIndex }),
  })
  return res.json()
}

export async function declineSponsor(offerIndex: number): Promise<any> {
  const res = await fetch(`${BASE}/api/sponsor/decline`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ offer_index: offerIndex }),
  })
  return res.json()
}

// ─── Promotion ───
export async function applyPromotion(opportunityId: string): Promise<any> {
  const res = await fetch(`${BASE}/api/promotion/apply`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ opportunity_id: opportunityId }),
  })
  return res.json()
}

export async function declinePromotion(opportunityId: string): Promise<any> {
  const res = await fetch(`${BASE}/api/promotion/decline`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ opportunity_id: opportunityId }),
  })
  return res.json()
}

// ─── Parts ───
export async function buyPart(partId: string, cost: number): Promise<any> {
  const res = await fetch(`${BASE}/api/parts/buy`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ part_id: partId, cost }),
  })
  const data = await res.json()
  if (!res.ok || data?.error) {
    throw new Error(data?.error || `Buy failed (${res.status})`)
  }
  return data
}

export async function sellPart(partId: string): Promise<any> {
  const res = await fetch(`${BASE}/api/parts/sell`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ part_id: partId }),
  })
  return res.json()
}

export async function equipPart(partId: string): Promise<any> {
  const res = await fetch(`${BASE}/api/parts/equip`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ part_id: partId }),
  })
  return res.json()
}

// ─── Staff / Job Board ───
export async function hireFreeAgent(entityName: string, freeAgentId?: number): Promise<any> {
  const res = await fetch(`${BASE}/api/staff/hire`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ entity_name: entityName, free_agent_id: freeAgentId ?? 0 }),
  })
  return res.json()
}

export async function fireStaff(entityName: string): Promise<any> {
  const res = await fetch(`${BASE}/api/staff/fire`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ entity_name: entityName }),
  })
  return res.json()
}

export async function applyForJob(listingId: number): Promise<any> {
  const res = await fetch(`${BASE}/api/staff/apply_job`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ listing_id: listingId }),
  })
  return res.json()
}

export async function submitStaffContractOffer(payload: {
  entity_id: number
  seasons_duration: number
  salary_annual: number
  signing_bonus_annual: number
  negotiation_round?: number
  role?: string
  performance_clauses?: Record<string, any>
  exit_clauses?: Record<string, any>
}): Promise<any> {
  const res = await fetch(`${BASE}/api/staff/contract/offer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return res.json()
}

export async function finalizeStaffContract(payload: {
  entity_id: number
  seasons_duration: number
  salary_annual: number
  signing_bonus_annual: number
  role?: string
  performance_clauses?: Record<string, any>
  exit_clauses?: Record<string, any>
}): Promise<any> {
  const res = await fetch(`${BASE}/api/staff/contract/finalize`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  return res.json()
}

// ─── New / Load / Save Game ───

export async function newGame(opts: {
  origin?: string
  identity?: string[]
  save_mode?: string
  tier?: string
  seed?: number
  team_name?: string
  ownership?: string
  manager_age?: number
  manager_first_name?: string
  manager_last_name?: string
}): Promise<any> {
  const res = await fetch(`${BASE}/api/new_game`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(opts),
  })
  return res.json()
}

export async function loadGame(path: string): Promise<any> {
  const res = await fetch(`${BASE}/api/load_game`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  })
  return res.json()
}

export async function saveGame(name?: string, path?: string): Promise<any> {
  const res = await fetch(`${BASE}/api/save_game`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: name || '', path: path || '' }),
  })
  return res.json()
}

export async function deleteSave(filename: string): Promise<any> {
  const res = await fetch(`${BASE}/api/saves/${encodeURIComponent(filename)}`, {
    method: 'DELETE',
  })
  return res.json()
}

// ─── UI Navigation (Audio CLI dynamic button clicking) ───

export async function navigateScreen(target: string, step?: number): Promise<any> {
  const body: Record<string, any> = { target }
  if (step !== undefined) body.step = step
  const res = await fetch(`${BASE}/api/navigate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return res.json()
}

export async function fetchUIScreen(): Promise<any> {
  try {
    const res = await fetch(`${BASE}/api/ui_screen`)
    return res.json()
  } catch {
    return { screen: 'landing', wizard_step: 1, buttons: [] }
  }
}

export async function tickStep(n: number = 1): Promise<any> {
  const res = await fetch(`${BASE}/api/tick`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ n, batch: false }),
  })
  return res.json()
}

export async function tickBatch(n: number = 7): Promise<any> {
  const res = await fetch(`${BASE}/api/tick`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ n, batch: true }),
  })
  return res.json()
}

// ─── Audio State ───
export async function fetchAudioState(): Promise<any> {
  try {
    const res = await fetch(`${BASE}/api/audio_state`)
    if (!res.ok) return null
    return res.json()
  } catch {
    return null
  }
}

// ─── R&D / Development ───
export async function fetchRDCatalog(): Promise<any[]> {
  try {
    const res = await fetch(`${BASE}/api/rd_catalog`)
    const data = await res.json()
    return data.catalog || []
  } catch {
    return []
  }
}

export async function startRDProject(projectId: string, budget: number = 0): Promise<any> {
  const res = await fetch(`${BASE}/api/rd/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ project_id: projectId, budget }),
  })
  return res.json()
}

export async function cancelRDProject(projectId: string): Promise<any> {
  const res = await fetch(`${BASE}/api/rd/cancel`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ project_id: projectId }),
  })
  return res.json()
}

// ─── Infrastructure ───
export async function upgradeInfrastructure(facility: string, amount: number = 10): Promise<any> {
  const res = await fetch(`${BASE}/api/infrastructure/upgrade`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ facility, amount }),
  })
  return res.json()
}

export async function sellInfrastructure(facility: string): Promise<any> {
  const res = await fetch(`${BASE}/api/infrastructure/sell`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ facility }),
  })
  return res.json()
}
