<script lang="ts">
  import { gameState } from '../lib/stores'
  import { sendCommand } from '../lib/api'
  import { formatCurrency } from '../lib/utils'

  $: team = $gameState.player_team
  $: rdProjects = team?.rd_projects || []
  $: infra = team?.infrastructure || {}

  function cancelProject(id: string) {
    sendCommand({ cmd: 'ftb_cancel_rd_project', project_id: id })
  }
  function upgradeInfra(facility: string) {
    sendCommand({ cmd: 'ftb_upgrade_infrastructure', facility, amount: 10 })
  }
  function sellInfra(facility: string) {
    sendCommand({ cmd: 'ftb_sell_infrastructure', facility })
  }
</script>

<div class="dev-view">
  <!-- Active R&D -->
  <div class="card">
    <div class="section-title">🔧 Active R&D Projects ({rdProjects.length})</div>
    <div class="rd-list">
      {#each rdProjects as proj}
        <div class="rd-item">
          <div class="rd-info">
            <div class="rd-name">{proj.subsystem || 'Project'}</div>
            <div class="rd-meta">Risk: {Math.round((proj.risk_level || 0) * 100)}% · Budget: {formatCurrency(proj.budget || 0)}</div>
            <div class="rd-bar">
              <div class="rd-fill" style="width: {Math.round((proj.progress || 0) * 100)}%"></div>
            </div>
            <div class="rd-progress">{Math.round((proj.progress || 0) * 100)}%</div>
          </div>
          <button class="btn btn-danger btn-sm" on:click={() => cancelProject(proj.id)}>Cancel</button>
        </div>
      {:else}
        <div class="empty-state">No active projects</div>
      {/each}
    </div>
  </div>

  <!-- Infrastructure -->
  <div class="card">
    <div class="section-title">🏭 Infrastructure</div>
    <div class="infra-list">
      {#each Object.entries(infra) as [facility, quality]}
        <div class="infra-item">
          <div class="infra-info">
            <span class="infra-name">{facility.replace(/_/g, ' ')}</span>
            <span class="infra-quality">Quality: {Math.round(Number(quality))}</span>
          </div>
          <div class="infra-actions">
            <button class="btn btn-primary btn-sm" on:click={() => upgradeInfra(facility)}>Upgrade</button>
            <button class="btn btn-ghost btn-sm" on:click={() => sellInfra(facility)}>Sell</button>
          </div>
        </div>
      {:else}
        <div class="empty-state">No facilities</div>
      {/each}
    </div>
  </div>
</div>

<style>
  .dev-view { display: flex; flex-direction: column; gap: 12px; padding: 12px; }
  .rd-list { display: flex; flex-direction: column; gap: 8px; }
  .rd-item {
    display: flex; justify-content: space-between; align-items: center;
    padding: 10px; background: var(--c-bg-tertiary); border-radius: var(--radius);
  }
  .rd-info { flex: 1; }
  .rd-name { font-size: 13px; font-weight: 600; }
  .rd-meta { font-size: 11px; color: var(--c-text-muted); margin: 2px 0 6px; }
  .rd-bar { height: 4px; background: var(--c-bg-input); border-radius: 2px; overflow: hidden; }
  .rd-fill { height: 100%; background: var(--c-accent); border-radius: 2px; transition: width 0.3s; }
  .rd-progress { font-size: 11px; color: var(--c-accent); font-family: var(--font-mono); margin-top: 2px; }
  .infra-list { display: flex; flex-direction: column; gap: 6px; }
  .infra-item {
    display: flex; justify-content: space-between; align-items: center;
    padding: 8px; background: var(--c-bg-tertiary); border-radius: var(--radius-sm);
  }
  .infra-name { font-size: 13px; font-weight: 500; text-transform: capitalize; }
  .infra-quality { font-size: 11px; color: var(--c-text-muted); display: block; }
  .infra-actions { display: flex; gap: 4px; }
  .empty-state { text-align: center; color: var(--c-text-muted); padding: 20px; font-size: 13px; }
</style>
