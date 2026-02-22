<script lang="ts">
  import { gameState } from '../lib/stores'
  import { formatCurrency } from '../lib/utils'
  import { formatEventSummary, isPlayerTeamEvent } from '../lib/eventFormat'
  import MetricDisplay from '../components/MetricDisplay.svelte'
  import Modal from '../components/Modal.svelte'

  $: team = $gameState.player_team
  $: teamName = team?.name || ''
  $: standingMetrics = team?.standing_metrics || {}
  $: budget = team?.budget || {}
  $: events = $gameState.recent_events || []

  // Personal events are strictly scoped to the player team.
  $: personalEvents = events.filter((e: any) => isPlayerTeamEvent(e, teamName))
  $: worldEvents = events.filter((e: any) => !isPlayerTeamEvent(e, teamName))

  // Pressure indicators
  $: cash = budget.cash || 0
  $: weeklyBurn = budget.weekly_expenses || 0
  $: runway = weeklyBurn > 0 ? Math.floor(cash / weeklyBurn) : 999
  $: morale = Number(standingMetrics?.morale ?? 50)
  $: teamHealth = Number(standingMetrics?.team_health ?? 50)
  $: reputation = Number(standingMetrics?.reputation ?? 50)
  $: moraleState = morale >= 70 ? 'High' : morale <= 35 ? 'Low' : 'Stable'
  $: moraleColor = morale >= 70 ? 'var(--c-success)' : morale <= 35 ? 'var(--c-danger)' : 'var(--c-warning)'
  $: teamHealthState = teamHealth >= 70 ? 'Strong' : teamHealth <= 35 ? 'Weak' : 'Mixed'

  const PHASE_LABELS: Record<string, string> = {
    development: '🔧 Development',
    race_weekend: '🏁 Race Weekend',
    offseason: '⏸️ Off-Season',
    'race_day:pre_race_prompt': '📣 Pre-Race Prompt',
    'race_day:quali_ready': '🟡 Qualifying Ready',
    'race_day:quali_running': '⏱️ Qualifying Running',
    'race_day:quali_complete': '🧾 Qualifying Complete',
    'race_day:race_ready': '🏎️ Race Ready',
    'race_day:race_running': '🔴 Race Running',
    'race_day:race_complete': '✅ Race Complete',
    'race_day:post_race_advance': '📦 Post-Race Advance',
  }

  const PHASE_COLORS: Record<string, string> = {
    development: 'var(--c-warning)',
    race_weekend: 'var(--c-accent)',
    offseason: 'var(--c-text-muted)',
    'race_day:pre_race_prompt': 'var(--c-warning)',
    'race_day:quali_ready': 'var(--c-warning)',
    'race_day:quali_running': 'var(--c-warning)',
    'race_day:quali_complete': 'var(--c-success)',
    'race_day:race_ready': 'var(--c-accent)',
    'race_day:race_running': 'var(--c-danger)',
    'race_day:race_complete': 'var(--c-success)',
    'race_day:post_race_advance': 'var(--c-accent)',
  }

  function formatPhaseFallback(phaseKey: string): string {
    if (!phaseKey) return '—'
    const clean = phaseKey.replace('race_day:', '')
    return clean
      .split('_')
      .filter(Boolean)
      .map((part: string) => part[0]?.toUpperCase() + part.slice(1))
      .join(' ')
  }

  $: basePhase = String($gameState?.phase || 'development').toLowerCase()
  $: raceDayPhase = String($gameState?.race_day?.phase || 'idle').toLowerCase()
  $: dashboardPhaseKey = raceDayPhase !== 'idle'
    ? `race_day:${raceDayPhase}`
    : ($gameState?.in_offseason ? 'offseason' : basePhase)
  $: dashboardPhaseLabel = PHASE_LABELS[dashboardPhaseKey] || formatPhaseFallback(dashboardPhaseKey)
  $: dashboardPhaseColor = PHASE_COLORS[dashboardPhaseKey] || 'var(--c-info)'

  let eventTab: 'personal' | 'world' = 'personal'

  // Team-driver race results.
  // Prefer backend `player_driver_recent_results`, fallback to recent_events.
  $: teamDrivers = (team?.roster?.drivers || [])
    .map((d: any) => d?.name)
    .filter(Boolean)

  $: backendDriverRecentResults = Array.isArray($gameState.player_driver_recent_results)
    ? $gameState.player_driver_recent_results
    : []

  $: fallbackTeamRaceResults = events
    .filter((e: any) => {
      const data = e?.data || {}
      const eventTeam = String(data?.team || data?.team_name || data?.player_team_name || '')
      return e?.category === 'race_result' && eventTeam === teamName
    })
    .map((e: any) => ({
      tick: Number(e?.tick || 0),
      driver: String(e?.data?.driver || ''),
      position: Number(e?.data?.position || 0),
      points: Number(e?.data?.points || 0),
      status: String(e?.data?.status || ''),
      trackName: String(e?.data?.track_name || ''),
      round: Number(e?.data?.round_number || 0),
      season: Number($gameState?.season_number || 0),
    }))

  $: normalizedBackendResults = backendDriverRecentResults.map((driverBlock: any) => ({
    name: String(driverBlock?.name || ''),
    results: (Array.isArray(driverBlock?.results) ? driverBlock.results : []).map((r: any) => ({
      tick: Number(r?.tick || 0),
      season: Number(r?.season || 0),
      round: Number(r?.round || 0),
      driver: String(r?.driver || driverBlock?.name || ''),
      position: Number(r?.position || 0),
      points: Number(r?.points || 0),
      status: String(r?.status || ''),
      trackName: String(r?.track_name || r?.trackName || ''),
    })),
  }))

  $: hasBackendDriverResults = normalizedBackendResults.some((d: any) => (d?.results || []).length > 0)

  $: driverRecentResults = hasBackendDriverResults
    ? teamDrivers.map((driverName: string) => {
        const found = normalizedBackendResults.find((d: any) => d.name === driverName)
        return {
          name: driverName,
          results: (found?.results || []).slice(0, 6),
        }
      })
    : teamDrivers.map((driverName: string) => ({
        name: driverName,
        results: fallbackTeamRaceResults
          .filter((r: any) => r.driver === driverName)
          .slice(-6)
          .reverse(),
      }))

  // Intrusive championship popup when a season_end event appears
  let showSeasonPopup = false
  let seasonPopupEvent: any = null
  const seenSeasonPopupKeys = new Set<string>()

  function seasonPopupKey(evt: any): string {
    if (!evt) return ''
    const data = evt?.data || {}
    return `${evt?.tick || 0}|${data?.league_id || data?.league || ''}|${data?.champion || ''}`
  }

  function getSeasonFinish(evt: any): { position: number; points: number } | null {
    if (!evt) return null
    const data = evt?.data || {}

    const explicitPos = Number(data?.player_position || 0)
    if (explicitPos > 0) {
      return {
        position: explicitPos,
        points: Number(data?.player_points || 0),
      }
    }

    const standings = Array.isArray(data?.standings) ? data.standings : []
    const idx = standings.findIndex((row: any) => Array.isArray(row) && String(row[0] || '') === teamName)
    if (idx < 0) return null
    return {
      position: idx + 1,
      points: Number(standings[idx]?.[1] || 0),
    }
  }

  $: seasonPopupFinish = seasonPopupEvent ? getSeasonFinish(seasonPopupEvent) : null
  $: seasonPopupTop = Array.isArray(seasonPopupEvent?.data?.standings) ? seasonPopupEvent.data.standings.slice(0, 5) : []

  $: {
    const latestSeasonEvent = [...events].reverse().find((e: any) => e?.category === 'season_end')
    if (!latestSeasonEvent) {
      // no-op
    } else {
      const key = seasonPopupKey(latestSeasonEvent)
      if (key && !seenSeasonPopupKeys.has(key)) {
        seenSeasonPopupKeys.add(key)
        seasonPopupEvent = latestSeasonEvent
        showSeasonPopup = true
      }
    }
  }
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
      label="Morale"
      value={`${Math.round(morale)}%`}
      sublabel={moraleState}
      color={moraleColor}
    />
    <MetricDisplay
      label="Phase"
      value={dashboardPhaseLabel}
      color={dashboardPhaseColor}
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
        <div class="info-item">
          <span class="info-label">Reputation</span>
          <span class="info-value">{Math.round(reputation)}%</span>
        </div>
        <div class="info-item">
          <span class="info-label">Team Morale</span>
          <span class="info-value">{Math.round(morale)}%</span>
        </div>
        <div class="info-item">
          <span class="info-label">Team Health</span>
          <span class="info-value">{Math.round(teamHealth)}% ({teamHealthState})</span>
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
          <span class="event-desc">{formatEventSummary(evt)}</span>
        </div>
      {:else}
        <div class="empty-state">No events yet</div>
      {/each}
    </div>
  </div>

  <div class="card">
    <div class="section-title">🏁 Recent Results (All Team Drivers)</div>
    <div class="driver-results-grid">
      {#each driverRecentResults as driverBlock}
        <div class="driver-result-row">
          <div class="driver-name">{driverBlock.name}</div>
          <div class="driver-result-pills">
            {#each driverBlock.results as result}
              <span
                class="result-pill"
                class:podium={result.position > 0 && result.position <= 3}
                class:dnf={result.status && result.status !== 'finished'}
                title={`${result.trackName || 'Race'} • ${result.status || 'finished'} • Tick ${result.tick}`}
              >
                P{result.position > 0 ? result.position : '—'} ({result.points})
              </span>
            {:else}
              <span class="result-empty">No recent race results</span>
            {/each}
          </div>
        </div>
      {:else}
        <div class="empty-state">No drivers available</div>
      {/each}
    </div>
  </div>
</div>

<Modal show={showSeasonPopup} title="🏆 Championship Finalized" size="md" on:close={() => showSeasonPopup = false}>
  {#if seasonPopupEvent}
    <div class="season-popup">
      <div class="season-line"><strong>{seasonPopupEvent?.data?.league || 'League'}</strong> season complete.</div>
      <div class="season-line">Champion: <strong>{seasonPopupEvent?.data?.champion || '—'}</strong></div>
      {#if seasonPopupFinish}
        <div class="season-line highlight">Your finish: <strong>P{seasonPopupFinish.position}</strong> ({Math.round(seasonPopupFinish.points)} pts)</div>
      {/if}

      {#if seasonPopupTop.length > 0}
        <div class="season-standings">
          {#each seasonPopupTop as row, idx}
            <div class="season-standing-row">
              <span class="pos">P{idx + 1}</span>
              <span class="team">{Array.isArray(row) ? row[0] : '—'}</span>
              <span class="pts">{Math.round(Number(Array.isArray(row) ? row[1] : 0))} pts</span>
            </div>
          {/each}
        </div>
      {/if}
    </div>
  {/if}
</Modal>

<style>
  .dashboard { display: flex; flex-direction: column; gap: 12px; padding: 12px; }
  .metrics-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
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
  .driver-results-grid {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .driver-result-row {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 8px;
    border: 1px solid var(--c-border);
    border-radius: var(--radius-sm);
    background: var(--c-bg-tertiary);
  }
  .driver-name {
    font-size: 12px;
    font-weight: 700;
    color: var(--c-text-primary);
  }
  .driver-result-pills {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .result-pill {
    display: inline-flex;
    align-items: center;
    padding: 3px 8px;
    border-radius: 999px;
    border: 1px solid var(--c-border);
    background: var(--c-bg-card);
    color: var(--c-text-secondary);
    font-size: 11px;
    font-family: var(--font-mono);
  }
  .result-pill.podium {
    color: var(--c-success);
    border-color: #3e8f61;
  }
  .result-pill.dnf {
    color: var(--c-danger);
    border-color: #8f4a4a;
  }
  .result-empty {
    color: var(--c-text-muted);
    font-size: 11px;
  }
  .season-popup {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .season-line {
    color: var(--c-text-secondary);
    font-size: 13px;
  }
  .season-line.highlight {
    color: var(--c-accent);
  }
  .season-standings {
    margin-top: 4px;
    border-top: 1px solid var(--c-border);
    padding-top: 8px;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .season-standing-row {
    display: grid;
    grid-template-columns: 38px 1fr auto;
    gap: 8px;
    font-size: 12px;
    align-items: center;
  }
  .season-standing-row .pos {
    color: var(--c-accent);
    font-family: var(--font-mono);
  }
  .season-standing-row .team {
    color: var(--c-text-primary);
  }
  .season-standing-row .pts {
    color: var(--c-text-muted);
    font-family: var(--font-mono);
  }
  @media (max-width: 480px) {
    .metrics-row { grid-template-columns: 1fr 1fr; }
  }
</style>
