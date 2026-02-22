<script lang="ts">
  import { onMount, onDestroy } from 'svelte'
  import { fetchState, fetchSaves, loadGame, fetchAudioState, checkAutosave } from './lib/api'
  import {
    gameState, subtitle, notifications, nowPlaying,
    connectionState, activeTab, eventLog, hasGame,
    addToast, lastBatchSummary, widgetUpdates
  } from './lib/stores'
  import * as webAudio from './lib/webAudio'
  import { onMessage } from './lib/ws'

  // Components
  import Toolbar from './components/Toolbar.svelte'
  import Toast from './components/Toast.svelte'
  import Modal from './components/Modal.svelte'
  import SetupWizard from './components/SetupWizard.svelte'
  import NotificationCenter from './components/NotificationCenter.svelte'

  // Tabs
  import Dashboard from './tabs/Dashboard.svelte'
  import Team from './tabs/Team.svelte'
  import AIAssistant from './tabs/AIAssistant.svelte'
  import ManagerCareer from './tabs/ManagerCareer.svelte'
  import Car from './tabs/Car.svelte'
  import Development from './tabs/Development.svelte'
  import Finance from './tabs/Finance.svelte'
  import RaceOps from './tabs/RaceOps.svelte'
  import RacingStats from './tabs/RacingStats.svelte'
  import Analytics from './tabs/Analytics.svelte'
  import Sponsors from './tabs/Sponsors.svelte'
  import Promotion from './tabs/Promotion.svelte'
  import Penalties from './tabs/Penalties.svelte'
  import History from './tabs/History.svelte'
  import Help from './tabs/Help.svelte'
  import PlayByPlay from './tabs/PlayByPlay.svelte'
  import Calendar from './tabs/Calendar.svelte'
  import FTBData from './tabs/FTBData.svelte'

  const tabs = [
    { id: 'dashboard',  label: '🏠', name: 'Home' },
    { id: 'team',       label: '👥', name: 'Team' },
    { id: 'car',        label: '🏎️', name: 'Car' },
    { id: 'development',label: '🔧', name: 'Dev' },
    { id: 'raceops',    label: '🏁', name: 'Race' },
    { id: 'pbp',        label: '📡', name: 'PBP' },
    { id: 'finance',    label: '💰', name: 'Finance' },
    { id: 'sponsors',   label: '🤝', name: 'Sponsors' },
    { id: 'promotion',  label: '📈', name: 'Promotion' },
    { id: 'stats',      label: '📊', name: 'Stats' },
    { id: 'analytics',  label: '📈', name: 'Analytics' },
    { id: 'career',     label: '🏆', name: 'Career' },
    { id: 'calendar',   label: '📅', name: 'Calendar' },
    { id: 'ai',         label: '🤖', name: 'AI' },
    { id: 'penalties',  label: '⚠️', name: 'Penalties' },
    { id: 'history',    label: '📜', name: 'History' },
    { id: 'help',       label: '❓', name: 'Help' },
    { id: 'data',       label: '🗄️', name: 'Data' },
  ]

  let showNotifs = false
  let showSetupWizard = false
  let showLoadScreen = false
  let saves: any[] = []
  let loadingList = false
  let loadingSave = false
  let pendingGameLoad = false  // true while waiting for backend to create/load game
  let autoLoadAttempted = false  // true once we've checked for autosave

  type RaceResultRow = {
    driver: string
    position: number
    points: number
    status: string
    prizeMoney: number
  }

  type RaceResultPopup = {
    key: string
    tick: number
    season: number
    round: number
    track: string
    league: string
    team: string
    rows: RaceResultRow[]
    totalPoints: number
    totalPrizeMoney: number
  }

  type DriverRecentResult = {
    driver: string
    tick: number
    season: number
    round: number
    position: number
    points: number
    status: string
    trackName: string
  }

  type ScheduleEntry = {
    tick: number
    trackId: string
    trackName: string
    completed: boolean
  }

  let raceResultSeenKeys = new Set<string>()
  let raceResultQueue: RaceResultPopup[] = []
  let activeRaceResult: RaceResultPopup | null = null
  let showRaceResultPopup = false
  let raceTrackingGameKey = ''
  let raceTrackingLastTick = -1
  let raceBaselineInitialized = false

  function toInt(value: any, fallback: number = 0): number {
    const n = Number(value)
    return Number.isFinite(n) ? Math.trunc(n) : fallback
  }

  function getRaceEventTeam(evt: any): string {
    const data = evt?.data || {}
    return String(data?.team || data?.team_name || data?.player_team_name || '')
  }

  function raceEventKey(evt: any, teamName: string): string {
    const data = evt?.data || {}
    const tickVal = toInt(evt?.tick ?? evt?.ts ?? 0)
    const seasonVal = toInt(data?.season ?? 0)
    const leagueId = String(data?.league_id || data?.league_name || '')
    const roundVal = toInt(data?.round_number || data?.round || 0)
    const track = String(data?.track_name || '')
    const team = getRaceEventTeam(evt) || teamName
    return `${seasonVal}|${tickVal}|${leagueId}|${roundVal}|${track}|${team}`
  }

  function isFinishedStatus(status: string): boolean {
    const normalized = String(status || '').trim().toLowerCase()
    return !normalized || normalized === 'finished'
  }

  function formatResultStatus(status: string): string {
    const raw = String(status || '').trim()
    if (!raw || raw.toLowerCase() === 'finished') return ''
    return raw.replace(/_/g, ' ').toUpperCase()
  }

  function formatLastRaceMeta(result: DriverRecentResult | null): string {
    if (!result) return ''
    const seasonRound = `${result.season > 0 ? `S${result.season}` : ''}${result.round > 0 ? ` R${result.round}` : ''}`.trim()
    if (seasonRound && result.trackName) return `${seasonRound} • ${result.trackName}`
    if (result.trackName) return result.trackName
    if (seasonRound) return seasonRound
    if (result.tick > 0) return `Tick ${result.tick}`
    return ''
  }

  function normalizeScheduleEntry(entry: any, index: number, racesDone: number, tracks: Record<string, any>): ScheduleEntry | null {
    const completedByIndex = index < racesDone

    if (entry && typeof entry === 'object' && !Array.isArray(entry)) {
      const tick = toInt(entry?.tick ?? entry?.race_tick ?? 0)
      const trackId = String(entry?.track_id || '')
      const trackName = String(entry?.track_name || (trackId && tracks?.[trackId]?.name) || '')
      const completed = Boolean(entry?.completed ?? completedByIndex)
      if (tick <= 0 && !trackId && !trackName) return null
      return { tick, trackId, trackName, completed }
    }

    if (Array.isArray(entry)) {
      const tick = toInt(entry[0] ?? 0)
      const trackId = String(entry[1] || '')
      const trackName = String((trackId && tracks?.[trackId]?.name) || '')
      if (tick <= 0 && !trackId && !trackName) return null
      return { tick, trackId, trackName, completed: completedByIndex }
    }

    if (typeof entry === 'number') {
      const tick = toInt(entry)
      if (tick <= 0) return null
      return { tick, trackId: '', trackName: '', completed: completedByIndex }
    }

    return null
  }

  function formatDaysUntilRace(days: number | null): string {
    if (days === null) return ''
    if (days <= 0) return 'Race Day'
    return `${days} day${days === 1 ? '' : 's'} until next race`
  }

  function resetRaceResultTracking() {
    raceResultSeenKeys = new Set<string>()
    raceResultQueue = []
    activeRaceResult = null
    showRaceResultPopup = false
    raceBaselineInitialized = false
    raceTrackingLastTick = -1
  }

  function seedRaceResultBaseline(gs: any) {
    const teamName = String(gs?.player_team?.name || '')
    const events = Array.isArray(gs?.recent_events) ? gs.recent_events : []
    for (const evt of events) {
      const category = String(evt?.category || '').toLowerCase()
      if (category !== 'race_result') continue
      if (getRaceEventTeam(evt) !== teamName) continue
      raceResultSeenKeys.add(raceEventKey(evt, teamName))
    }
  }

  function openNextRaceResultPopup() {
    if (raceResultQueue.length <= 0) {
      activeRaceResult = null
      showRaceResultPopup = false
      return
    }
    activeRaceResult = raceResultQueue[0]
    raceResultQueue = raceResultQueue.slice(1)
    showRaceResultPopup = true
  }

  function acknowledgeRaceResultPopup() {
    if (raceResultQueue.length > 0) {
      openNextRaceResultPopup()
      return
    }
    activeRaceResult = null
    showRaceResultPopup = false
  }

  function queueNewRaceResultPopups(gs: any) {
    const teamName = String(gs?.player_team?.name || '')
    const events = Array.isArray(gs?.recent_events) ? gs.recent_events : []
    if (!teamName || events.length === 0) return

    const grouped = new Map<string, RaceResultPopup>()
    for (const evt of events) {
      const category = String(evt?.category || '').toLowerCase()
      if (category !== 'race_result') continue
      if (getRaceEventTeam(evt) !== teamName) continue

      const key = raceEventKey(evt, teamName)
      if (raceResultSeenKeys.has(key)) continue

      const data = evt?.data || {}
      const tickVal = toInt(evt?.tick ?? evt?.ts ?? 0)
      const popup = grouped.get(key) || {
        key,
        tick: tickVal,
        season: toInt(data?.season ?? gs?.season_number ?? 0),
        round: toInt(data?.round_number ?? 0),
        track: String(data?.track_name || 'Unknown Circuit'),
        league: String(data?.league_name || data?.league_id || ''),
        team: getRaceEventTeam(evt) || teamName,
        rows: [],
        totalPoints: 0,
        totalPrizeMoney: 0,
      }

      const row: RaceResultRow = {
        driver: String(data?.driver || 'Driver'),
        position: toInt(data?.position, 0),
        points: toInt(data?.points, 0),
        status: String(data?.status || 'finished'),
        prizeMoney: toInt(data?.prize_money, 0),
      }
      popup.rows.push(row)
      popup.totalPoints += row.points
      popup.totalPrizeMoney += row.prizeMoney
      grouped.set(key, popup)
    }

    if (grouped.size <= 0) return

    const newPopups = Array.from(grouped.values())
      .map((popup: RaceResultPopup) => ({
        ...popup,
        rows: popup.rows.slice().sort((a, b) => a.position - b.position),
      }))
      .sort((a, b) => a.tick - b.tick)

    for (const popup of newPopups) {
      raceResultSeenKeys.add(popup.key)
    }
    raceResultQueue = [...raceResultQueue, ...newPopups]

    if (!showRaceResultPopup && !activeRaceResult) {
      openNextRaceResultPopup()
    }
  }

  $: {
    const gs: any = $gameState
    const teamName = String(gs?.player_team?.name || '')
    const isRunning = Boolean(gs?.status === 'running' && teamName)

    if (!isRunning) {
      resetRaceResultTracking()
    } else {
      const gameKey = String(gs?.game_id || '')
      const currentTick = toInt(gs?.tick, 0)
      const tickRolledBack = raceTrackingLastTick >= 0 && currentTick < raceTrackingLastTick

      if (gameKey !== raceTrackingGameKey || tickRolledBack) {
        resetRaceResultTracking()
        raceTrackingGameKey = gameKey
      }

      raceTrackingLastTick = currentTick

      if (!raceBaselineInitialized) {
        seedRaceResultBaseline(gs)
        raceBaselineInitialized = true
      } else {
        queueNewRaceResultPopups(gs)
      }
    }
  }

  // ─── Top Banner: Player Team Last Race Results ────────────────
  $: bannerTeamName = String($gameState?.player_team?.name || '')
  $: bannerDriverNames = (($gameState?.player_team?.roster?.drivers || []) as any[])
    .map((driver: any) => String(driver?.name || '').trim())
    .filter(Boolean)

  $: bannerBackendDriverBlocks = Array.isArray($gameState?.player_driver_recent_results)
    ? $gameState.player_driver_recent_results
    : []

  $: bannerNormalizedBackend = bannerBackendDriverBlocks.map((driverBlock: any) => ({
    name: String(driverBlock?.name || '').trim(),
    results: (Array.isArray(driverBlock?.results) ? driverBlock.results : [])
      .map((row: any): DriverRecentResult => ({
        driver: String(row?.driver || driverBlock?.name || '').trim(),
        tick: toInt(row?.tick ?? 0),
        season: toInt(row?.season ?? 0),
        round: toInt(row?.round ?? 0),
        position: toInt(row?.position ?? 0),
        points: toInt(row?.points ?? 0),
        status: String(row?.status || 'finished'),
        trackName: String(row?.track_name || row?.trackName || ''),
      }))
      .filter((row: DriverRecentResult) => Boolean(row.driver))
      .sort((a: DriverRecentResult, b: DriverRecentResult) => b.tick - a.tick),
  }))

  $: bannerHasBackend = bannerNormalizedBackend.some((block: any) => (block?.results || []).length > 0)

  $: bannerFallbackResults = (Array.isArray($gameState?.recent_events) ? $gameState.recent_events : [])
    .filter((evt: any) => {
      const category = String(evt?.category || '').toLowerCase()
      if (category !== 'race_result') return false
      const data = evt?.data || {}
      const eventTeam = String(data?.team || data?.team_name || data?.player_team_name || '')
      return eventTeam === bannerTeamName
    })
    .map((evt: any): DriverRecentResult => {
      const data = evt?.data || {}
      return {
        driver: String(data?.driver || '').trim(),
        tick: toInt(evt?.tick ?? evt?.ts ?? 0),
        season: toInt(data?.season ?? $gameState?.season_number ?? 0),
        round: toInt(data?.round_number ?? data?.round ?? 0),
        position: toInt(data?.position ?? 0),
        points: toInt(data?.points ?? 0),
        status: String(data?.status || 'finished'),
        trackName: String(data?.track_name || ''),
      }
    })
    .filter((row: DriverRecentResult) => Boolean(row.driver))
    .sort((a: DriverRecentResult, b: DriverRecentResult) => b.tick - a.tick)

  $: bannerDriverHistories = bannerHasBackend
    ? bannerDriverNames.map((driverName: string) => {
        const found = bannerNormalizedBackend.find((block: any) => block.name === driverName)
        return {
          name: driverName,
          results: (found?.results || []).slice(0, 8),
        }
      })
    : bannerDriverNames.map((driverName: string) => ({
        name: driverName,
        results: bannerFallbackResults
          .filter((row: DriverRecentResult) => row.driver === driverName)
          .slice(0, 8),
      }))

  $: bannerLatestRaceTick = bannerDriverHistories.reduce((maxTick: number, block: any) => {
    const bestForDriver = (block?.results || []).reduce(
      (best: number, row: DriverRecentResult) => Math.max(best, toInt(row?.tick ?? 0)),
      0
    )
    return Math.max(maxTick, bestForDriver)
  }, 0)

  $: lastRaceBannerResults = bannerDriverHistories
    .map((block: any) => {
      const rows: DriverRecentResult[] = Array.isArray(block?.results) ? block.results : []
      if (!rows.length) return null
      const sameRace = bannerLatestRaceTick > 0
        ? rows.find((row: DriverRecentResult) => row.tick === bannerLatestRaceTick)
        : null
      const picked = sameRace || rows[0]
      if (!picked) return null
      return { ...picked, driver: block.name || picked.driver }
    })
    .filter((row: DriverRecentResult | null): row is DriverRecentResult => Boolean(row))

  $: lastRaceBannerPrimary = (
    lastRaceBannerResults.find((row: DriverRecentResult) => bannerLatestRaceTick > 0 && row.tick === bannerLatestRaceTick)
    || lastRaceBannerResults[0]
    || null
  ) as DriverRecentResult | null
  $: lastRaceBannerMeta = formatLastRaceMeta(lastRaceBannerPrimary)

  // ─── Top Banner: Days Until Next Race ─────────────────────────
  $: bannerLeagues = ($gameState?.leagues || {}) as Record<string, any>
  $: bannerTracks = ($gameState?.tracks || {}) as Record<string, any>
  $: bannerCurrentTick = toInt($gameState?.tick ?? 0)
  $: bannerPlayerLeague = Object.values(bannerLeagues).find((league: any) =>
    Array.isArray(league?.team_names) && league.team_names.includes(bannerTeamName)
  ) as any
  $: bannerRawSchedule = Array.isArray(bannerPlayerLeague?.schedule) ? bannerPlayerLeague.schedule : []
  $: bannerRacesDone = Math.max(0, toInt(bannerPlayerLeague?.races_this_season ?? 0))
  $: bannerSchedule = bannerRawSchedule
    .map((entry: any, idx: number) => normalizeScheduleEntry(entry, idx, bannerRacesDone, bannerTracks))
    .filter((entry: ScheduleEntry | null): entry is ScheduleEntry => Boolean(entry))
    .sort((a: ScheduleEntry, b: ScheduleEntry) => a.tick - b.tick)

  $: nextRaceByIndex = bannerSchedule[bannerRacesDone] || null
  $: nextRaceByTick = bannerSchedule.find((entry: ScheduleEntry) => entry.tick >= bannerCurrentTick) || null
  $: nextRaceEntry = nextRaceByIndex || nextRaceByTick || null
  $: daysUntilNextRace = nextRaceEntry ? Math.max(0, nextRaceEntry.tick - bannerCurrentTick) : null
  $: nextRaceTrack = nextRaceEntry
    ? (nextRaceEntry.trackName || (nextRaceEntry.trackId && bannerTracks?.[nextRaceEntry.trackId]?.name) || '')
    : ''
  $: nextRaceCountdownLabel = formatDaysUntilRace(daysUntilNextRace)
  $: showNextRaceBanner = Boolean($hasGame && nextRaceEntry && nextRaceCountdownLabel)

  // ─── REST Polling ───
  let pollInterval: ReturnType<typeof setInterval> | null = null

  async function pollState() {
    try {
      const state = await fetchState()
      connectionState.set('connected')

      // If server returned "busy" (lock contended), skip this update — keep
      // the existing gameState so the UI doesn't flicker.
      if (state.status === 'busy') return

      gameState.set(state)

      // If we were waiting for a game to appear and it just did, clear the flag
      if (pendingGameLoad) {
        if (state.status === 'running' && state.player_team) {
          console.log('[FTB] Game detected — clearing pendingGameLoad', state.status)
          pendingGameLoad = false
        }
      }
    } catch {
      connectionState.set('disconnected')
    }
  }

  function startPolling() {
    if (pollInterval) return
    pollState() // immediate first fetch
    pollInterval = setInterval(pollState, 3000)
  }

  function stopPolling() {
    if (pollInterval) { clearInterval(pollInterval); pollInterval = null }
  }

  async function tryAutoLoad() {
    // Wait a moment for the first poll to land
    await new Promise(r => setTimeout(r, 1500))
    // If game is already loaded (backend started with state), skip
    if ($hasGame) { autoLoadAttempted = true; return }
    try {
      const info = await checkAutosave()
      if (info.exists && info.path) {
        console.log('[FTB] Autosave found, loading:', info.path)
        pendingGameLoad = true
        autoLoadAttempted = true  // show "Setting up" screen, not "Checking"
        await handleLoadSave(info.path)
        return
      }
    } catch (e) {
      console.warn('[FTB] Autosave check failed:', e)
    }
    autoLoadAttempted = true
  }

  onMount(() => {
    connectionState.set('connecting')
    startPolling()

    // Auto-load autosave if no game is loaded
    tryAutoLoad()

    // Listen for WebSocket audio events and navigation commands
    const unsubWs = onMessage((msg: any) => {
      if (msg?.type === 'audio_event') {
        webAudio.handleAudioEvent(msg.data)
      }
      // Handle navigation commands from Audio CLI (dynamic button clicking)
      if (msg?.type === 'navigate') {
        const data = msg.data || {}
        const screen = data.screen || ''
        console.log('[FTB] Navigate message received:', screen, data)
        if (screen === 'wizard') {
          showSetupWizard = true
          showLoadScreen = false
          pendingGameLoad = true
        } else if (screen === 'landing') {
          showSetupWizard = false
          showLoadScreen = false
          pendingGameLoad = false
        } else if (screen === 'loading') {
          showLoadScreen = false
          showSetupWizard = false
          pendingGameLoad = true
        } else if (screen === 'game') {
          showSetupWizard = false
          showLoadScreen = false
          pendingGameLoad = false
          // Game was created — trigger immediate poll to pick up state ASAP
          pollState()
        }
      }
      // Handle tab switching from Audio CLI
      if (msg?.type === 'switch_tab') {
        const tab = msg.data?.tab
        if (tab) {
          console.log('[FTB] Tab switch received:', tab)
          activeTab.set(tab)
          showNotifs = false
        }
      }
    })

    // Poll audio state every 5s for drift correction
    audioSyncInterval = setInterval(async () => {
      if (!$hasGame || !webAudio.hasUserInteracted()) return
      const s = await fetchAudioState()
      if (s) webAudio.syncFromState(s)
    }, 5000)

    // Unlock audio on first user interaction
    const unlock = () => {
      webAudio.ensureUserInteraction()
      // If a game is already loaded, start music now
      if ($hasGame) webAudio.startMusic()
      document.removeEventListener('click', unlock)
      document.removeEventListener('touchstart', unlock)
    }
    document.addEventListener('click', unlock, { once: false })
    document.addEventListener('touchstart', unlock, { once: false })

    return () => {
      unsubWs()
    }
  })

  let audioSyncInterval: ReturnType<typeof setInterval> | null = null

  onDestroy(() => {
    stopPolling()
    if (audioSyncInterval) clearInterval(audioSyncInterval)
    webAudio.stopAll()
  })

  // Start music when game first becomes available
  $: if ($hasGame && webAudio.hasUserInteracted() && !webAudio.isStarted()) {
    webAudio.startMusic()
  }
  // Clear pending flag reactively when game appears
  $: if ($hasGame && pendingGameLoad) {
    pendingGameLoad = false
  }
  // Stop audio when game disappears (station stopped)
  $: if (!$hasGame && webAudio.isStarted()) {
    webAudio.stopAll()
  }

  // ─── Load Game Screen ───
  async function openLoadScreen() {
    showLoadScreen = true
    loadingList = true
    try { saves = await fetchSaves() } catch { saves = [] }
    loadingList = false
  }

  async function handleLoadSave(path: string) {
    if (loadingSave) return
    loadingSave = true
    pendingGameLoad = true
    try {
      await loadGame(path)
      // Poll until the backend has loaded the game (up to 30s)
      let loaded = false
      for (let i = 0; i < 60; i++) {
        await new Promise(r => setTimeout(r, 500))
        try {
          const state = await fetchState()
          if (state && state.status === 'running' && state.player_team) {
            gameState.set(state)
            loaded = true
            break
          }
        } catch {}
      }
      if (!loaded) {
        // Don't alert — just keep pendingGameLoad true; background poll will pick it up
      }
      showLoadScreen = false
    } catch (e) {
      console.error('load save', e)
      alert('Failed to load save.')
      pendingGameLoad = false
    }
    loadingSave = false
  }

  function handleNewGame() {
    showLoadScreen = false
    showSetupWizard = true
    pendingGameLoad = true
  }

  async function handleSetupStart() {
    showSetupWizard = false
    // Aggressively poll until the game state appears (up to 60s).
    // The wizard's own poll may have missed it if the engine was busy.
    for (let i = 0; i < 120; i++) {
      await new Promise(r => setTimeout(r, 500))
      try {
        const state = await fetchState()
        if (state && state.status === 'running' && state.player_team) {
          gameState.set(state)
          pendingGameLoad = false
          return
        }
      } catch {}
    }
    // If we still haven't loaded after 60s, clear pending so user isn't stuck
    pendingGameLoad = false
  }

  function formatDate(mtime: number): string {
    return new Date(mtime * 1000).toLocaleString()
  }

  function formatSize(bytes: number): string {
    if (bytes < 1024) return bytes + ' B'
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB'
    return (bytes / 1048576).toFixed(1) + ' MB'
  }
