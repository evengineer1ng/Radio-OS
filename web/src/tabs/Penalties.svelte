<script lang="ts">
  import { gameState } from '../lib/stores'
  import { formatCurrency } from '../lib/utils'

  $: penalties = $gameState.penalties || []
</script>

<div class="penalties-view">
  <div class="card">
    <div class="section-title">⚠️ Penalty History ({penalties.length})</div>
    <div class="penalty-list scroll-y">
      {#each penalties.slice().reverse() as p}
        <div class="penalty-item">
          <div class="penalty-header">
            <span class="penalty-type">{p.type || 'Penalty'}</span>
            <span class="penalty-tick">Tick {p.tick}</span>
          </div>
          <div class="penalty-reason">{p.reason || '—'}</div>
          {#if p.amount}
            <div class="penalty-amount">-{formatCurrency(p.amount)}</div>
          {/if}
        </div>
      {:else}
        <div class="empty-state">No penalties — keep it clean! 👍</div>
      {/each}
    </div>
  </div>
</div>

<style>
  .penalties-view { padding: 12px; }
  .penalty-list { max-height: 500px; display: flex; flex-direction: column; gap: 6px; }
  .penalty-item {
    padding: 10px; background: var(--c-bg-tertiary); border-radius: var(--radius);
    border-left: 3px solid var(--c-warning);
  }
  .penalty-header { display: flex; justify-content: space-between; margin-bottom: 4px; }
  .penalty-type { font-size: 13px; font-weight: 600; color: var(--c-warning); }
  .penalty-tick { font-size: 11px; color: var(--c-text-muted); font-family: var(--font-mono); }
  .penalty-reason { font-size: 12px; color: var(--c-text-secondary); }
  .penalty-amount { font-size: 13px; color: var(--c-danger); font-family: var(--font-mono); font-weight: 600; margin-top: 4px; }
  .empty-state { text-align: center; color: var(--c-text-muted); padding: 30px; font-size: 13px; }
</style>
