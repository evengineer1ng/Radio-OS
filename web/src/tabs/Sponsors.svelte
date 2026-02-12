<script lang="ts">
  import { gameState } from '../lib/stores'
  import { formatCurrency } from '../lib/utils'

  $: team = $gameState.player_team
  $: teamName = team?.name || ''
  $: sponsors = ($gameState.sponsorships || {})[teamName] || []
  $: pendingOffers = ($gameState.pending_sponsor_offers || {})[teamName] || []
</script>

<div class="sponsors-view">
  <div class="card">
    <div class="section-title">🏢 Current Sponsors ({sponsors.length})</div>
    <div class="sponsor-list">
      {#each sponsors as sp}
        <div class="sponsor-card">
          <div class="sp-name">{sp.name}</div>
          <div class="sp-details">
            <span class="sp-value">{formatCurrency(sp.value || 0)}/yr</span>
            <span class="sp-duration">{sp.seasons_remaining} seasons left</span>
          </div>
        </div>
      {:else}
        <div class="empty-state">No sponsors</div>
      {/each}
    </div>
  </div>

  {#if pendingOffers.length}
    <div class="card">
      <div class="section-title">📨 Pending Offers ({pendingOffers.length})</div>
      {#each pendingOffers as offer}
        <div class="sponsor-card offer">
          <div class="sp-name">{offer.name}</div>
          <div class="sp-details">
            <span class="sp-value">{formatCurrency(offer.value || 0)}/yr</span>
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .sponsors-view { display: flex; flex-direction: column; gap: 12px; padding: 12px; }
  .sponsor-list { display: flex; flex-direction: column; gap: 6px; }
  .sponsor-card {
    padding: 10px; background: var(--c-bg-tertiary); border-radius: var(--radius);
    display: flex; justify-content: space-between; align-items: center;
  }
  .sponsor-card.offer { border: 1px dashed var(--c-accent-dim); }
  .sp-name { font-size: 13px; font-weight: 600; }
  .sp-details { display: flex; gap: 12px; font-size: 12px; }
  .sp-value { color: var(--c-success); font-family: var(--font-mono); }
  .sp-duration { color: var(--c-text-muted); }
  .empty-state { text-align: center; color: var(--c-text-muted); padding: 20px; font-size: 13px; }
</style>
