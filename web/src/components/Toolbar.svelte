<script lang="ts">
  import { tickStep, tickBatch, saveGame, fetchState } from '../lib/api'
  import { gameState, dateStr, tick, phase, notifications, unreadCount, hasGame } from '../lib/stores'
  import { createEventDispatcher } from 'svelte'

  const dispatch = createEventDispatcher()

  let showNotifications = false
  let working = false

  async function handleTick(n: number) {
    if (working) return; working = true
    try { await tickStep(n); await refreshState() } catch (e) { console.error('tick', e) }
    working = false
  }

  async function handleBatch(n: number) {
    if (working) return; working = true
    try { await tickBatch(n); await refreshState() } catch (e) { console.error('batch', e) }
    working = false
  }

  async function handleSave() {
    try { await saveGame() } catch (e) { console.error('save', e) }
  }

  function newGame() {
    if (confirm('Start a new game? Current progress will be lost if not saved.')) {
      dispatch('newgame')
    }
  }

  async function refreshState() {
    try {
      // Small delay so backend processes queued command
      await new Promise(r => setTimeout(r, 600))
      const state = await fetchState()
      gameState.set(state)
    } catch (e) { console.error('refresh', e) }
  }
</script>

<div class="toolbar">
  <div class="toolbar-left">
    <span class="logo">🏎️ FTB</span>
    <span class="date-display">{$dateStr}</span>
    <span class="tick-display">T{$tick}</span>
  </div>

  {#if $hasGame}
    <div class="toolbar-center">
      <button class="btn btn-primary btn-sm" disabled={working} on:click={() => handleTick(1)} title="+1 Day">+1</button>
      <button class="btn btn-primary btn-sm" disabled={working} on:click={() => handleBatch(7)} title="+1 Week">+7</button>
      <button class="btn btn-primary btn-sm" disabled={working} on:click={() => handleBatch(30)} title="+1 Month">+30</button>
    </div>
  {/if}

  <div class="toolbar-right">
    <button class="btn btn-ghost btn-sm" on:click={refreshState} title="Refresh">🔄</button>
    <button class="btn btn-ghost btn-sm" on:click={handleSave} title="Save">💾</button>
    <button class="btn btn-ghost btn-sm notification-btn" on:click={() => dispatch('notifications')} title="Notifications">
      🔔
      {#if $unreadCount > 0}
        <span class="badge">{$unreadCount}</span>
      {/if}
    </button>
  </div>
</div>

<style>
  .toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 6px 12px;
    background: var(--c-bg-secondary);
    border-bottom: 1px solid var(--c-border);
    height: 48px;
    flex-shrink: 0;
    gap: 8px;
  }
  .toolbar-left {
    display: flex;
    align-items: center;
    gap: 10px;
    min-width: 0;
  }
  .logo {
    font-size: 16px;
    font-weight: 800;
    white-space: nowrap;
  }
  .date-display {
    font-size: 12px;
    color: var(--c-text-secondary);
    font-family: var(--font-mono);
    white-space: nowrap;
  }
  .tick-display {
    font-size: 11px;
    color: var(--c-text-muted);
    font-family: var(--font-mono);
  }
  .toolbar-center {
    display: flex;
    gap: 4px;
  }
  .toolbar-right {
    display: flex;
    align-items: center;
    gap: 4px;
  }
  .notification-btn {
    position: relative;
  }
  .notification-btn .badge {
    position: absolute;
    top: -4px;
    right: -4px;
  }
</style>