</script>

<div class="app" class:has-game={$hasGame}>
  <Toolbar on:notifications={() => showNotifs = !showNotifs} on:newgame={handleNewGame} on:loadsave={openLoadScreen} />

  {#if showNextRaceBanner}
    <div class="next-race-banner" class:imminent={daysUntilNextRace !== null && daysUntilNextRace <= 3}>
      <span class="nr-title">📅 Next Race</span>
      <span class="nr-count">{nextRaceCountdownLabel}</span>
      {#if nextRaceTrack}
        <span class="nr-track">{nextRaceTrack}</span>
      {/if}
    </div>
  {/if}

  {#if $hasGame && lastRaceBannerResults.length > 0}
    <div class="last-race-banner">
      <div class="last-race-header">
        <span class="last-race-title">🏁 Player Last Race</span>
        {#if lastRaceBannerMeta}
          <span class="last-race-meta">{lastRaceBannerMeta}</span>
        {/if}
      </div>
      <div class="last-race-list">
        {#each lastRaceBannerResults as result}
          <div
            class="last-race-pill"
            class:podium={result.position > 0 && result.position <= 3}
            class:dnf={!isFinishedStatus(result.status)}
          >
            <span class="lr-driver">{result.driver}</span>
            <span class="lr-pos">P{result.position > 0 ? result.position : '—'}</span>
            <span class="lr-pts">{result.points} pts</span>
            {#if !isFinishedStatus(result.status)}
              <span class="lr-status">{formatResultStatus(result.status)}</span>
            {/if}
          </div>
        {/each}
      </div>
    </div>
  {/if}

  {#if !autoLoadAttempted && !$hasGame}
    <!-- Still checking for autosave — show loading splash -->
    <div class="landing">
      <div class="landing-inner">
        <h1>🏎️ FROM THE BACKMARKER</h1>
        <p style="font-size:16px;">⏳ Checking for saved game…</p>
      </div>
    </div>

  {:else if !$hasGame && !showSetupWizard && !showLoadScreen && !pendingGameLoad}
    <!-- No game loaded: show landing -->
    <div class="landing">
      <div class="landing-inner">
        <h1>🏎️ FROM THE BACKMARKER</h1>
        <p>Racing Management Simulation</p>
        <div class="landing-actions">
          <button class="btn btn-primary btn-lg" on:click={() => { showSetupWizard = true; pendingGameLoad = true }}>
            🆕 New Game
          </button>
          <button class="btn btn-ghost btn-lg" on:click={openLoadScreen}>
            📂 Load Game
          </button>
        </div>
      </div>
    </div>

  {:else if showLoadScreen}
    <!-- Load Game Screen (works from landing or in-game) -->
    <div class="load-screen">
      <div class="load-header">
        <button class="btn btn-ghost btn-sm" on:click={() => showLoadScreen = false}>← Back</button>
        <h2>📂 Load Game</h2>
        <button class="btn btn-ghost btn-sm" on:click={openLoadScreen}>🔄</button>
      </div>
      <div class="save-list scroll-y">
        {#if loadingList}
          <div class="empty-state">Loading saves…</div>
        {:else if saves.length === 0}
          <div class="empty-state">No save files found.</div>
        {:else}
          {#each saves as save}
            <div class="save-item">
              <div class="save-info">
                <div class="save-name">{save.name}</div>
                <div class="save-meta">
                  <span>{formatDate(save.mtime)}</span>
                  <span class="sep">·</span>
                  <span>{formatSize(save.size)}</span>
                </div>
              </div>
              <button class="btn btn-primary btn-sm" disabled={loadingSave} on:click={() => handleLoadSave(save.path)}>
                {loadingSave ? '⏳' : '▶️ Load'}
              </button>
            </div>
          {/each}
        {/if}
      </div>
    </div>

  {:else if showSetupWizard}
    <SetupWizard on:start={handleSetupStart} />

  {:else if pendingGameLoad && !$hasGame}
    <!-- Waiting for backend to create/load the game -->
    <div class="landing">
      <div class="landing-inner">
        <h1>🏎️ FROM THE BACKMARKER</h1>
        <p style="font-size:16px;">⏳ Setting up your game…</p>
        <p style="color:var(--c-text-muted);">Generating world, teams, and schedules. This may take a moment.</p>
        <button class="btn btn-ghost btn-sm" style="margin-top:24px;" on:click={() => { pendingGameLoad = false }}>
          ← Cancel
        </button>
      </div>
    </div>

  {:else}
    <!-- Main Game UI -->
    <main class="main-area">
      {#if showNotifs}
        <NotificationCenter />
      {:else}
        {#if $activeTab === 'dashboard'}<Dashboard />
        {:else if $activeTab === 'team'}<Team />
        {:else if $activeTab === 'car'}<Car />
        {:else if $activeTab === 'development'}<Development />
        {:else if $activeTab === 'raceops'}<RaceOps />
        {:else if $activeTab === 'pbp'}<PlayByPlay />
        {:else if $activeTab === 'finance'}<Finance />
        {:else if $activeTab === 'sponsors'}<Sponsors />
        {:else if $activeTab === 'promotion'}<Promotion />
        {:else if $activeTab === 'stats'}<RacingStats />
        {:else if $activeTab === 'analytics'}<Analytics />
        {:else if $activeTab === 'career'}<ManagerCareer />
        {:else if $activeTab === 'calendar'}<Calendar />
        {:else if $activeTab === 'ai'}<AIAssistant />
        {:else if $activeTab === 'penalties'}<Penalties />
        {:else if $activeTab === 'history'}<History />
        {:else if $activeTab === 'help'}<Help />
        {:else if $activeTab === 'data'}<FTBData />
        {:else}<Dashboard />
        {/if}
      {/if}
    </main>

    <!-- Subtitle overlay -->
    {#if $subtitle}
      <div class="subtitle-bar">
        <span class="subtitle-text">{$subtitle}</span>
      </div>
    {/if}

    <!-- Bottom Tab Bar (mobile nav) -->
    <nav class="tab-nav">
      {#each tabs as tab}
        <button
          class="tab-nav-btn"
          class:active={$activeTab === tab.id}
          on:click={() => { activeTab.set(tab.id); showNotifs = false }}
          title={tab.name}
        >
          <span class="tab-icon">{tab.label}</span>
          <span class="tab-label">{tab.name}</span>
        </button>
      {/each}
    </nav>
  {/if}

  <!-- Connection indicator -->
  {#if $connectionState === 'disconnected'}
    <div class="conn-banner">
      ⚡ Server unreachable — retrying...
    </div>
  {/if}

  <Modal
    show={showRaceResultPopup}
    title="🏁 Race Result"
    size="md"
    closeOnBackdrop={false}
    showCloseButton={false}
    on:close={acknowledgeRaceResultPopup}
  >
    {#if activeRaceResult}
      <div class="race-result-popup">
        <div class="rr-head">
          <div class="rr-title">{activeRaceResult.team}</div>
          <div class="rr-meta">
            {activeRaceResult.league || 'League'}
            {#if activeRaceResult.round > 0} • Round {activeRaceResult.round}{/if}
          </div>
          <div class="rr-meta">{activeRaceResult.track} • Tick {activeRaceResult.tick}</div>
        </div>

        <div class="rr-summary">
          <span class="rr-chip">Team Points: {activeRaceResult.totalPoints}</span>
          {#if activeRaceResult.totalPrizeMoney > 0}
            <span class="rr-chip">Prize: ${activeRaceResult.totalPrizeMoney.toLocaleString()}</span>
          {/if}
        </div>

        <div class="rr-rows">
          {#each activeRaceResult.rows as row}
            <div class="rr-row">
              <span class="rr-driver">{row.driver}</span>
              <span class="rr-pos">P{row.position > 0 ? row.position : '—'}</span>
              <span class="rr-pts">{row.points} pts</span>
              <span class="rr-status">{row.status}</span>
            </div>
          {/each}
        </div>

        <div class="rr-actions">
          {#if raceResultQueue.length > 0}
            <span class="rr-pending">{raceResultQueue.length} more race result{raceResultQueue.length > 1 ? 's' : ''} queued</span>
          {/if}
          <button class="btn btn-primary" on:click={acknowledgeRaceResultPopup}>Continue</button>
        </div>
      </div>
    {/if}
  </Modal>

  <Toast />
</div>

<style>
  .app {
    display: flex;
    flex-direction: column;
    height: 100dvh;
    background: var(--c-bg-primary);
    color: var(--c-text-primary);
    overflow: hidden;
  }

  .main-area {
    flex: 1;
    overflow-y: auto;
    overflow-x: hidden;
    position: relative;
    -webkit-overflow-scrolling: touch;
  }

  .next-race-banner {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 7px 12px;
    border-bottom: 1px solid var(--c-border);
    background:
      linear-gradient(180deg, rgba(96, 165, 250, 0.12) 0%, rgba(96, 165, 250, 0.04) 100%),
      var(--c-bg-secondary);
    font-size: 12px;
  }
  .next-race-banner.imminent {
    background:
      linear-gradient(180deg, rgba(251, 191, 36, 0.16) 0%, rgba(251, 191, 36, 0.05) 100%),
      var(--c-bg-secondary);
  }
  .nr-title {
    font-weight: 700;
    color: var(--c-text-primary);
    white-space: nowrap;
  }
  .nr-count {
    font-family: var(--font-mono);
    color: var(--c-accent);
    font-weight: 700;
    white-space: nowrap;
  }
  .nr-track {
    flex: 1;
    color: var(--c-text-secondary);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .last-race-banner {
    flex-shrink: 0;
    padding: 8px 12px 9px;
    border-bottom: 1px solid var(--c-border);
    background:
      linear-gradient(180deg, rgba(76, 201, 240, 0.12) 0%, rgba(76, 201, 240, 0.04) 100%),
      var(--c-bg-secondary);
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .last-race-header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 10px;
  }
  .last-race-title {
    font-size: 12px;
    font-weight: 700;
    color: var(--c-text-primary);
    letter-spacing: 0.2px;
  }
  .last-race-meta {
    font-size: 11px;
    color: var(--c-text-secondary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .last-race-list {
    display: flex;
    gap: 6px;
    overflow-x: auto;
    scrollbar-width: none;
    -ms-overflow-style: none;
  }
  .last-race-list::-webkit-scrollbar { display: none; }
  .last-race-pill {
    flex: 0 0 auto;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 6px 10px;
    border-radius: 999px;
    border: 1px solid var(--c-border);
    background: rgba(15, 15, 30, 0.45);
    font-size: 11px;
    line-height: 1;
  }
  .last-race-pill.podium {
    border-color: rgba(251, 191, 36, 0.55);
    background: rgba(251, 191, 36, 0.12);
  }
  .last-race-pill.dnf {
    border-color: rgba(248, 113, 113, 0.5);
    background: rgba(248, 113, 113, 0.13);
  }
  .lr-driver {
    font-weight: 600;
    color: var(--c-text-primary);
  }
  .lr-pos {
    font-family: var(--font-mono);
    color: var(--c-accent);
    font-weight: 700;
  }
  .lr-pts {
    font-family: var(--font-mono);
    color: var(--c-text-secondary);
  }
  .lr-status {
    color: var(--c-danger);
    font-weight: 700;
    letter-spacing: 0.2px;
  }

  /* ─── Landing ─── */
  .landing {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    text-align: center;
  }
  .landing-inner h1 {
    font-size: 28px;
    font-weight: 800;
    letter-spacing: 2px;
    margin-bottom: 8px;
  }
  .landing-inner p { color: var(--c-text-muted); margin-bottom: 24px; }
  .landing-actions { display: flex; gap: 12px; justify-content: center; }
  .landing-hint { font-size: 12px; margin-top: 20px; }

  /* ─── Load Game Screen ─── */
  .load-screen {
    flex: 1;
    display: flex;
    flex-direction: column;
    padding: 16px;
    overflow: hidden;
  }
  .load-header {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 16px;
  }
  .load-header h2 {
    flex: 1;
    font-size: 18px;
    font-weight: 700;
    text-align: center;
  }
  .save-list {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 6px;
    overflow-y: auto;
  }
  .save-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 14px;
    background: var(--c-bg-card);
    border: 1px solid var(--c-border);
    border-radius: var(--radius);
  }
  .save-name {
    font-size: 14px;
    font-weight: 600;
    word-break: break-all;
  }
  .save-meta {
    font-size: 11px;
    color: var(--c-text-muted);
    margin-top: 2px;
  }
  .save-meta .sep { margin: 0 4px; }
  .empty-state {
    text-align: center;
    color: var(--c-text-muted);
    padding: 40px 20px;
    font-size: 14px;
  }

  /* ─── Subtitle overlay ─── */
  .subtitle-bar {
    position: fixed;
    bottom: 64px;
    left: 50%;
    transform: translateX(-50%);
    background: rgba(0, 0, 0, 0.85);
    backdrop-filter: blur(8px);
    padding: 8px 20px;
    border-radius: 8px;
    max-width: 90vw;
    box-sizing: border-box;
    overflow: hidden;
    text-align: center;
    z-index: 90;
    pointer-events: none;
    animation: fadeInUp 0.2s ease-out;
  }
  .subtitle-text {
    font-size: 14px;
    color: #fff;
    line-height: 1.4;
    overflow-wrap: break-word;
    word-break: break-word;
    display: block;
  }

  @keyframes fadeInUp {
    from { opacity: 0; transform: translateX(-50%) translateY(8px); }
    to   { opacity: 1; transform: translateX(-50%) translateY(0); }
  }

  /* ─── Tab Navigation (bottom bar) ─── */
  .tab-nav {
    display: flex;
    overflow-x: auto;
    background: var(--c-bg-secondary);
    border-top: 1px solid var(--c-border);
    flex-shrink: 0;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: none;
    padding: 0 24px;
  }
  .tab-nav::-webkit-scrollbar { display: none; }
  .tab-nav-btn {
    flex: 0 0 auto;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 6px 10px;
    background: none;
    border: none;
    color: var(--c-text-muted);
    cursor: pointer;
    min-width: 56px;
    transition: color 0.15s;
    border-top: 2px solid transparent;
  }
  .tab-nav-btn.active {
    color: var(--c-accent);
    border-top-color: var(--c-accent);
  }
  .tab-icon { font-size: 18px; line-height: 1; }
  .tab-label { font-size: 9px; margin-top: 2px; }

  /* ─── Connection Banner ─── */
  .conn-banner {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    text-align: center;
    padding: 4px;
    font-size: 11px;
    font-weight: 600;
    background: var(--c-danger);
    color: #fff;
    z-index: 200;
  }
  .conn-banner.connecting {
    background: var(--c-warning);
    color: #000;
  }

  .race-result-popup {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .rr-head {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .rr-title {
    font-size: 16px;
    font-weight: 700;
    color: var(--c-text-primary);
  }
  .rr-meta {
    font-size: 12px;
    color: var(--c-text-secondary);
  }
  .rr-summary {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
  }
  .rr-chip {
    font-size: 11px;
    font-weight: 700;
    color: var(--c-text-primary);
    background: var(--c-bg-card);
    border: 1px solid var(--c-border);
    border-radius: 999px;
    padding: 4px 8px;
  }
  .rr-rows {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .rr-row {
    display: grid;
    grid-template-columns: 1fr auto auto auto;
    gap: 8px;
    align-items: center;
    padding: 8px 10px;
    border-radius: 8px;
    background: var(--c-bg-card);
    border: 1px solid var(--c-border);
    font-size: 12px;
  }
  .rr-driver {
    font-weight: 600;
    color: var(--c-text-primary);
  }
  .rr-pos {
    font-family: var(--font-mono);
    font-weight: 700;
    color: var(--c-accent);
  }
  .rr-pts {
    font-family: var(--font-mono);
    color: var(--c-text-secondary);
  }
  .rr-status {
    text-transform: capitalize;
    color: var(--c-text-secondary);
  }
  .rr-actions {
    margin-top: 4px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }
  .rr-pending {
    font-size: 11px;
    color: var(--c-text-muted);
  }

  /* ─── Responsive ─── */
  @media (min-width: 769px) {
    .tab-nav {
      justify-content: center;
    }
    .tab-nav-btn {
      min-width: 64px;
    }
    .subtitle-bar {
      bottom: 72px;
    }
  }
</style>
