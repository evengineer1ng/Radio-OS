<script lang="ts">
  import { sendCommand, requestState } from '../lib/ws'
  import { dateStr, tick, phase, notifications, unreadCount, hasGame } from '../lib/stores'
  import { createEventDispatcher } from 'svelte'

  const dispatch = createEventDispatcher()

  let showNotifications = false

  function tickStep(n: number) { sendCommand({ cmd: 'ftb_tick_step', n }) }
  function tickBatch(n: number) { sendCommand({ cmd: 'ftb_tick_batch', n }) }
  function saveGame() { sendCommand({ cmd: 'ftb_save' }) }
  function newGame() {
    if (confirm('Start a new game? Current progress will be lost if not saved.')) {
      sendCommand({ cmd: 'ftb_reset' })
      dispatch('newgame')
    }
  }

  function refreshState() { requestState() }
</script>

<div class="toolbar">
  <div class="toolbar-left">
    <span class="logo">🏎️ FTB</span>
    <span class="date-display">{$dateStr}</span>
    <span class="tick-display">T{$tick}</span>
  </div>

  {#if $hasGame}
    <div class="toolbar-center">
      <button class="btn btn-primary btn-sm" on:click={() => tickStep(1)} title="+1 Day">+1</button>
      <button class="btn btn-primary btn-sm" on:click={() => tickBatch(7)} title="+1 Week">+7</button>
      <button class="btn btn-primary btn-sm" on:click={() => tickBatch(30)} title="+1 Month">+30</button>
    </div>
  {/if}

  <div class="toolbar-right">
    <button class="btn btn-ghost btn-sm" on:click={refreshState} title="Refresh">🔄</button>
    <button class="btn btn-ghost btn-sm" on:click={saveGame} title="Save">💾</button>
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
