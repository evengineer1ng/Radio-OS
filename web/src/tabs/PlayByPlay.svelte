<script lang="ts">
  import { gameState } from '../lib/stores'
  import { sendCommand } from '../lib/ws'

  $: pbp = $gameState?.play_by_play || {}
  $: liveEvents = pbp.live_events || []
  $: standings = pbp.standings || []
  $: raceHistory = pbp.history || []
  $: telemetry = pbp.telemetry || {}
  $: isLive = pbp.is_live || false
  $: lapInfo = pbp.lap_info || { current: 0, total: 0 }

  let subTab: 'live' | 'standings' | 'events' | 'telemetry' | 'history' = 'live'

  function formatGap(gap: any): string {
    if (!gap || gap === 0) return 'Leader'
    if (typeof gap === 'string') return gap
    return `+${Number(gap).toFixed(3)}s`
  }
</script>

<div class="tab-content scroll-y">
  <div class="tab-bar">
    {#each ['live', 'standings', 'events', 'telemetry', 'history'] as t}
      <button class="tab-btn" class:active={subTab === t} on:click={() => subTab = t}>
        {t === 'live' ? '🏁 Live' : t === 'standings' ? '📊 Standings' : t === 'events' ? '📋 Events' : t === 'telemetry' ? '📡 Telemetry' : '📜 History'}
      </button>
    {/each}
  </div>

  {#if !isLive && subTab === 'live'}
    <div class="empty-state">
      <p>No race currently in progress.</p>
      <p class="muted">Advance time to the next race weekend.</p>
    </div>
  {:else if subTab === 'live'}
    <div class="race-header">
      <span class="live-badge">🔴 LIVE</span>
      <span class="lap-counter">Lap {lapInfo.current}/{lapInfo.total}</span>
    </div>
    <div class="live-feed">
      {#each liveEvents as evt, i}
        <div class="live-event" class:highlight={evt.highlight}>
          <span class="event-lap">L{evt.lap || '?'}</span>
          <span class="event-text">{evt.text || evt}</span>
        </div>
      {/each}
      {#if liveEvents.length === 0}
        <p class="muted">Waiting for race events...</p>
      {/if}
    </div>

  {:else if subTab === 'standings'}
    <table class="data-table">
      <thead>
        <tr><th>Pos</th><th>Driver</th><th>Team</th><th>Gap</th></tr>
      </thead>
      <tbody>
        {#each standings as s, i}
          <tr class:player-row={s.is_player}>
            <td class="pos">{i + 1}</td>
            <td>{s.driver || s.name || '—'}</td>
            <td class="muted">{s.team || '—'}</td>
            <td class="mono">{formatGap(s.gap)}</td>
          </tr>
        {/each}
        {#if standings.length === 0}
          <tr><td colspan="4" class="muted">No standings data.</td></tr>
        {/if}
      </tbody>
    </table>

  {:else if subTab === 'events'}
    <div class="event-list">
      {#each liveEvents as evt}
        <div class="event-row">
          <span class="event-type badge badge-{evt.type || 'info'}">{evt.type || 'event'}</span>
          <span>{evt.text || JSON.stringify(evt)}</span>
        </div>
      {/each}
      {#if liveEvents.length === 0}
        <p class="muted">No events recorded.</p>
      {/if}
    </div>

  {:else if subTab === 'telemetry'}
    <div class="telemetry-grid">
      {#each Object.entries(telemetry) as [key, val]}
        <div class="telemetry-item">
          <span class="tel-label">{key}</span>
          <span class="tel-value">{typeof val === 'number' ? val.toFixed(2) : val}</span>
        </div>
      {/each}
      {#if Object.keys(telemetry).length === 0}
        <p class="muted">No telemetry available.</p>
      {/if}
    </div>

  {:else if subTab === 'history'}
    <div class="history-list">
      {#each raceHistory as race, i}
        <div class="history-card card">
          <div class="card-header">{race.name || `Race ${i + 1}`}</div>
          <div class="card-body">
            <span>Winner: {race.winner || '—'}</span>
            <span class="muted">Player finish: {race.player_finish ?? '—'}</span>
          </div>
        </div>
      {/each}
      {#if raceHistory.length === 0}
        <p class="muted">No race history yet.</p>
      {/if}
    </div>
  {/if}
</div>

<style>
  .race-header {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 0;
  }
  .live-badge {
    font-weight: 700;
    font-size: 14px;
    animation: pulse 1.5s infinite;
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
  }
  .lap-counter {
    font-family: var(--font-mono);
    font-size: 13px;
    color: var(--c-text-secondary);
  }
  .live-feed {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .live-event {
    display: flex;
    gap: 8px;
    padding: 6px 8px;
    font-size: 13px;
    border-left: 2px solid var(--c-border);
  }
  .live-event.highlight {
    border-left-color: var(--c-warning);
    background: rgba(255, 183, 77, 0.06);
  }
  .event-lap {
    font-family: var(--font-mono);
    color: var(--c-text-muted);
    min-width: 28px;
  }
  .data-table { width: 100%; border-collapse: collapse; }
  .data-table th, .data-table td { padding: 8px 10px; text-align: left; font-size: 13px; }
  .data-table th { color: var(--c-text-muted); font-size: 11px; text-transform: uppercase; border-bottom: 1px solid var(--c-border); }
  .data-table tr:hover { background: var(--c-bg-card); }
  .player-row { background: rgba(76, 201, 240, 0.06) !important; }
  .pos { font-weight: 700; width: 36px; }
  .mono { font-family: var(--font-mono); }
  .event-list { display: flex; flex-direction: column; gap: 6px; }
  .event-row { display: flex; align-items: center; gap: 8px; font-size: 13px; }
  .telemetry-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
    gap: 8px;
  }
  .telemetry-item {
    background: var(--c-bg-card);
    padding: 10px;
    border-radius: var(--radius-sm);
    text-align: center;
  }
  .tel-label { display: block; font-size: 10px; color: var(--c-text-muted); text-transform: uppercase; }
  .tel-value { display: block; font-size: 18px; font-weight: 700; font-family: var(--font-mono); margin-top: 4px; }
  .history-list { display: flex; flex-direction: column; gap: 8px; }
  .empty-state { text-align: center; padding: 48px 16px; color: var(--c-text-muted); }
</style>
