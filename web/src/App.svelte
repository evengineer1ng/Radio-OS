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
  import Penalties from './tabs/Penalties.svelte'
  import History from './tabs/History.svelte'
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
    { id: 'stats',      label: '📊', name: 'Stats' },
    { id: 'analytics',  label: '📈', name: 'Analytics' },
    { id: 'career',     label: '🏆', name: 'Career' },
    { id: 'calendar',   label: '📅', name: 'Calendar' },
    { id: 'ai',         label: '🤖', name: 'AI' },
    { id: 'penalties',  label: '⚠️', name: 'Penalties' },
    { id: 'history',    label: '📜', name: 'History' },
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
        const ready = state.status && state.status !== 'no_game' && state.status !== 'no_controller'
        if (ready) {
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

    // Listen for WebSocket audio events
    const unsubWs = onMessage((msg: any) => {
      if (msg?.type === 'audio_event') {
        webAudio.handleAudioEvent(msg.data)
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
          if (state && state.status && state.status !== 'no_game' && state.status !== 'no_controller') {
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

  function handleSetupStart() {
    showSetupWizard = false
    // The wizard already set pendingGameLoad; background polling will detect the game.
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
        {:else if $activeTab === 'stats'}<RacingStats />
        {:else if $activeTab === 'analytics'}<Analytics />
        {:else if $activeTab === 'career'}<ManagerCareer />
        {:else if $activeTab === 'calendar'}<Calendar />
        {:else if $activeTab === 'ai'}<AIAssistant />
        {:else if $activeTab === 'penalties'}<Penalties />
        {:else if $activeTab === 'history'}<History />
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
    z-index: 90;
    pointer-events: none;
    animation: fadeInUp 0.2s ease-out;
  }
  .subtitle-text {
    font-size: 14px;
    color: #fff;
    line-height: 1.4;
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
