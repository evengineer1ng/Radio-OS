<script lang="ts">
  import { onDestroy } from 'svelte'
  import { gameState } from '../lib/stores'
  import { fetchState, raceDayRespond, raceDayStartLive, raceDayPause, raceDayComplete } from '../lib/api'

  $: raceDay = $gameState.race_day || { phase: 'idle' }
  $: phase = raceDay.phase || 'idle'
  $: team = $gameState.player_team
  $: drivers = team?.roster?.drivers || []
  $: leagues = $gameState.leagues || {}
  $: tracks = $gameState.tracks || {}

  $: playerLeague = Object.values(leagues).find((l: any) =>
    l.team_names?.includes(team?.name)
  ) as any
  $: schedule = playerLeague?.schedule || []
  $: nextRace = schedule.find((r: any) => !r.completed)
  $: completedRaces = schedule.filter((r: any) => r.completed).length

  $: qualiGrid = raceDay.quali_grid || []
  $: standings = raceDay.standings || []
  $: liveEvents = raceDay.events || []
  $: currentLap = raceDay.current_lap || 0
  $: totalLaps = raceDay.total_laps || 0
  $: raceResult = raceDay.result || null
  $: trackId = raceDay.track_id || ''
  $: trackInfo = tracks[trackId] || {}

  let raceSpeed = 10

  // Poll for live updates when race day is active
  let pollInterval: ReturnType<typeof setInterval> | null = null
  function startPolling() {
    if (pollInterval) return
    pollInterval = setInterval(async () => {
      try { gameState.set(await fetchState()) } catch {}
    }, 1500)
  }
  function stopPolling() {
    if (pollInterval) { clearInterval(pollInterval); pollInterval = null }
  }
  $: phase !== 'idle' ? startPolling() : stopPolling()
  onDestroy(stopPolling)

  async function respondToPrompt(watchLive: boolean) {
    await raceDayRespond(watchLive)
    setTimeout(async () => { try { gameState.set(await fetchState()) } catch {} }, 500)
  }
  async function startLive() {
    await raceDayStartLive(raceSpeed)
  }
  async function pauseRace() { await raceDayPause() }
  async function completeRaceDay() {
    await raceDayComplete()
    stopPolling()
    setTimeout(async () => { try { gameState.set(await fetchState()) } catch {} }, 1000)
  }

  function formatGap(gap: any): string {
    if (!gap || gap === 0) return 'Leader'
    if (typeof gap === 'string') return gap
    return `+${Number(gap).toFixed(3)}s`
  }
</script>

