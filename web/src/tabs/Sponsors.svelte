<script lang="ts">
  import { gameState, addToast } from '../lib/stores'
  import { formatCurrency } from '../lib/utils'
  import { acceptSponsor, declineSponsor, safeRefreshState } from '../lib/api'

  $: team = $gameState.player_team
  $: standingMetrics = team?.standing_metrics || {}
  $: teamName = team?.name || ''
  $: sponsors = ($gameState.sponsorships || {})[teamName] || []
  $: pendingOffers = ($gameState.pending_sponsor_offers || {})[teamName] || []
  $: reputation = Number(standingMetrics?.reputation ?? 50)
  $: avgConfidence = sponsors.length
    ? sponsors.reduce((sum: number, sp: any) => sum + Number(sp.confidence ?? 100), 0) / sponsors.length
    : 0
  $: atRiskSponsors = sponsors.filter((sp: any) => Number(sp.confidence ?? 100) < 40).length

  let working = false
  async function handleAccept(index: number) {
    if (working) return
    working = true
    try {
      await acceptSponsor(index)
      await new Promise(r => setTimeout(r, 500))
      await safeRefreshState()
      addToast('Sponsor accepted ✅', 'success')
    } catch (e) { console.error('accept sponsor', e); addToast('Accept failed', 'error') }
    working = false
  }
  async function handleDecline(index: number) {
    if (working) return
    working = true
    try {
      await declineSponsor(index)
      await new Promise(r => setTimeout(r, 500))
      await safeRefreshState()
      addToast('Sponsor declined', 'success')
    } catch (e) { console.error('decline sponsor', e); addToast('Decline failed', 'error') }
    working = false
  }
</script>

<div class="sponsors-view">
  <div class="card summary-card">
    <div class="summary-item">
      <span class="summary-label">Team Reputation</span>
      <span class="summary-value">{Math.round(reputation)}%</span>
    </div>
    <div class="summary-item">
      <span class="summary-label">Sponsor Health</span>
      <span class="summary-value" class:warn={avgConfidence < 50}>{sponsors.length ? `${Math.round(avgConfidence)}%` : 'No sponsors'}</span>
    </div>
    <div class="summary-item">
      <span class="summary-label">At Risk</span>
      <span class="summary-value" class:warn={atRiskSponsors > 0}>{atRiskSponsors}</span>
    </div>
  </div>

  <div class="card">
    <div class="section-title">🏢 Current Sponsors ({sponsors.length})</div>
    <div class="sponsor-list">
      {#each sponsors as sp}
        <div class="sponsor-card">
          <div class="sp-name">{sp.name}</div>
          <div class="sp-details">
            <span class="sp-value">{formatCurrency(sp.value || 0)}/yr</span>
            <span class="sp-duration">{sp.seasons_remaining} season{sp.seasons_remaining !== 1 ? 's' : ''} left</span>
            {#if sp.confidence < 100}
              <span class="sp-confidence" class:low={sp.confidence < 50}>{Math.round(sp.confidence)}% confidence</span>
            {/if}
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
              {#if offer.seasons_remaining}<span class="sp-duration">{offer.seasons_remaining} season{offer.seasons_remaining > 1 ? 's' : ''}</span>{/if}
              {#if offer.confidence}<span class="sp-confidence">{Math.round(offer.confidence)}% confidence</span>{/if}
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
  .summary-card {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
  }
  .summary-item {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 8px;
    border: 1px solid var(--c-border);
    border-radius: var(--radius-sm);
    background: var(--c-bg-tertiary);
  }
  .summary-label {
    font-size: 11px;
    color: var(--c-text-muted);
    text-transform: uppercase;
    letter-spacing: 0.3px;
  }
  .summary-value {
    font-size: 15px;
    font-weight: 700;
    color: var(--c-accent);
    font-family: var(--font-mono);
  }
  .summary-value.warn {
    color: var(--c-danger);
  }
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
  .sp-confidence.low { color: var(--c-danger); }
  .empty-state { text-align: center; color: var(--c-text-muted); padding: 20px; font-size: 13px; }
  @media (max-width: 640px) {
    .summary-card {
      grid-template-columns: 1fr;
    }
  }
</style>
