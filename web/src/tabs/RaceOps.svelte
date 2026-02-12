<script lang="ts">
  import { gameState } from '../lib/stores'

  $: phase = $gameState.phase
  $: raceActive = $gameState.race_day_active
  $: team = $gameState.player_team
  $: drivers = team?.roster?.drivers || []
  $: events = $gameState.recent_events || []
  $: raceEvents = events.filter((e: any) => (e.type || '').toLowerCase().includes('race'))
  $: leagues = $gameState.leagues || {}

  // Find player league + next race
  $: playerLeague = Object.values(leagues).find((l: any) =>
    l.team_names?.includes(team?.name)
  ) as any
  $: schedule = playerLeague?.schedule || []
  $: nextRace = schedule.find((r: any) => !r.completed)
</script>

<div class="raceops-view">
  <!-- Phase Status -->
  <div class="card">
    <div class="section-title">🏁 Race Weekend Status</div>
    <div class="phase-indicator" class:active={raceActive}>
      {#if raceActive}
        🟢 RACE DAY ACTIVE
      {:else if phase === 'race_weekend'}
        🟡 Race Weekend
      {:else}
        ⚪ {phase || 'Development Phase'}
      {/if}
    </div>
  </div>

  <!-- Next Race -->
  {#if nextRace}
    <div class="card">
      <div class="section-title">🗺️ Next Race</div>
      <div class="track-info">
        <div class="track-name">{nextRace.track_name || 'TBD'}</div>
        <div class="track-meta">Tick {nextRace.tick || '?'}</div>
      </div>
    </div>
  {/if}

  <!-- Driver Lineup -->
  <div class="card">
    <div class="section-title">🏎️ Driver Lineup</div>
    <div class="lineup">
      {#each (Array.isArray(drivers) ? drivers : [drivers]) as d}
        {#if d}
          <div class="driver-chip">
            <span class="driver-name">{d.name}</span>
            <span class="driver-rating">{Math.round(d.overall || 0)}</span>
          </div>
        {/if}
      {:else}
        <div class="empty-state">No drivers</div>
      {/each}
    </div>
  </div>

  <!-- Recent Race Results -->
  <div class="card">
    <div class="section-title">🏆 Recent Results</div>
    <div class="results-list scroll-y">
      {#each raceEvents.slice(-10).reverse() as evt}
        <div class="result-item">
          <span class="result-desc">{evt.description || JSON.stringify(evt)}</span>
        </div>
      {:else}
        <div class="empty-state">No race results yet</div>
      {/each}
    </div>
  </div>
</div>

<style>
  .raceops-view { display: flex; flex-direction: column; gap: 12px; padding: 12px; }
  .phase-indicator {
    text-align: center; padding: 16px; border-radius: var(--radius);
    font-weight: 600; font-size: 14px; background: var(--c-bg-tertiary);
    text-transform: uppercase;
  }
  .phase-indicator.active { color: var(--c-success); background: rgba(74, 222, 128, 0.1); }
  .track-info { padding: 8px 0; }
  .track-name { font-size: 16px; font-weight: 700; }
  .track-meta { font-size: 12px; color: var(--c-text-muted); margin-top: 2px; }
  .lineup { display: flex; flex-wrap: wrap; gap: 8px; }
  .driver-chip {
    display: flex; align-items: center; gap: 8px;
    padding: 8px 12px; background: var(--c-bg-tertiary); border-radius: var(--radius);
  }
  .driver-name { font-size: 13px; font-weight: 500; }
  .driver-rating { font-family: var(--font-mono); color: var(--c-accent); font-weight: 700; }
  .results-list { max-height: 300px; }
  .result-item { padding: 6px 0; font-size: 12px; border-bottom: 1px solid var(--c-border); color: var(--c-text-secondary); }
  .empty-state { text-align: center; color: var(--c-text-muted); padding: 20px; font-size: 13px; }
</style>
