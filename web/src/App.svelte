<script lang="ts">
  import { onMount, onDestroy } from 'svelte'
  import { connect, onMessage, disconnect } from './lib/ws'
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
  ]

  let showNotifs = false
  let showSetupWizard = false

  // Handle incoming WS messages
  function handleMessage(msg: any) {
    switch (msg.type) {
      case 'state':
        gameState.set(msg.data)
        break
      case 'subtitle':
        subtitle.set(msg.text || '')
        break
      case 'widget_update':
        widgetUpdates.update(w => ({ ...w, [msg.key]: msg.data }))
        // If widget_update carries full game state, merge it
        if (msg.key === 'ftb_game' && msg.data) {
          gameState.set(msg.data)
        }
        break
      case 'event':
        eventLog.update(log => [msg, ...log].slice(0, 200))
        if (msg.event_type === 'now_playing_on') {
          nowPlaying.set(msg)
        } else if (msg.event_type === 'now_playing_off') {
          nowPlaying.set(null)
        }
        break
      case 'notification':
        notifications.update(n => [msg.data, ...n])
        addToast(msg.data.title || 'New notification', 'info')
        break
      case 'notifications_list':
        notifications.set(msg.data || [])
        break
      case 'batch_summary':
        lastBatchSummary.set(msg.data)
        break
      case 'toast':
        addToast(msg.text || msg.message, msg.level || 'info')
        break
      case 'pong':
        break
      default:
        console.log('[FTB WS] unhandled:', msg.type)
    }
  }

  onMount(() => {
    onMessage(handleMessage)
    connect()
  })

  onDestroy(() => {
    disconnect()
  })

  function handleNewGame() {
    showSetupWizard = true
  }

  function handleSetupStart() {
    showSetupWizard = false
  }
</script>

<div class="app" class:has-game={$hasGame}>
  <Toolbar on:notifications={() => showNotifs = !showNotifs} on:newgame={handleNewGame} />

  {#if !$hasGame && !showSetupWizard}
    <!-- No game loaded: show landing -->
    <div class="landing">
      <div class="landing-inner">
        <h1>🏎️ FROM THE BACKMARKER</h1>
        <p>Racing Management Simulation</p>
        <div class="landing-actions">
          <button class="btn btn-primary btn-lg" on:click={() => showSetupWizard = true}>
            🆕 New Game
          </button>
        </div>
        <p class="muted landing-hint">Or load a save from the desktop app.</p>
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
  {#if $connectionState !== 'connected'}
    <div class="conn-banner" class:connecting={$connectionState === 'connecting'}>
      {$connectionState === 'connecting' ? '⟳ Connecting...' : '⚡ Disconnected — retrying...'}
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
