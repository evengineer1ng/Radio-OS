<script lang="ts">
  import { gameState } from '../lib/stores'
  import { applyPromotion, declinePromotion } from '../lib/api'

  let busyOpportunityId = ''
  let actionMessage = ''
  let actionError = ''

  $: team = $gameState.player_team
  $: cash = Number(team?.budget?.cash || 0)
  $: nowTick = Number($gameState.tick || 0)
  $: rawOpportunities = Array.isArray($gameState.promotion_opportunities)
    ? $gameState.promotion_opportunities
    : []

  $: opportunities = [...rawOpportunities].sort(
    (a: any, b: any) => Number(b?.created_tick || 0) - Number(a?.created_tick || 0),
  )

  function normalizedStatus(opp: any): string {
    const status = String(opp?.status || 'open').toLowerCase()
    const expiresTick = Number(opp?.expires_tick || 0)
    if (status === 'open' && expiresTick > 0 && nowTick > expiresTick) return 'expired'
    return status
  }

  function statusLabel(status: string): string {
    if (status === 'open') return 'OPEN'
    if (status === 'applied') return 'APPLIED'
    if (status === 'promoted') return 'PROMOTED'
    if (status === 'declined') return 'DECLINED'
    if (status === 'expired') return 'EXPIRED'
    return status.toUpperCase()
  }

  function statusClass(status: string): string {
    if (status === 'open') return 'is-open'
    if (status === 'applied') return 'is-applied'
    if (status === 'promoted') return 'is-promoted'
    if (status === 'declined') return 'is-declined'
    if (status === 'expired') return 'is-expired'
    return ''
  }

  async function onApply(opp: any) {
    const opportunityId = String(opp?.opportunity_id || '')
    if (!opportunityId || busyOpportunityId) return
    actionError = ''
    actionMessage = ''
    busyOpportunityId = opportunityId
    try {
      const res = await applyPromotion(opportunityId)
      if (res?.error) {
        actionError = String(res.error)
      } else {
        actionMessage = 'Promotion application submitted.'
      }
    } catch (e: any) {
      actionError = String(e?.message || e || 'Failed to apply for promotion')
    } finally {
      busyOpportunityId = ''
    }
  }

  async function onDecline(opp: any) {
    const opportunityId = String(opp?.opportunity_id || '')
    if (!opportunityId || busyOpportunityId) return
    actionError = ''
    actionMessage = ''
    busyOpportunityId = opportunityId
    try {
      const res = await declinePromotion(opportunityId)
      if (res?.error) {
        actionError = String(res.error)
      } else {
        actionMessage = 'Promotion opportunity declined.'
      }
    } catch (e: any) {
      actionError = String(e?.message || e || 'Failed to decline promotion')
    } finally {
      busyOpportunityId = ''
    }
  }
</script>

<div class="promotion-tab">
  <div class="card">
    <div class="section-title">📈 Team Promotion</div>
    {#if team}
      <div class="summary">{team.name} • Cash: ${Math.round(cash).toLocaleString()}</div>
    {:else}
      <div class="summary">No active team loaded</div>
    {/if}
  </div>

  {#if actionMessage}
    <div class="card notice success">{actionMessage}</div>
  {/if}
  {#if actionError}
    <div class="card notice error">{actionError}</div>
  {/if}

  {#if !team}
    <div class="card empty">Start or load a game to view promotion opportunities.</div>
  {:else if opportunities.length === 0}
    <div class="card empty">No promotion opportunities yet. Finish high in your championship to unlock one.</div>
  {:else}
    {#each opportunities as opp}
      {@const status = normalizedStatus(opp)}
      {@const entryFee = Number(opp?.entry_fee || 0)}
      {@const canAfford = entryFee <= 0 || cash >= entryFee}
      {@const canAct = status === 'open'}
      <div class="card opp-card">
        <div class="opp-head">
          <div class="opp-title">Season {Number(opp?.season || 0)} • {opp?.league_name || opp?.league_id || 'League'}</div>
          <div class={`badge ${statusClass(status)}`}>{statusLabel(status)}</div>
        </div>

        <div class="opp-line">
          P{Number(opp?.position || 0)} • {Math.round(Number(opp?.points || 0))} pts • Eligibility {Math.round(Number(opp?.eligibility_score || 0))}/100
        </div>
        <div class="opp-line">
          {opp?.from_tier_name || 'Current tier'} → {opp?.to_tier_name || 'Next tier'}
        </div>
        <div class="opp-fee">
          {#if entryFee > 0}
            Entry fee: ${Math.round(entryFee).toLocaleString()}
          {:else}
            No entry fee (invited)
          {/if}
        </div>

        {#if canAct}
          <div class="actions">
            <button
              class="btn btn-primary"
              disabled={Boolean(busyOpportunityId) || !canAfford}
              on:click={() => onApply(opp)}
            >
              {canAfford ? 'Apply For Promotion' : 'Insufficient Cash'}
            </button>
            <button
              class="btn btn-ghost"
              disabled={Boolean(busyOpportunityId)}
              on:click={() => onDecline(opp)}
            >
              Decline
            </button>
          </div>
        {/if}

        {#if !canAct && opp?.message}
          <div class="opp-msg">{opp.message}</div>
        {/if}
      </div>
    {/each}
  {/if}
</div>

<style>
  .promotion-tab { display: flex; flex-direction: column; gap: 10px; padding: 12px; }
  .summary { color: var(--c-text-muted); font-size: 12px; }
  .notice { font-size: 12px; }
  .notice.success { border-left: 3px solid var(--c-success); }
  .notice.error { border-left: 3px solid var(--c-danger); }
  .empty { color: var(--c-text-muted); font-size: 13px; }
  .opp-card { display: flex; flex-direction: column; gap: 6px; }
  .opp-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  .opp-title { font-size: 13px; font-weight: 700; color: var(--c-text-primary); }
  .badge {
    font-size: 10px;
    font-weight: 700;
    padding: 3px 8px;
    border-radius: 999px;
    border: 1px solid var(--c-border);
    color: var(--c-text-muted);
    background: var(--c-bg-tertiary);
  }
  .badge.is-open { color: var(--c-success); border-color: #3e8f61; }
  .badge.is-applied { color: var(--c-info); border-color: #4b77a7; }
  .badge.is-promoted { color: var(--c-success); border-color: #3e8f61; }
  .badge.is-declined { color: var(--c-text-muted); }
  .badge.is-expired { color: var(--c-warning); border-color: #8b6a2a; }
  .opp-line { font-size: 12px; color: var(--c-text-secondary); }
  .opp-fee { font-size: 12px; color: var(--c-text-muted); }
  .actions { display: flex; gap: 8px; margin-top: 4px; }
  .opp-msg { font-size: 11px; color: var(--c-text-muted); }
</style>
