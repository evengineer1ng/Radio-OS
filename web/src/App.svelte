<script lang="ts">
  import { onMount, onDestroy } from 'svelte'
  import { fetchState, fetchSaves, loadGame } from './lib/api'
  import {
    gameState, subtitle, notifications, nowPlaying,
    connectionState, activeTab, eventLog, hasGame,
    addToast, lastBatchSummary, widgetUpdates
  } from './lib/stores'

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

  // ─── REST Polling ───
  let pollInterval: ReturnType<typeof setInterval> | null = null

  async function pollState() {
    try {
      const state = await fetchState()
      gameState.set(state)
      connectionState.set('connected')
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

  onMount(() => {
    connectionState.set('connecting')
    startPolling()
  })

  onDestroy(stopPolling)

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
    try {
      await loadGame(path)
      await new Promise(r => setTimeout(r, 1500))
      const state = await fetchState()
      gameState.set(state)
      showLoadScreen = false
    } catch (e) {
      console.error('load save', e)
      alert('Failed to load save.')
    }
    loadingSave = false
  }

  function handleNewGame() {
    showLoadScreen = false
    showSetupWizard = true
  }

  function handleSetupStart() {
    showSetupWizard = false
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
  <Toolbar on:notifications={() => showNotifs = !showNotifs} on:newgame={handleNewGame} />

  {#if !$hasGame && !showSetupWizard && !showLoadScreen}
    <!-- No game loaded: show landing -->
    <div class="landing">
      <div class="landing-inner">
        <h1>🏎️ FROM THE BACKMARKER</h1>
        <p>Racing Management Simulation</p>
        <div class="landing-actions">
          <button class="btn btn-primary btn-lg" on:click={() => showSetupWizard = true}>
            🆕 New Game
          </button>
          <button class="btn btn-ghost btn-lg" on:click={openLoadScreen}>
            📂 Load Game
          </button>
        </div>
      </div>
    </div>

  {:else if showLoadScreen && !$hasGame}
    <!-- Load Game Screen -->
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
    overflow: hidden;
    position: relative;
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
