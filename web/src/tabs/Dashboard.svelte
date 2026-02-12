<script lang="ts">
  import { gameState } from '../lib/stores'
  import { formatCurrency } from '../lib/utils'
  import MetricDisplay from '../components/MetricDisplay.svelte'

  $: team = $gameState.player_team
  $: budget = team?.budget || {}
  $: events = $gameState.recent_events || []
  $: personalEvents = events.filter((e: any) => e.category !== 'world')
  $: worldEvents = events.filter((e: any) => e.category === 'world')

  // Pressure indicators
  $: cash = budget.cash || 0
  $: weeklyBurn = budget.weekly_expenses || 0
  $: runway = weeklyBurn > 0 ? Math.floor(cash / weeklyBurn) : 999

  let eventTab: 'personal' | 'world' = 'personal'
</script>

<div class="dashboard">
  <!-- Pressure Indicators -->
  <div class="section-title">📊 Pressure Indicators</div>
  <div class="metrics-row">
    <MetricDisplay
      label="Cash Runway"
      value="{runway}w"
      sublabel={runway < 8 ? '⚠️ Critical' : 'Stable'}
      color={runway < 8 ? 'var(--c-danger)' : runway < 20 ? 'var(--c-warning)' : 'var(--c-success)'}
    />
    <MetricDisplay
      label="Budget"
      value={formatCurrency(cash)}
      sublabel="Current balance"
      color="var(--c-accent)"
    />
    <MetricDisplay
      label="Phase"
      value={$gameState.phase || '—'}
      color="var(--c-info)"
    />
  </div>

  {#if team}
    <!-- Team Info -->
    <div class="card team-info">
      <div class="section-title">🏁 {team.name || 'Your Team'}</div>
      <div class="info-grid">
        <div class="info-item">
          <span class="info-label">League</span>
          <span class="info-value">{$gameState.leagues ? Object.keys($gameState.leagues).find(l => {
            const league = $gameState.leagues[l]
            return league.team_names?.includes(team.name)
          }) || '—' : '—'}</span>
        </div>
        <div class="info-item">
          <span class="info-label">Budget</span>
          <span class="info-value">{formatCurrency(cash)}</span>
        </div>
        <div class="info-item">
          <span class="info-label">Drivers</span>
          <span class="info-value">{(team.roster?.drivers || []).length}</span>
        </div>
        <div class="info-item">
          <span class="info-label">Control</span>
          <span class="info-value">{$gameState.control_mode}</span>
        </div>
      </div>
    </div>
  {/if}

  <!-- Event Log -->
  <div class="card event-log-card">
    <div class="section-title">📰 Event Log</div>
    <div class="event-tabs">
      <button class="tab-btn" class:active={eventTab === 'personal'} on:click={() => eventTab = 'personal'}>
        Personal ({personalEvents.length})
      </button>
      <button class="tab-btn" class:active={eventTab === 'world'} on:click={() => eventTab = 'world'}>
        World ({worldEvents.length})
      </button>
    </div>
    <div class="event-list scroll-y">
      {#each (eventTab === 'personal' ? personalEvents : worldEvents).slice(-20).reverse() as evt}
        <div class="event-item">
          <span class="event-type">{evt.type || '•'}</span>
          <span class="event-desc">{evt.description || JSON.stringify(evt)}</span>
        </div>
      {:else}
        <div class="empty-state">No events yet</div>
      {/each}
    </div>
  </div>
</div>

<style>
  .dashboard { display: flex; flex-direction: column; gap: 12px; padding: 12px; }
  .metrics-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
  .info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
  .info-item { display: flex; justify-content: space-between; font-size: 12px; padding: 4px 0; }
  .info-label { color: var(--c-text-muted); }
  .info-value { color: var(--c-text-primary); font-weight: 500; }
  .event-log-card { flex: 1; display: flex; flex-direction: column; min-height: 0; }
  .event-tabs { display: flex; gap: 4px; margin-bottom: 8px; }
  .event-list { flex: 1; min-height: 0; max-height: 300px; }
  .event-item {
    padding: 6px 8px;
    font-size: 12px;
    border-bottom: 1px solid var(--c-border);
    display: flex;
    gap: 8px;
  }
  .event-type {
    color: var(--c-accent);
    font-weight: 600;
    font-size: 11px;
    white-space: nowrap;
    flex-shrink: 0;
  }
  .event-desc { color: var(--c-text-secondary); }
  .empty-state {
    text-align: center;
    color: var(--c-text-muted);
    padding: 24px;
    font-size: 13px;
  }
  @media (max-width: 480px) {
    .metrics-row { grid-template-columns: 1fr; }
  }
</style>
