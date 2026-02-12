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
