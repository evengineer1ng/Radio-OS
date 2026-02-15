/**
 * Browser-side audio engine for FTB.
 *
 * Mirrors the server-side ftb_audio_engine by playing the same OGG files
 * served via /audio/ from the FTB web server.  Audio events arrive either
 * through WebSocket messages (type "audio_event") or by polling /api/audio_state.
 *
 * Uses HTML5 Audio elements for simplicity and broad compatibility.
 */

// ─── Types ────────────────────────────────────────────────────────────────

interface AudioChannel {
  el: HTMLAudioElement
  baseVolume: number
  currentVolume: number
  fadeTo?: { target: number; step: number; timer: number }
}

type MusicVariant = 'minor' | 'neutral' | 'major'

// ─── State ────────────────────────────────────────────────────────────────

let ctx: AudioContext | null = null // created on first user interaction
let musicChannel: AudioChannel | null = null
let engineChannel: AudioChannel | null = null
let ambientChannels: Map<string, AudioChannel> = new Map()

let currentVariant: MusicVariant = 'neutral'
let isDucking = false
let isPbpMuted = false
let engineLeague: string | null = null
let started = false
let userInteracted = false  // true after first user tap/click

const MUSIC_VOLUME = 0.10
const MUSIC_DUCK_VOLUME = 0.02
const ENGINE_VOLUME = 0.12
const CRASH_VOLUME = 0.30
const CROWD_VOLUME = 0.25
const AMBIENT_VOLUME = 0.08

// ─── Helpers ──────────────────────────────────────────────────────────────

function audioUrl(path: string): string {
  return `/audio/${path}`
}

function makeChannel(src: string, volume: number, loop: boolean = false): AudioChannel {
  const el = new Audio(src)
  el.loop = loop
  el.volume = volume
  el.preload = 'auto'
  const ch: AudioChannel = { el, baseVolume: volume, currentVolume: volume }
  return ch
}

function fadeChannel(ch: AudioChannel, target: number, durationMs: number = 2000) {
  if (ch.fadeTo?.timer) clearInterval(ch.fadeTo.timer)
  const steps = 40
  const stepMs = durationMs / steps
  const delta = (target - ch.currentVolume) / steps
  let i = 0
  ch.fadeTo = {
    target,
    step: delta,
    timer: window.setInterval(() => {
      i++
      ch.currentVolume = Math.max(0, Math.min(1, ch.currentVolume + delta))
      ch.el.volume = ch.currentVolume
      if (i >= steps) {
        ch.currentVolume = target
        ch.el.volume = target
        if (ch.fadeTo?.timer) clearInterval(ch.fadeTo.timer)
        ch.fadeTo = undefined
        // Stop playback if faded to 0
        if (target === 0) ch.el.pause()
      }
    }, stepMs) as unknown as number,
  }
}

function stopChannel(ch: AudioChannel | null) {
  if (!ch) return
  if (ch.fadeTo?.timer) clearInterval(ch.fadeTo.timer)
  ch.el.pause()
  ch.el.currentTime = 0
}

// ─── Public API ───────────────────────────────────────────────────────────

/**
 * Must be called from a user-interaction event handler (click/tap)
 * to satisfy browser autoplay policies.
 */
export function ensureUserInteraction() {
  if (userInteracted) return
  userInteracted = true
  // Create AudioContext to "unlock" audio on iOS/Safari
  try {
    ctx = new (window.AudioContext || (window as any).webkitAudioContext)()
    if (ctx.state === 'suspended') ctx.resume()
  } catch { /* ok */ }
}

/** Start background music with the current variant. */
export function startMusic(variant?: MusicVariant) {
  if (!userInteracted) return
  if (variant) currentVariant = variant
  const src = audioUrl(`music/theme_${currentVariant}.ogg`)

  if (musicChannel) {
    // If already playing same variant, skip
    if (musicChannel.el.src.endsWith(`theme_${currentVariant}.ogg`) && !musicChannel.el.paused) {
      return
    }
    stopChannel(musicChannel)
  }

  const vol = isPbpMuted ? 0 : (isDucking ? MUSIC_DUCK_VOLUME : MUSIC_VOLUME)
  musicChannel = makeChannel(src, vol, true)
  musicChannel.el.play().catch(() => { /* autoplay blocked */ })
  started = true
}

/** Crossfade to a new music variant. */
export function setMusicVariant(v: MusicVariant) {
  if (v === currentVariant && musicChannel && !musicChannel.el.paused) return
  currentVariant = v
  if (started) startMusic(v)
}

