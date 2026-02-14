/**
 * REST API helpers for FTB web server.
 */

const BASE = ''  // Same origin — proxied in dev by Vite

export async function fetchState(): Promise<any> {
  const res = await fetch(`${BASE}/api/state`)
  return res.json()
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
  const res = await fetch(`${BASE}/api/race_day/pause`, { method: 'POST' })
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

// ─── Parts ───
export async function buyPart(partId: string, cost: number): Promise<any> {
  const res = await fetch(`${BASE}/api/parts/buy`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ part_id: partId, cost }),
  })
  return res.json()
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

export async function saveGame(path?: string): Promise<any> {
  const res = await fetch(`${BASE}/api/save_game`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path: path || '' }),
  })
  return res.json()
}

export async function deleteSave(filename: string): Promise<any> {
  const res = await fetch(`${BASE}/api/saves/${encodeURIComponent(filename)}`, {
    method: 'DELETE',
  })
  return res.json()
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
