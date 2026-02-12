<script lang="ts">
  import { gameState } from '../lib/stores'
  import { sendCommand } from '../lib/ws'
  import EntityCard from '../components/EntityCard.svelte'
  import { formatCurrency } from '../lib/utils'

  $: team = $gameState.player_team
  $: roster = team?.roster || {}
  $: budget = team?.budget || {}
  $: freeAgents = $gameState.free_agents || []
  $: jobBoard = $gameState.job_board || []
  $: aiTeams = $gameState.ai_teams || []

  let marketTab: string = 'free_drivers'

  function fireEntity(name: string) {
    if (confirm(`Fire ${name}? This cannot be undone.`)) {
      sendCommand({ cmd: 'ftb_fire_entity', entity_name: name, confirmed: true })
    }
  }

  function hireAgent(agentId: number) {
    sendCommand({ cmd: 'ftb_hire_free_agent', free_agent_id: agentId })
  }

  function applyJob(listingId: number) {
    sendCommand({ cmd: 'ftb_apply_job', listing_id: listingId })
  }

  // Split free agents by type
  $: faDrivers = freeAgents.filter((e: any) => (e.type || '').includes('Driver'))
  $: faEngineers = freeAgents.filter((e: any) => (e.type || '').includes('Engineer'))
  $: faMechanics = freeAgents.filter((e: any) => (e.type || '').includes('Mechanic'))
  $: faStrategists = freeAgents.filter((e: any) => (e.type || '').includes('Strategist'))
  $: faPrincipals = freeAgents.filter((e: any) => (e.type || '').includes('Principal'))
</script>

<div class="team-view">
  <!-- Financial Overview -->
  {#if team}
    <div class="card">
      <div class="section-title">💰 Financial Overview</div>
      <div class="finance-grid">
        <div><span class="label">Cash</span> <span class="val">{formatCurrency(budget.cash || 0)}</span></div>
        <div><span class="label">Weekly Expenses</span> <span class="val">{formatCurrency(budget.weekly_expenses || 0)}</span></div>
        <div><span class="label">Weekly Income</span> <span class="val">{formatCurrency(budget.weekly_income || 0)}</span></div>
      </div>
    </div>
  {/if}

  <!-- Current Roster -->
  <div class="card">
    <div class="section-title">👥 Current Roster</div>
    <div class="roster-grid">
      {#if roster.drivers}
        {#each (Array.isArray(roster.drivers) ? roster.drivers : [roster.drivers]) as driver}
          {#if driver}
            <EntityCard entity={driver} onFire={() => fireEntity(driver.name)} />
          {/if}
        {/each}
      {/if}
      {#if roster.engineers}
        {#each (Array.isArray(roster.engineers) ? roster.engineers : [roster.engineers]) as eng}
          {#if eng}
            <EntityCard entity={eng} onFire={() => fireEntity(eng.name)} />
          {/if}
        {/each}
      {/if}
      {#if roster.mechanics}
        {#each (Array.isArray(roster.mechanics) ? roster.mechanics : [roster.mechanics]) as mech}
          {#if mech}
            <EntityCard entity={mech} compact onFire={() => fireEntity(mech.name)} />
          {/if}
        {/each}
      {/if}
      {#if roster.strategist}
        <EntityCard entity={roster.strategist} compact onFire={() => fireEntity(roster.strategist.name)} />
      {/if}
      {#if roster.principal}
        <EntityCard entity={roster.principal} compact onFire={() => fireEntity(roster.principal.name)} />
      {/if}
    </div>
  </div>

  <!-- Job Market -->
  <div class="card">
    <div class="section-title">📋 Job Market</div>
    <div class="tab-bar">
      <button class="tab-btn" class:active={marketTab === 'jobs'} on:click={() => marketTab = 'jobs'}>Openings ({jobBoard.length})</button>
      <button class="tab-btn" class:active={marketTab === 'free_drivers'} on:click={() => marketTab = 'free_drivers'}>Drivers ({faDrivers.length})</button>
      <button class="tab-btn" class:active={marketTab === 'free_engineers'} on:click={() => marketTab = 'free_engineers'}>Engineers ({faEngineers.length})</button>
      <button class="tab-btn" class:active={marketTab === 'free_mechanics'} on:click={() => marketTab = 'free_mechanics'}>Mechanics ({faMechanics.length})</button>
      <button class="tab-btn" class:active={marketTab === 'free_strategists'} on:click={() => marketTab = 'free_strategists'}>Strategists ({faStrategists.length})</button>
    </div>
    <div class="market-list scroll-y">
      {#if marketTab === 'jobs'}
        {#each jobBoard as job}
          <div class="market-item">
            <div class="market-info">
              <div class="market-name">{job.team_name}</div>
              <div class="market-meta">{job.role}</div>
            </div>
            <button class="btn btn-primary btn-sm" on:click={() => applyJob(job.id)}>Apply</button>
          </div>
        {:else}
          <div class="empty-state">No openings</div>
        {/each}
      {:else}
        {@const agents = marketTab === 'free_drivers' ? faDrivers :
                         marketTab === 'free_engineers' ? faEngineers :
                         marketTab === 'free_mechanics' ? faMechanics :
                         marketTab === 'free_strategists' ? faStrategists : faPrincipals}
        {#each agents.slice(0, 30) as agent}
          <EntityCard entity={agent} compact />
        {:else}
          <div class="empty-state">No free agents</div>
        {/each}
      {/if}
    </div>
  </div>

  <!-- Browse Teams -->
  <div class="card">
    <div class="section-title">🏁 Browse Teams ({aiTeams.length})</div>
    <div class="teams-list scroll-y">
      {#each aiTeams as t}
        <details class="team-item">
          <summary>{t.name} — {formatCurrency(t.budget?.cash || 0)}</summary>
          <div class="team-details">
            {#if t.roster?.drivers}
              {#each (Array.isArray(t.roster.drivers) ? t.roster.drivers : [t.roster.drivers]) as d}
                {#if d}
                  <EntityCard entity={d} compact />
                {/if}
              {/each}
            {/if}
          </div>
        </details>
      {/each}
    </div>
  </div>
</div>

<style>
  .team-view { display: flex; flex-direction: column; gap: 12px; padding: 12px; }
  .finance-grid { display: flex; flex-direction: column; gap: 4px; }
  .finance-grid div { display: flex; justify-content: space-between; font-size: 12px; padding: 3px 0; }
  .label { color: var(--c-text-muted); }
  .val { color: var(--c-text-primary); font-weight: 500; font-family: var(--font-mono); }
  .roster-grid { display: flex; flex-direction: column; gap: 8px; }
  .market-list { max-height: 400px; }
  .market-item {
    display: flex; align-items: center; justify-content: space-between;
    padding: 8px; border-bottom: 1px solid var(--c-border);
  }
  .market-name { font-size: 13px; font-weight: 500; }
  .market-meta { font-size: 11px; color: var(--c-text-muted); }
  .teams-list { max-height: 400px; }
  .team-item { padding: 6px 0; border-bottom: 1px solid var(--c-border); }
  .team-item summary { font-size: 13px; cursor: pointer; padding: 4px; }
  .team-details { padding: 8px 0; display: flex; flex-direction: column; gap: 6px; }
  .empty-state { text-align: center; color: var(--c-text-muted); padding: 20px; font-size: 13px; }
</style>