/** Duck music for narrator speech. */
export function setDucking(duck: boolean) {
  isDucking = duck
  if (!musicChannel || isPbpMuted) return
  const target = duck ? MUSIC_DUCK_VOLUME : MUSIC_VOLUME
  fadeChannel(musicChannel, target, 1500)
}

/** Mute/unmute music for play-by-play mode. */
export function setPbpMute(muted: boolean) {
  isPbpMuted = muted
  if (!musicChannel) return
  const target = muted ? 0 : (isDucking ? MUSIC_DUCK_VOLUME : MUSIC_VOLUME)
  fadeChannel(musicChannel, target, 2000)
}

/** Start engine loop for a league tier. */
export function startEngine(leagueTier: string) {
  if (!userInteracted) return
  if (engineLeague === leagueTier && engineChannel && !engineChannel.el.paused) return
  engineLeague = leagueTier

  if (engineChannel) stopChannel(engineChannel)

  // Pick a deterministic engine file — the server picks random ones but we
  // just use the directory.  For now request the tier directory index isn't
  // available, so we try a known pattern.  If files are named differently the
  // request simply 404s silently.
  const src = audioUrl(`world/engines/${leagueTier}/engine.ogg`)
  engineChannel = makeChannel(src, ENGINE_VOLUME, true)
  engineChannel.el.play().catch(() => {})
}

/** Stop engine loop. */
export function stopEngine() {
  if (engineChannel) {
    fadeChannel(engineChannel, 0, 1000)
    engineLeague = null
  }
}

/** Play a one-shot crash sound. */
export function playCrash(severity: number) {
  if (!userInteracted) return
  let type = 'light'
  if (severity > 0.7) type = 'hard'
  else if (severity > 0.3) type = 'medium'
  const src = audioUrl(`world/crashes/${type}.ogg`)
  const el = new Audio(src)
  el.volume = CRASH_VOLUME * Math.min(1, 0.5 + severity)
  el.play().catch(() => {})
}

/** Play a one-shot crowd reaction. */
export function playCrowd(reaction: string = 'cheer') {
  if (!userInteracted) return
  const map: Record<string, string> = {
    cheer: 'crowdcheer_oneshot.ogg',
    chatter: 'crowdchatter_oneshot.ogg',
    whoop: 'crowdwhoop.ogg',
  }
  const file = map[reaction] || map.cheer
  const src = audioUrl(`world/ambient/${file}`)
  const el = new Audio(src)
  el.volume = CROWD_VOLUME
  el.play().catch(() => {})
}

/** Stop everything. */
export function stopAll() {
  stopChannel(musicChannel)
  musicChannel = null
  stopChannel(engineChannel)
  engineChannel = null
  ambientChannels.forEach(ch => stopChannel(ch))
  ambientChannels.clear()
  started = false
  engineLeague = null
}

// ─── WebSocket / polling handler ──────────────────────────────────────────

/**
 * Handle an audio_event message from the WebSocket.
 * Called by the WS message router in App.svelte.
 */
export function handleAudioEvent(data: any) {
  if (!data) return
  const type = data.audio_type

  if (type === 'narrator_duck') {
    setDucking(!!data.ducking)
  } else if (type === 'pbp_mode') {
    setPbpMute(!!data.muted)
  } else if (type === 'world') {
    const action = data.action
    if (action === 'engine_start') startEngine(data.league_tier || 'midformula')
    else if (action === 'engine_stop') stopEngine()
    else if (action === 'crash') playCrash(data.metadata?.severity ?? 0.5)
    else if (action === 'crowd_reaction') playCrowd(data.metadata?.reaction_type || 'cheer')
  } else if (type === 'performance_update') {
    if (data.variant) setMusicVariant(data.variant)
  }
}

/**
 * Poll-based sync: call periodically with the result of /api/audio_state.
 */
export function syncFromState(state: any) {
  if (!state || !userInteracted) return
  // Music variant
  if (state.music_variant && state.music_variant !== currentVariant) {
    setMusicVariant(state.music_variant)
  }
  // Ducking
  if (state.music_ducking !== isDucking) setDucking(state.music_ducking)
  // PBP mute
  if (state.music_pbp_muted !== isPbpMuted) setPbpMute(state.music_pbp_muted)
  // Engine
  if (state.engine_league && state.engine_league !== engineLeague) {
    startEngine(state.engine_league)
  } else if (!state.engine_league && engineLeague) {
    stopEngine()
  }
}

export function isStarted(): boolean {
  return started
}

export function hasUserInteracted(): boolean {
  return userInteracted
}
