/**
 * Svelte stores for FTB game state, subtitles, and notifications.
 * Updated by the WebSocket message handler in App.svelte.
 */
import { writable, derived } from 'svelte/store'

// ─── Connection ───
export const connectionState = writable<'disconnected' | 'connecting' | 'connected'>('disconnected')

// ─── Game State ───
export const gameState = writable<any>({
  status: 'no_game',
  tick: 0,
  date_str: '',
  phase: 'development',
  time_mode: 'paused',
  control_mode: 'human',
  player_team: null,
  ai_teams: [],
  leagues: {},
  free_agents: [],
  job_board: [],
  recent_events: [],
  pending_decisions: [],
  sponsorships: {},
  penalties: [],
  parts_marketplace: [],
  manager_career: {},
  delegation_settings: {},
  delegation_focus: null,
})

// ─── Subtitle ───
export const subtitle = writable<string>('')

// ─── Active Tab ───
export const activeTab = writable<string>('dashboard')

// ─── Widget updates (latest per key) ───
export const widgetUpdates = writable<Record<string, any>>({})

// ─── Notifications ───
export const notifications = writable<any[]>([])
export const unreadCount = derived(notifications, $n =>
  $n.filter(n => !n.read).length
)

// ─── Event Log ───
export const eventLog = writable<any[]>([])

// ─── Now Playing ───
export const nowPlaying = writable<any | null>(null)

// ─── Toast Messages ───
export const toasts = writable<Array<{ id: number; text: string; type: string; ts: number }>>([])
let toastId = 0
export function addToast(text: string, type: string = 'info') {
  const id = ++toastId
  toasts.update(t => [...t, { id, text, type, ts: Date.now() }])
  setTimeout(() => {
    toasts.update(t => t.filter(x => x.id !== id))
  }, 5000)
}

// ─── Derived helpers ───
export const playerTeam = derived(gameState, $s => $s.player_team)
export const budget = derived(gameState, $s => $s.player_team?.budget?.cash ?? 0)
export const tick = derived(gameState, $s => $s.tick)
export const dateStr = derived(gameState, $s => $s.date_str || '--/--')
export const phase = derived(gameState, $s => $s.phase)
export const hasGame = derived(gameState, $s => $s.status !== 'no_game')

// ─── Batch Summary ───
export const lastBatchSummary = writable<any | null>(null)
