<script lang="ts">
  import { gameState } from '../lib/stores'
  import { formatCurrency } from '../lib/utils'
  import MetricDisplay from '../components/MetricDisplay.svelte'

  $: team = $gameState.player_team
  $: budget = team?.budget || {}
  $: cash = budget.cash || 0
  $: expenses = budget.weekly_expenses || 0
  $: income = budget.weekly_income || 0
  $: runway = expenses > 0 ? Math.floor(cash / expenses) : 999
  $: net = income - expenses

  $: sponsorships = (() => {
    const teamName = team?.name || ''
    const all = $gameState.sponsorships || {}
    return all[teamName] || []
  })()
</script>

<div class="finance-view">
  <div class="metrics-row">
    <MetricDisplay label="Current Cash" value={formatCurrency(cash)} color="var(--c-accent)" />
    <MetricDisplay label="Weekly Burn" value={formatCurrency(expenses)} color="var(--c-danger)" />
    <MetricDisplay label="Runway" value="{runway}w" color={runway < 8 ? 'var(--c-danger)' : 'var(--c-success)'} />
  </div>

  <div class="card">
    <div class="section-title">📊 Weekly Breakdown</div>
    <div class="breakdown">
      <div class="br-item"><span>Income</span><span class="positive">+{formatCurrency(income)}</span></div>
      <div class="br-item"><span>Expenses</span><span class="negative">-{formatCurrency(expenses)}</span></div>
      <div class="br-item total"><span>Net</span><span class={net >= 0 ? 'positive' : 'negative'}>{net >= 0 ? '+' : ''}{formatCurrency(net)}</span></div>
    </div>
  </div>

  <div class="card">
    <div class="section-title">💵 Sponsor Income</div>
    {#each sponsorships as sp}
      <div class="sponsor-item">
        <span class="sp-name">{sp.name}</span>
        <span class="sp-value">{formatCurrency(sp.value || 0)}/yr</span>
        <span class="sp-duration">{sp.seasons_remaining} seasons</span>
      </div>
    {:else}
      <div class="empty-state">No sponsorships</div>
    {/each}
  </div>
</div>

<style>
  .finance-view { display: flex; flex-direction: column; gap: 12px; padding: 12px; }
  .metrics-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
  .breakdown { display: flex; flex-direction: column; gap: 4px; }
  .br-item { display: flex; justify-content: space-between; font-size: 13px; padding: 6px 0; border-bottom: 1px solid var(--c-border); }
  .br-item.total { font-weight: 700; border-top: 2px solid var(--c-border); margin-top: 4px; padding-top: 8px; }
  .positive { color: var(--c-success); font-family: var(--font-mono); }
  .negative { color: var(--c-danger); font-family: var(--font-mono); }
  .sponsor-item { display: flex; justify-content: space-between; align-items: center; padding: 6px 0; font-size: 12px; border-bottom: 1px solid var(--c-border); }
  .sp-name { font-weight: 500; }
  .sp-value { color: var(--c-success); font-family: var(--font-mono); }
  .sp-duration { color: var(--c-text-muted); }
  .empty-state { text-align: center; color: var(--c-text-muted); padding: 20px; font-size: 13px; }
  @media (max-width: 480px) { .metrics-row { grid-template-columns: 1fr; } }
</style>
