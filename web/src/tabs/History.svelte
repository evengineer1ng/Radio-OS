<script lang="ts">
  import { gameState } from '../lib/stores'
  import { formatCurrency } from '../lib/utils'

  $: events = $gameState.recent_events || []
  $: pending = $gameState.pending_decisions || []

  let historyTab: 'decisions' | 'results' | 'transactions' = 'decisions'

  // Categorize events
  $: decisions = events.filter((e: any) => ['hire', 'fire', 'contract', 'focus', 'budget'].some(k => (e.type || '').toLowerCase().includes(k)))
  $: results = events.filter((e: any) => (e.type || '').toLowerCase().includes('race'))
  $: transactions = events.filter((e: any) => ['financial', 'payment', 'penalty', 'prize', 'salary', 'sponsor'].some(k => (e.type || '').toLowerCase().includes(k)))
</script>

<div class="history-view">
  <div class="tab-bar">
    <button class="tab-btn" class:active={historyTab === 'decisions'} on:click={() => historyTab = 'decisions'}>Decisions ({decisions.length})</button>
    <button class="tab-btn" class:active={historyTab === 'results'} on:click={() => historyTab = 'results'}>Results ({results.length})</button>
    <button class="tab-btn" class:active={historyTab === 'transactions'} on:click={() => historyTab = 'transactions'}>Transactions ({transactions.length})</button>
  </div>

  <div class="card history-list scroll-y">
    {#each (historyTab === 'decisions' ? decisions : historyTab === 'results' ? results : transactions).slice().reverse() as evt}
      <div class="history-item">
        <div class="h-header">
          <span class="h-type">{evt.type || '•'}</span>
          <span class="h-tick">Tick {evt.tick || '?'}</span>
        </div>
        <div class="h-desc">{evt.description || JSON.stringify(evt)}</div>
      </div>
    {:else}
      <div class="empty-state">No {historyTab} recorded</div>
    {/each}
  </div>
</div>

<style>
  .history-view { display: flex; flex-direction: column; gap: 0; padding: 12px; }
  .history-list { max-height: 600px; margin-top: 8px; }
  .history-item {
    padding: 8px; border-bottom: 1px solid var(--c-border);
  }
  .h-header { display: flex; justify-content: space-between; margin-bottom: 2px; }
  .h-type { font-size: 11px; font-weight: 600; color: var(--c-accent); text-transform: uppercase; }
  .h-tick { font-size: 11px; color: var(--c-text-muted); font-family: var(--font-mono); }
  .h-desc { font-size: 12px; color: var(--c-text-secondary); }
  .empty-state { text-align: center; color: var(--c-text-muted); padding: 30px; font-size: 13px; }
</style>
