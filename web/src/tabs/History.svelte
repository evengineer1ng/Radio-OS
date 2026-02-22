<script lang="ts">
  import { gameState } from '../lib/stores'
  import { formatEventSummary } from '../lib/eventFormat'

  let historyTab: 'decisions' | 'results' | 'transactions' = 'decisions'

  const DECISION_HINTS = ['decision', 'hire', 'fire', 'contract', 'focus', 'budget']
  const TRANSACTION_HINTS = ['financial', 'payment', 'salary', 'prize', 'sponsor', 'penalty', 'expense', 'income', 'cash']

  function toLabel(raw: any, fallback: string): string {
    const s = String(raw || fallback).trim()
    return s ? s.replace(/_/g, ' ') : fallback
  }

  function normalizeFallbackEvent(evt: any, fallbackLabel: string) {
    return {
      id: String(evt?.event_id ?? `${evt?.tick ?? 0}:${evt?.type ?? ''}:${evt?.category ?? ''}`),
      tick: Number(evt?.tick || 0),
      season: Number($gameState?.season_number || 0),
      game_day: null,
      label: toLabel(evt?.category || evt?.type, fallbackLabel),
      description: String(evt?.description || evt?.text || formatEventSummary(evt)),
      detail: '',
      amount: null,
      type: String(evt?.type || '').toLowerCase(),
    }
  }

  $: history = $gameState?.history || {}
  $: events = Array.isArray($gameState?.recent_events) ? $gameState.recent_events : []

  $: feedDecisions = Array.isArray(history?.decisions) ? history.decisions : []
  $: feedResults = Array.isArray(history?.results) ? history.results : []
  $: feedTransactions = Array.isArray(history?.transactions) ? history.transactions : []

  $: fallbackDecisions = events
    .filter((e: any) => {
      const type = String(e?.type || '').toLowerCase()
      const category = String(e?.category || '').toLowerCase()
      return DECISION_HINTS.some(k => type.includes(k) || category.includes(k))
    })
    .map((e: any) => normalizeFallbackEvent(e, 'decision'))

  $: fallbackResults = events
    .filter((e: any) => {
      const type = String(e?.type || '').toLowerCase()
      const category = String(e?.category || '').toLowerCase()
      return category === 'race_result' || category === 'season_end' || type.includes('race')
    })
    .map((e: any) => normalizeFallbackEvent(e, 'result'))

  $: fallbackTransactions = events
    .filter((e: any) => {
      const type = String(e?.type || '').toLowerCase()
      const category = String(e?.category || '').toLowerCase()
      const desc = String(e?.description || '').toLowerCase()
      return TRANSACTION_HINTS.some(k => type.includes(k) || category.includes(k) || desc.includes(k))
    })
    .map((e: any) => normalizeFallbackEvent(e, 'transaction'))

  function amountClass(item: any): string {
    const amount = Number(item?.amount)
    if (!Number.isFinite(amount)) return ''
    if (amount > 0) return 'is-positive'
    if (amount < 0) return 'is-negative'
    return ''
  }

  function sortByTickDesc(rows: any[]): any[] {
    return rows
      .slice()
      .sort((a: any, b: any) => Number(b?.tick || 0) - Number(a?.tick || 0))
  }

  $: decisions = sortByTickDesc(feedDecisions.length > 0 ? feedDecisions : fallbackDecisions)
  $: results = sortByTickDesc(feedResults.length > 0 ? feedResults : fallbackResults)
  $: transactions = sortByTickDesc(feedTransactions.length > 0 ? feedTransactions : fallbackTransactions)
</script>

<div class="history-view">
  <div class="tab-bar">
    <button class="tab-btn" class:active={historyTab === 'decisions'} on:click={() => historyTab = 'decisions'}>
      Decisions ({decisions.length})
    </button>
    <button class="tab-btn" class:active={historyTab === 'results'} on:click={() => historyTab = 'results'}>
      Results ({results.length})
    </button>
    <button class="tab-btn" class:active={historyTab === 'transactions'} on:click={() => historyTab = 'transactions'}>
      Transactions ({transactions.length})
    </button>
  </div>

  <div class="card history-list scroll-y">
    {#each (historyTab === 'decisions' ? decisions : historyTab === 'results' ? results : transactions) as evt}
      <div class="history-item">
        <div class="h-header">
          <span class="h-type">{evt?.label || evt?.type || '•'}</span>
          <span class="h-tick">Tick {evt?.tick || '?'}</span>
        </div>
        <div class="h-desc">{evt?.description || formatEventSummary(evt)}</div>
        {#if evt?.detail}
          <div class="h-detail {amountClass(evt)}">{evt.detail}</div>
        {/if}
        {#if evt?.season || evt?.game_day}
          <div class="h-meta">
            {#if evt?.season}Season {evt.season}{/if}
            {#if evt?.season && evt?.game_day} • {/if}
            {#if evt?.game_day}Day {evt.game_day}{/if}
          </div>
        {/if}
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
    padding: 8px;
    border-bottom: 1px solid var(--c-border);
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .h-header { display: flex; justify-content: space-between; margin-bottom: 2px; gap: 8px; }
  .h-type { font-size: 11px; font-weight: 600; color: var(--c-accent); text-transform: uppercase; }
  .h-tick { font-size: 11px; color: var(--c-text-muted); font-family: var(--font-mono); }
  .h-desc { font-size: 12px; color: var(--c-text-secondary); }
  .h-detail { font-size: 12px; color: var(--c-text-primary); }
  .h-detail.is-positive { color: var(--c-success); }
  .h-detail.is-negative { color: var(--c-danger); }
  .h-meta { font-size: 11px; color: var(--c-text-muted); font-family: var(--font-mono); }
  .empty-state { text-align: center; color: var(--c-text-muted); padding: 30px; font-size: 13px; }
</style>
