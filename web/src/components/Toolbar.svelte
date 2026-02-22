<script lang="ts">
  import { tickStep, tickBatch, saveGame, fetchSaves, globalRefresh } from '../lib/api'
  import { gameState, dateStr, tick, phase, notifications, unreadCount, hasGame, addToast } from '../lib/stores'
  import { createEventDispatcher } from 'svelte'

  const dispatch = createEventDispatcher()

  let showNotifications = false
  let working = false
  let saving = false
  let showSaveModal = false
  let saveName = ''
  let existingSaves: any[] = []
  let loadingSaves = false

  async function handleTick(n: number) {
    if (working) return; working = true
    try { await tickStep(n); await refreshState(600); addToast(`Advanced ${n} day${n > 1 ? 's' : ''}`, 'success') } catch (e) { console.error('tick', e); addToast('Tick failed', 'error') }
    working = false
  }

  async function handleBatch(n: number) {
    if (working) return; working = true
    try { await tickBatch(n); await refreshState(600); addToast(`Advanced ${n} days`, 'success') } catch (e) { console.error('batch', e); addToast('Batch failed', 'error') }
    working = false
  }

  async function openSaveModal() {
    // Generate a default name from team + date
    const gs = $gameState as any
    const team = gs?.player_team_name || gs?.team?.name || 'save'
    const day = gs?.date_str || `T${gs?.tick || 0}`
    saveName = `${team} - ${day}`.replace(/[\/\\:*?"<>|]/g, '_')
    showSaveModal = true
    loadingSaves = true
    try { existingSaves = await fetchSaves() } catch { existingSaves = [] }
    loadingSaves = false
  }

  async function handleSave() {
    if (saving || !saveName.trim()) return
    saving = true
    try {
      await saveGame(saveName.trim())
      addToast(`Saved as "${saveName.trim()}" ✅`, 'success')
      showSaveModal = false
    } catch (e) {
      console.error('save', e)
      addToast('Save failed', 'error')
    }
    saving = false
  }

  function overwriteSave(name: string) {
    // Strip .json extension for display, keep for save
    saveName = name.replace(/\.json$/, '')
    handleSave()
  }

  function newGame() {
    if (confirm('Start a new game? Current progress will be lost if not saved.')) {
      dispatch('newgame')
    }
  }

  async function refreshState(delayMs: number = 0) {
    try {
      if (delayMs > 0) {
        // Small delay so backend processes queued command
        await new Promise(r => setTimeout(r, delayMs))
      }
      await globalRefresh()
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
      <button class="btn btn-tick" class:working disabled={working} on:click={() => handleTick(1)} title="+1 Day">
        {#if working}⏳{:else}⏩{/if} +1
      </button>
      <button class="btn btn-tick" class:working disabled={working} on:click={() => handleBatch(7)} title="+1 Week">+7</button>
      <button class="btn btn-tick" class:working disabled={working} on:click={() => handleBatch(30)} title="+1 Month">+30</button>
    </div>
  {/if}

  <div class="toolbar-right">
    <button class="btn btn-ghost btn-sm" on:click={() => refreshState()} title="Refresh">🔄</button>
    <button class="btn btn-ghost btn-sm" class:working={saving} disabled={saving} on:click={openSaveModal} title="Save Game">💾</button>
    <button class="btn btn-ghost btn-sm" on:click={() => dispatch('loadsave')} title="Load Save">📂</button>
    <button class="btn btn-ghost btn-sm" on:click={newGame} title="New Game">🆕</button>
    <button class="btn btn-ghost btn-sm notification-btn" on:click={() => dispatch('notifications')} title="Notifications">
      🔔
      {#if $unreadCount > 0}
        <span class="badge">{$unreadCount}</span>
      {/if}
    </button>
  </div>
</div>

{#if showSaveModal}
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <!-- svelte-ignore a11y-no-static-element-interactions -->
  <div class="modal-overlay" on:click|self={() => showSaveModal = false}>
    <div class="save-modal">
      <div class="save-modal-header">
        <h3>💾 Save Game</h3>
        <button class="btn btn-ghost btn-sm" on:click={() => showSaveModal = false}>✕</button>
      </div>
      <div class="save-modal-body">
        <label class="save-label" for="save-name-input">Save name</label>
        <div class="save-input-row">
          <input
            id="save-name-input"
            class="save-input"
            type="text"
            bind:value={saveName}
            placeholder="Enter save name…"
            on:keydown={(e) => e.key === 'Enter' && handleSave()}
          />
          <button class="btn btn-primary" disabled={saving || !saveName.trim()} on:click={handleSave}>
            {saving ? '⏳ Saving…' : '💾 Save'}
          </button>
        </div>

        {#if existingSaves.length > 0}
          <div class="existing-saves">
            <label class="save-label">Or overwrite existing save</label>
            <div class="existing-saves-list">
              {#each existingSaves as save}
                <button class="existing-save-item" on:click={() => overwriteSave(save.name)}>
                  <span class="existing-save-name">{save.name.replace(/\.json$/, '')}</span>
                  <span class="existing-save-meta">{new Date(save.mtime * 1000).toLocaleString()}</span>
                </button>
              {/each}
            </div>
          </div>
        {/if}
      </div>
    </div>
  </div>
{/if}

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
  .btn-tick {
    background: var(--c-accent);
    color: #000;
    font-weight: 700;
    font-size: 13px;
    padding: 6px 14px;
    border-radius: 6px;
    min-width: 48px;
  }
  .btn-tick:hover:not(:disabled) {
    background: #5dd9ff;
    box-shadow: 0 0 8px rgba(76, 201, 240, 0.4);
  }
  .btn-tick:active:not(:disabled) {
    transform: scale(0.9);
    filter: brightness(0.8);
    transition: all 0.04s;
  }
  .btn-tick.working {
    background: var(--c-bg-tertiary);
    color: var(--c-accent);
    animation: tick-pulse 0.8s ease-in-out infinite;
  }
  @keyframes tick-pulse {
    0%, 100% { opacity: 1; box-shadow: 0 0 0 0 rgba(76,201,240,0.4); }
    50% { opacity: 0.7; box-shadow: 0 0 12px 2px rgba(76,201,240,0.3); }
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

  /* ─── Save Modal ─── */
  .modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.6);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
  }
  .save-modal {
    background: var(--c-bg-secondary);
    border: 1px solid var(--c-border);
    border-radius: 12px;
    width: 440px;
    max-width: 90vw;
    max-height: 80vh;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.5);
  }
  .save-modal-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 14px 18px;
    border-bottom: 1px solid var(--c-border);
  }
  .save-modal-header h3 {
    margin: 0;
    font-size: 16px;
  }
  .save-modal-body {
    padding: 18px;
    overflow-y: auto;
  }
  .save-label {
    display: block;
    font-size: 12px;
    color: var(--c-text-secondary);
    margin-bottom: 6px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
  .save-input-row {
    display: flex;
    gap: 8px;
    margin-bottom: 16px;
  }
  .save-input {
    flex: 1;
    padding: 8px 12px;
    border: 1px solid var(--c-border);
    border-radius: 6px;
    background: var(--c-bg);
    color: var(--c-text);
    font-size: 14px;
    outline: none;
  }
  .save-input:focus {
    border-color: var(--c-accent);
    box-shadow: 0 0 0 2px rgba(76, 201, 240, 0.15);
  }
  .existing-saves {
    margin-top: 8px;
  }
  .existing-saves-list {
    display: flex;
    flex-direction: column;
    gap: 4px;
    max-height: 200px;
    overflow-y: auto;
  }
  .existing-save-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 12px;
    border: 1px solid var(--c-border);
    border-radius: 6px;
    background: var(--c-bg);
    color: var(--c-text);
    cursor: pointer;
    font-size: 13px;
    text-align: left;
    transition: background 0.15s;
  }
  .existing-save-item:hover {
    background: var(--c-bg-tertiary);
    border-color: var(--c-accent);
  }
  .existing-save-name {
    font-weight: 600;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 200px;
  }
  .existing-save-meta {
    font-size: 11px;
    color: var(--c-text-muted);
    white-space: nowrap;
  }
</style>
