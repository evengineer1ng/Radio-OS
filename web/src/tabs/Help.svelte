<script lang="ts">
  import { gameState } from '../lib/stores'

  const TIER_NAMES: Record<number, string> = {
    1: 'Grassroots',
    2: 'Formula V',
    3: 'Formula X',
    4: 'Formula Y',
    5: 'Formula Z',
  }

  const RACE_PRIZE_POOL_BY_TIER: Record<number, number> = {
    1: 175000,
    2: 250000,
    3: 500000,
    4: 1000000,
    5: 2000000,
  }

  const CHAMPIONSHIP_POOL_BY_TIER: Record<number, number> = {
    1: 650000,
    2: 1200000,
    3: 2500000,
    4: 6000000,
    5: 15000000,
  }

  const CHAMPIONSHIP_SHARE_TABLE: number[] = [0.24, 0.18, 0.14, 0.11, 0.09, 0.07, 0.06, 0.05, 0.035, 0.025]

  $: playerTeam = $gameState.player_team || null
  $: leagues = $gameState.leagues || {}
  $: playerLeague = Object.values(leagues).find((league: any) =>
    Array.isArray(league?.team_names) && league.team_names.includes(playerTeam?.name)
  ) as any

  $: activeTier = Number(playerLeague?.tier ?? playerTeam?.tier ?? 1)
  $: activeTierName = TIER_NAMES[activeTier] || `Tier ${activeTier}`
  $: racePrizePool = RACE_PRIZE_POOL_BY_TIER[activeTier] || RACE_PRIZE_POOL_BY_TIER[1]
  $: championshipPool = CHAMPIONSHIP_POOL_BY_TIER[activeTier] || CHAMPIONSHIP_POOL_BY_TIER[1]

  $: championshipRows = CHAMPIONSHIP_SHARE_TABLE.map((share, idx) => ({
    position: idx + 1,
    share,
    payout: Math.round(championshipPool * share),
  }))

  function money(value: number): string {
    return `$${Math.round(value || 0).toLocaleString()}`
  }
</script>

<div class="help-tab">
  <div class="card">
    <div class="section-title">❓ Help & Operations Manual</div>
    <p class="lead">
      Quick-reference guide for running your team day-to-day, understanding morale behavior,
      and tracking how race and championship money works.
    </p>
  </div>

  <div class="card">
    <div class="section-title">🏁 Core Loop</div>
    <ul class="help-list">
      <li><strong>Development days:</strong> adjust roster, contracts, parts, infrastructure, and finances.</li>
      <li><strong>Race days:</strong> results drive standings, morale shifts, and race prize payouts.</li>
      <li><strong>Season end:</strong> championship standings finalize, season payout is distributed, promotion/relegation windows open.</li>
    </ul>
  </div>

  <div class="card">
    <div class="section-title">😊 Morale System</div>
    <ul class="help-list">
      <li><strong>Primary driver:</strong> race results are the main source of morale movement.</li>
      <li><strong>Team-state multiplier:</strong> team health and team morale scale result impact, so context matters beyond one individual.</li>
      <li><strong>Passive drift:</strong> non-race day movement is intentionally small and slower than race-weekend movement.</li>
      <li><strong>Team health inputs:</strong> personnel morale, finances/runway, infrastructure quality, and championship form.</li>
    </ul>
  </div>

  <div class="card">
    <div class="section-title">💰 Prizes & Payouts ({activeTierName})</div>
    <div class="payout-meta">
      <div><span class="label">Race Prize Pool (per race)</span> <span class="value">{money(racePrizePool)}</span></div>
      <div><span class="label">Season Championship Pool</span> <span class="value">{money(championshipPool)}</span></div>
      <div><span class="label">Distribution Rule</span> <span class="value">Top 10 paid (not winner-only)</span></div>
    </div>

    <div class="table-wrap scroll-y">
      <table>
        <thead>
          <tr>
            <th>Pos</th>
            <th>Share</th>
            <th>Payout ({activeTierName})</th>
          </tr>
        </thead>
        <tbody>
          {#each championshipRows as row}
            <tr>
              <td>P{row.position}</td>
              <td>{(row.share * 100).toFixed(1)}%</td>
              <td>{money(row.payout)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </div>

  <div class="card">
    <div class="section-title">🧭 Where To Do What</div>
    <ul class="help-list">
      <li><strong>Home:</strong> strategic snapshot, event feed, morale and runway pulse checks.</li>
      <li><strong>Team:</strong> fire/hire, negotiate contracts, monitor roster quality and market.</li>
      <li><strong>Car:</strong> buy/sell/equip parts and compare quality by type.</li>
      <li><strong>Dev:</strong> R&amp;D and infrastructure planning.</li>
      <li><strong>Race / PBP:</strong> race control and live telemetry.</li>
      <li><strong>Finance:</strong> cashflow, expenses, sponsor income.</li>
      <li><strong>History:</strong> decisions/results/transactions log.</li>
      <li><strong>Data:</strong> deep DB/query explorer for audits and debugging.</li>
    </ul>
  </div>

  <div class="card">
    <div class="section-title">🛠️ Operating Tips</div>
    <ul class="help-list">
      <li>If the economy feels tight, track runway in Finance and prioritize sponsor stability over risky spend.</li>
      <li>Use Team + Car together: roster quality and part quality compound in race outcomes.</li>
      <li>After major actions (hire/buy/equip), give the sim a tick if you want downstream effects to settle.</li>
      <li>Use History + Data tabs to validate whether a result was simulation variance or a structural weakness.</li>
    </ul>
  </div>
</div>

<style>
  .help-tab {
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding: 12px;
  }
  .lead {
    margin: 0;
    color: var(--c-text-secondary);
    font-size: 13px;
    line-height: 1.5;
  }
  .help-list {
    margin: 0;
    padding-left: 18px;
    display: flex;
    flex-direction: column;
    gap: 6px;
    color: var(--c-text-secondary);
    font-size: 13px;
    line-height: 1.45;
  }
  .help-list strong {
    color: var(--c-text-primary);
    font-weight: 600;
  }
  .payout-meta {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin-bottom: 8px;
  }
  .payout-meta div {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 8px;
    font-size: 12px;
  }
  .label {
    color: var(--c-text-muted);
  }
  .value {
    color: var(--c-text-primary);
    font-family: var(--font-mono);
    font-weight: 600;
  }
  .table-wrap {
    max-height: 300px;
    overflow: auto;
    border: 1px solid var(--c-border);
    border-radius: var(--radius-sm);
  }
  table {
    width: 100%;
    border-collapse: collapse;
  }
  th, td {
    text-align: left;
    padding: 8px 10px;
    font-size: 12px;
    border-bottom: 1px solid var(--c-border);
  }
  th {
    font-size: 11px;
    color: var(--c-text-muted);
    text-transform: uppercase;
    letter-spacing: 0.03em;
    background: var(--c-bg-tertiary);
    position: sticky;
    top: 0;
    z-index: 1;
  }
  tr:last-child td {
    border-bottom: none;
  }
</style>
