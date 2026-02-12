<script lang="ts">
  import { gameState } from '../lib/stores'
  import { formatCurrency } from '../lib/utils'

  $: aiTeams = $gameState.ai_teams || []
  $: playerTeam = $gameState.player_team
  $: allTeams = playerTeam ? [playerTeam, ...aiTeams] : aiTeams

  // Build comparison data
  $: comparison = allTeams.map((t: any) => ({
    name: t.name,
    budget: t.budget?.cash || 0,
    driverCount: (Array.isArray(t.roster?.drivers) ? t.roster.drivers : [t.roster?.drivers]).filter(Boolean).length,
    carRating: t.car?.overall || 0,
    isPlayer: t.name === playerTeam?.name,
  })).sort((a: any, b: any) => b.carRating - a.carRating)
</script>

<div class="analytics-view">
  <div class="card">
    <div class="section-title">📊 Team Performance Comparison</div>
    <div class="table-wrap scroll-y">
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Team</th>
            <th>Budget</th>
            <th>Car</th>
            <th>Drivers</th>
          </tr>
        </thead>
        <tbody>
          {#each comparison as row, i}
            <tr class:player-row={row.isPlayer}>
              <td class="pos">{i + 1}</td>
              <td class="name">{row.name} {row.isPlayer ? '⭐' : ''}</td>
              <td class="mono">{formatCurrency(row.budget)}</td>
              <td class="mono">{Math.round(row.carRating)}</td>
              <td class="mono">{row.driverCount}</td>
            </tr>
          {:else}
            <tr><td colspan="5" class="empty-state">No team data</td></tr>
          {/each}
        </tbody>
      </table>
    </div>
  </div>
</div>

<style>
  .analytics-view { padding: 12px; }
  .table-wrap { max-height: 500px; }
  table { width: 100%; border-collapse: collapse; }
  th { text-align: left; font-size: 11px; color: var(--c-text-muted); padding: 6px 8px; border-bottom: 2px solid var(--c-border); }
  td { padding: 8px; font-size: 13px; border-bottom: 1px solid var(--c-border); }
  .pos { width: 30px; font-weight: 700; color: var(--c-accent); font-family: var(--font-mono); }
  .name { font-weight: 500; }
  .mono { font-family: var(--font-mono); color: var(--c-text-secondary); }
  .player-row { background: rgba(76, 201, 240, 0.08); }
  .empty-state { text-align: center; color: var(--c-text-muted); padding: 20px; }
</style>