<div class="raceops-view scroll-y">
  <!-- Phase Banner -->
  <div class="card">
    <div class="section-title">🏁 Race Day Control</div>
    <div class="phase-banner phase-{phase}">
      {#if phase === 'idle'}
        ⚪ No Race Active
      {:else if phase === 'pre_race_prompt'}
        🟡 RACE DAY — Choose Mode
      {:else if phase === 'quali_running'}
        🟠 Qualifying In Progress…
      {:else if phase === 'quali_complete'}
        🟢 Qualifying Complete — Ready to Race
      {:else if phase === 'race_running'}
        🔴 RACE LIVE — Lap {currentLap}/{totalLaps}
      {:else if phase === 'race_complete'}
        🏁 Race Finished
      {:else}
        ⚪ {phase}
      {/if}
    </div>
  </div>

  <!-- Pre-Race Prompt -->
  {#if phase === 'pre_race_prompt'}
    <div class="card prompt-card">
      <div class="section-title">📋 Race Weekend at {trackInfo.name || trackId || 'Unknown Track'}</div>
      <p class="prompt-text">Your team is ready for the race. How would you like to experience it?</p>
      <div class="prompt-actions">
        <button class="btn btn-primary btn-lg" on:click={() => respondToPrompt(true)}>🏎️ Watch Live Race</button>
        <button class="btn btn-ghost btn-lg" on:click={() => respondToPrompt(false)}>⏩ Instant Sim</button>
      </div>
    </div>
  {/if}

  <!-- Qualifying Results -->
  {#if qualiGrid.length > 0 && phase !== 'idle'}
    <div class="card">
      <div class="section-title">🏎️ Qualifying Grid</div>
      <table class="data-table">
        <thead><tr><th>Pos</th><th>Driver</th><th>Team</th><th>Score</th></tr></thead>
        <tbody>
          {#each qualiGrid as entry, i}
            <tr class:player-row={entry.is_player}>
              <td class="pos">{i + 1}</td>
              <td>{entry.driver}</td>
              <td class="muted">{entry.team}</td>
              <td class="mono">{entry.score?.toFixed(3) || '—'}</td>
            </tr>
          {/each}
        </tbody>
      </table>
      {#if phase === 'quali_complete'}
        <div class="race-start-controls">
          <label class="speed-label">Speed:
            <select bind:value={raceSpeed}>
              <option value={5}>Fast (5s/lap)</option>
              <option value={10}>Normal (10s/lap)</option>
              <option value={20}>Slow (20s/lap)</option>
            </select>
          </label>
          <button class="btn btn-primary" on:click={startLive}>▶️ Start Live Race</button>
        </div>
      {/if}
    </div>
  {/if}

  <!-- Live Race -->
  {#if phase === 'race_running'}
    <div class="card">
      <div class="race-header">
        <span class="live-badge">🔴 LIVE</span>
        <span class="lap-counter">Lap {currentLap}/{totalLaps}</span>
        <button class="btn btn-ghost btn-sm" on:click={pauseRace}>⏸ Pause</button>
      </div>
      <table class="data-table">
        <thead><tr><th>Pos</th><th>Driver</th><th>Team</th><th>Gap</th></tr></thead>
        <tbody>
          {#each standings as s, i}
            <tr class:player-row={s.is_player}>
              <td class="pos">{i + 1}</td>
              <td>{s.driver || s.name || '—'}</td>
              <td class="muted">{s.team || '—'}</td>
              <td class="mono">{formatGap(s.gap)}</td>
            </tr>
          {:else}
            <tr><td colspan="4" class="muted">Waiting for data…</td></tr>
          {/each}
        </tbody>
      </table>
      <div class="section-title" style="margin-top:12px">📋 Commentary</div>
      <div class="live-feed scroll-y">
        {#each liveEvents.slice(-20).reverse() as evt}
          <div class="live-event" class:highlight={evt.highlight}>
            <span class="event-lap">L{evt.lap || '?'}</span>
            <span class="event-text">{evt.text || evt}</span>
          </div>
        {:else}
          <p class="muted">Waiting for race events…</p>
        {/each}
      </div>
    </div>
  {/if}

  <!-- Race Complete -->
  {#if phase === 'race_complete'}
    <div class="card">
      <div class="section-title">🏆 Race Results</div>
      {#if raceResult}
        <div class="result-highlight">
          <div class="winner">🥇 {raceResult.winner_driver} ({raceResult.winner_team})</div>
          {#if raceResult.player_finish}
            <div class="player-finish">Your finish: P{raceResult.player_finish}</div>
          {/if}
        </div>
      {/if}
      {#if standings.length}
        <table class="data-table">
          <thead><tr><th>Pos</th><th>Driver</th><th>Team</th><th>Gap</th></tr></thead>
          <tbody>
            {#each standings as s, i}
              <tr class:player-row={s.is_player}><td class="pos">{i+1}</td><td>{s.driver||'—'}</td><td class="muted">{s.team||'—'}</td><td class="mono">{formatGap(s.gap)}</td></tr>
            {/each}
          </tbody>
        </table>
      {/if}
      <div class="complete-actions">
        <button class="btn btn-primary" on:click={completeRaceDay}>✅ Continue Season</button>
      </div>
    </div>
  {/if}

  <!-- Idle: Driver Lineup + Schedule -->
  {#if phase === 'idle'}
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
    {#if schedule.length}
      <div class="card">
        <div class="section-title">📅 Season ({completedRaces}/{schedule.length})</div>
        <div class="schedule-list scroll-y">
          {#each schedule as race, i}
            <div class="schedule-item" class:completed={race.completed} class:next={!race.completed && i === completedRaces}>
              <span class="race-num">R{i+1}</span>
              <span class="track-name">{race.track_name || tracks[race.track_id]?.name || 'TBD'}</span>
              <span class="race-tick">Tick {race.tick||'?'}</span>
              {#if race.completed}<span class="badge-done">✓</span>
              {:else if i === completedRaces}<span class="badge-next">NEXT</span>{/if}
            </div>
          {/each}
        </div>
      </div>
    {/if}
  {/if}
</div>

<style>
  .raceops-view { display:flex; flex-direction:column; gap:12px; padding:12px; height:100%; overflow-y:auto; }
  .phase-banner { text-align:center; padding:16px; border-radius:var(--radius); font-weight:700; font-size:14px; text-transform:uppercase; background:var(--c-bg-tertiary); }
  .phase-banner.phase-pre_race_prompt { color:var(--c-warning); background:rgba(255,183,77,0.1); }
  .phase-banner.phase-race_running { color:var(--c-danger); background:rgba(244,67,54,0.1); }
  .phase-banner.phase-quali_complete { color:var(--c-success); background:rgba(74,222,128,0.1); }
  .phase-banner.phase-race_complete { color:var(--c-accent); background:rgba(76,201,240,0.1); }
  .prompt-card { text-align:center; }
  .prompt-text { color:var(--c-text-secondary); margin:12px 0 20px; font-size:14px; }
  .prompt-actions { display:flex; gap:12px; justify-content:center; flex-wrap:wrap; }
  .race-header { display:flex; align-items:center; gap:12px; padding:10px 0; }
  .live-badge { font-weight:700; font-size:14px; animation:pulse 1.5s infinite; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.5} }
  .lap-counter { font-family:var(--font-mono); font-size:13px; color:var(--c-text-secondary); }
  .race-start-controls { display:flex; align-items:center; gap:12px; margin-top:12px; justify-content:center; }
  .speed-label { font-size:12px; color:var(--c-text-muted); display:flex; align-items:center; gap:6px; }
  .speed-label select { padding:4px 8px; border:1px solid var(--c-border); border-radius:var(--radius-sm); background:var(--c-bg-input); color:var(--c-text-primary); font-size:12px; }
  .data-table { width:100%; border-collapse:collapse; }
  .data-table th,.data-table td { padding:8px 10px; text-align:left; font-size:13px; }
  .data-table th { color:var(--c-text-muted); font-size:11px; text-transform:uppercase; border-bottom:1px solid var(--c-border); }
  .data-table tr:hover { background:var(--c-bg-card); }
  .player-row { background:rgba(76,201,240,0.08)!important; font-weight:600; }
  .pos { font-weight:700; width:36px; }
  .mono { font-family:var(--font-mono); }
  .live-feed { display:flex; flex-direction:column; gap:4px; max-height:200px; }
  .live-event { display:flex; gap:8px; padding:6px 8px; font-size:13px; border-left:2px solid var(--c-border); }
  .live-event.highlight { border-left-color:var(--c-warning); background:rgba(255,183,77,0.06); }
  .event-lap { font-family:var(--font-mono); color:var(--c-text-muted); min-width:28px; }
  .result-highlight { text-align:center; padding:16px; margin-bottom:12px; }
  .winner { font-size:18px; font-weight:800; }
  .player-finish { font-size:14px; color:var(--c-accent); margin-top:6px; }
  .complete-actions { display:flex; justify-content:center; margin-top:12px; }
  .lineup { display:flex; flex-wrap:wrap; gap:8px; }
  .driver-chip { display:flex; align-items:center; gap:8px; padding:8px 12px; background:var(--c-bg-tertiary); border-radius:var(--radius); }
  .driver-name { font-size:13px; font-weight:500; }
  .driver-rating { font-family:var(--font-mono); color:var(--c-accent); font-weight:700; }
  .schedule-list { max-height:300px; }
  .schedule-item { display:flex; align-items:center; gap:8px; padding:8px; font-size:13px; border-bottom:1px solid var(--c-border); }
  .schedule-item.completed { opacity:0.5; }
  .schedule-item.next { background:rgba(76,201,240,0.06); }
  .race-num { font-weight:700; min-width:28px; color:var(--c-text-muted); }
  .track-name { flex:1; }
  .race-tick { font-family:var(--font-mono); font-size:11px; color:var(--c-text-muted); }
  .badge-done { color:var(--c-success); font-size:11px; }
  .badge-next { color:var(--c-accent); font-size:10px; font-weight:700; padding:2px 6px; border:1px solid var(--c-accent); border-radius:4px; }
  .empty-state { text-align:center; color:var(--c-text-muted); padding:20px; font-size:13px; }
  .muted { color:var(--c-text-muted); }
</style>