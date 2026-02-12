<script lang="ts">
  import { gameState } from '../lib/stores'

  $: leagues = $gameState.leagues || {}
  $: leagueNames = Object.keys(leagues)

  let selectedLeague = ''
  $: if (leagueNames.length && !selectedLeague) selectedLeague = leagueNames[0]

  $: league = leagues[selectedLeague] || {}
  $: champTable = league.championship_table || {}
  $: driverChamp = league.driver_championship || {}

  let statsTab: 'teams' | 'drivers' = 'teams'

  // Convert championship tables to sorted arrays
  $: teamStandings = (() => {
    if (Array.isArray(champTable)) return champTable
    return Object.entries(champTable)
      .map(([name, pts]) => ({ name, points: Number(pts) }))
      .sort((a, b) => b.points - a.points)
  })()

  $: driverStandings = (() => {
    if (Array.isArray(driverChamp)) return driverChamp
    return Object.entries(driverChamp)
      .map(([name, pts]) => ({ name, points: Number(pts) }))
      .sort((a, b) => b.points - a.points)
  })()
</script>

<div class="stats-view">
  <!-- Filters -->
  <div class="card filters">
    <select class="filter-select" bind:value={selectedLeague}>
      {#each leagueNames as ln}
        <option value={ln}>{ln}</option>
      {/each}
    </select>
    <div class="tab-bar compact">
      <button class="tab-btn" class:active={statsTab === 'teams'} on:click={() => statsTab = 'teams'}>Teams</button>
      <button class="tab-btn" class:active={statsTab === 'drivers'} on:click={() => statsTab = 'drivers'}>Drivers</button>
    </div>
  </div>

  <!-- Standings -->
  <div class="card">
    <div class="section-title">{statsTab === 'teams' ? '🏆 Team Standings' : '🏎️ Driver Standings'}</div>
    <div class="standings-table scroll-y">
      <table>
        <thead>
          <tr><th>#</th><th>Name</th><th>Pts</th></tr>
        </thead>
        <tbody>
          {#each (statsTab === 'teams' ? teamStandings : driverStandings) as row, i}
            <tr>
              <td class="pos">{i + 1}</td>
              <td class="name">{row.name}</td>
              <td class="pts">{row.points}</td>
            </tr>
          {:else}
            <tr><td colspan="3" class="empty-state">No standings data</td></tr>
          {/each}
        </tbody>
      </table>
    </div>
  </div>
</div>

<style>
  .stats-view { display: flex; flex-direction: column; gap: 12px; padding: 12px; }
  .filters { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
  .filter-select {
    padding: 6px 10px; border: 1px solid var(--c-border); border-radius: var(--radius-sm);
    background: var(--c-bg-input); color: var(--c-text-primary); font-size: 12px;
  }
  .compact { border: none; }
  .standings-table { max-height: 500px; }
  table { width: 100%; border-collapse: collapse; }
  th { text-align: left; font-size: 11px; color: var(--c-text-muted); padding: 6px 8px; border-bottom: 2px solid var(--c-border); text-transform: uppercase; }
  td { padding: 8px; font-size: 13px; border-bottom: 1px solid var(--c-border); }
  .pos { width: 40px; font-weight: 700; color: var(--c-accent); font-family: var(--font-mono); }
  .name { font-weight: 500; }
  .pts { font-family: var(--font-mono); color: var(--c-text-secondary); text-align: right; width: 60px; }
  .empty-state { text-align: center; color: var(--c-text-muted); padding: 20px; }
</style>
