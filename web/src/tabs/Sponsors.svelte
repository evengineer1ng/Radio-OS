<script lang="ts">
  import { gameState } from '../lib/stores'
  import { formatCurrency } from '../lib/utils'
  import { acceptSponsor, declineSponsor, fetchState } from '../lib/api'

  $: team = $gameState.player_team
  $: teamName = team?.name || ''
  $: sponsors = ($gameState.sponsorships || {})[teamName] || []
  $: pendingOffers = ($gameState.pending_sponsor_offers || {})[teamName] || []

  let working = false
  async function handleAccept(index: number) {
    if (working) return
    working = true
    try {
      await acceptSponsor(index)
      gameState.set(await fetchState())
    } catch (e) { console.error('accept sponsor', e) }
    working = false
  }
  async function handleDecline(index: number) {
    if (working) return
    working = true
    try {
      await declineSponsor(index)
      gameState.set(await fetchState())
    } catch (e) { console.error('decline sponsor', e) }
    working = false
  }
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
      {#each pendingOffers as offer, i}
        <div class="sponsor-card offer">
          <div class="offer-info">
            <div class="sp-name">{offer.name}</div>
            <div class="sp-details">
              <span class="sp-value">{formatCurrency(offer.value || 0)}/yr</span>
              {#if offer.seasons}<span class="sp-duration">{offer.seasons} season{offer.seasons > 1 ? 's' : ''}</span>{/if}
              {#if offer.confidence}<span class="sp-confidence">{Math.round(offer.confidence * 100)}% confidence</span>{/if}
            </div>
          </div>
          <div class="offer-actions">
            <button class="btn btn-primary btn-sm" disabled={working} on:click={() => handleAccept(offer.index ?? i)}>✅ Accept</button>
            <button class="btn btn-ghost btn-sm" disabled={working} on:click={() => handleDecline(offer.index ?? i)}>❌ Decline</button>
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
  .sponsor-card.offer { border: 1px dashed var(--c-accent-dim); flex-direction: column; gap: 8px; align-items: stretch; }
  .offer-info { display: flex; justify-content: space-between; align-items: center; }
  .offer-actions { display: flex; gap: 8px; justify-content: flex-end; }
  .sp-name { font-size: 13px; font-weight: 600; }
  .sp-details { display: flex; gap: 12px; font-size: 12px; }
  .sp-value { color: var(--c-success); font-family: var(--font-mono); }
  .sp-duration { color: var(--c-text-muted); }
  .sp-confidence { color: var(--c-accent); font-size: 11px; }
  .empty-state { text-align: center; color: var(--c-text-muted); padding: 20px; font-size: 13px; }
</style>
