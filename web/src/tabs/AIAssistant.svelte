<script lang="ts">
  import { gameState } from '../lib/stores'
  import { sendCommand } from '../lib/ws'

  $: delegation = $gameState.delegation_settings || {}
  $: focus = $gameState.delegation_focus
  $: controlMode = $gameState.control_mode

  let focusText = ''

  function delegate() {
    sendCommand({ cmd: 'ftb_delegate' })
  }
  function regainControl() {
    sendCommand({ cmd: 'ftb_regain_control' })
  }
  function applyFocus() {
    if (focusText.trim()) {
      sendCommand({ cmd: 'ftb_apply_focus', focus_text: focusText.trim() })
    }
  }
  function clearFocus() {
    sendCommand({ cmd: 'ftb_clear_focus' })
    focusText = ''
  }
</script>

<div class="ai-view">
  <!-- Status & Control -->
  <div class="card">
    <div class="section-title">🤖 AI Delegation Status</div>
    <div class="mode-badge" class:delegated={controlMode === 'delegated'}>
      {controlMode === 'delegated' ? '🟢 AI ACTIVE — DELEGATED' : '🔵 MANUAL CONTROL'}
    </div>
    <div class="control-btns">
      {#if controlMode !== 'delegated'}
        <button class="btn btn-primary" on:click={delegate}>Enable AI Delegation</button>
      {:else}
        <button class="btn btn-danger" on:click={regainControl}>Regain Control</button>
      {/if}
    </div>
  </div>

  <!-- Focus -->
  <div class="card">
    <div class="section-title">🎯 Delegation Focus</div>
    {#if focus}
      <div class="current-focus">
        <strong>Current:</strong> {focus.text || '—'}
      </div>
    {/if}
    <div class="focus-input">
      <input type="text" placeholder="e.g. 'Focus on developing young drivers'" bind:value={focusText} />
      <button class="btn btn-primary btn-sm" on:click={applyFocus}>Apply</button>
      <button class="btn btn-ghost btn-sm" on:click={clearFocus}>Clear</button>
    </div>
  </div>
</div>

<style>
  .ai-view { display: flex; flex-direction: column; gap: 12px; padding: 12px; }
  .mode-badge {
    text-align: center; padding: 12px; border-radius: var(--radius);
    font-weight: 600; font-size: 14px;
    background: var(--c-bg-tertiary); margin-bottom: 12px;
  }
  .mode-badge.delegated { color: var(--c-success); }
  .control-btns { display: flex; gap: 8px; }
  .current-focus {
    font-size: 13px; color: var(--c-text-secondary);
    padding: 8px; background: var(--c-bg-tertiary); border-radius: var(--radius);
    margin-bottom: 8px;
  }
  .focus-input { display: flex; gap: 6px; align-items: center; }
  .focus-input input {
    flex: 1; padding: 8px 12px; border: 1px solid var(--c-border);
    border-radius: var(--radius); background: var(--c-bg-input);
    color: var(--c-text-primary); font-family: var(--font); font-size: 13px;
  }
</style>
