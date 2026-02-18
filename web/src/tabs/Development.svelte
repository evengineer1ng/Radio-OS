<script lang="ts">
  import { gameState, addToast } from '../lib/stores'
  import { fetchRDCatalog, startRDProject, cancelRDProject, upgradeInfrastructure, sellInfrastructure, safeRefreshState } from '../lib/api'
  import { formatCurrency } from '../lib/utils'
  import StatBar from '../components/StatBar.svelte'
  import Modal from '../components/Modal.svelte'

  $: team = $gameState.player_team
  $: rdProjects = team?.rd_projects || []
  $: activeProjects = rdProjects.filter((p: any) => !p.completed && !p.cancelled)
  $: completedProjects = rdProjects.filter((p: any) => p.completed)
  $: infra = team?.infrastructure || {}
  $: cash = team?.budget?.cash || 0

  let working = false
  let showCatalog = false
  let catalog: any[] = []
  let catalogLoading = false

  // Infrastructure display helpers
  const facilityIcons: Record<string, string> = {
    factory: '🏭', wind_tunnel: '🌬️', simulator: '💻',
    design_office: '📐', test_track: '🏎️', pit_equipment: '🔧',
    data_center: '📊', hospitality: '🏠',
  }
  const facilityNames: Record<string, string> = {
    factory: 'Factory', wind_tunnel: 'Wind Tunnel', simulator: 'Simulator',
    design_office: 'Design Office', test_track: 'Test Track',
    pit_equipment: 'Pit Equipment', data_center: 'Data Center',
    hospitality: 'Hospitality Suite',
  }

  // R&D risk display
  const riskColors: Record<string, string> = {
    low: 'var(--c-success)', medium: 'var(--c-warning)', high: 'var(--c-danger)',
  }

  async function refreshAfterCommand() {
    await new Promise(r => setTimeout(r, 600))
    await safeRefreshState()
  }

  async function openCatalog() {
    catalogLoading = true
    showCatalog = true
    try {
      catalog = await fetchRDCatalog()
    } catch (e) {
      addToast('Failed to load R&D catalog', 'error')
      catalog = []
    }
    catalogLoading = false
  }

  async function handleStartProject(project: any) {
    if (working) return
    if (cash < project.cost) {
      addToast(`Need ${formatCurrency(project.cost)} — only have ${formatCurrency(cash)}`, 'error')
      return
    }
    const alreadyRunning = activeProjects.some((p: any) => p.id === project.id)
    if (alreadyRunning) {
      addToast('Already running this project', 'error')
      return
    }
    working = true
    try {
      await startRDProject(project.id, project.cost)
      await refreshAfterCommand()
      addToast(`Started: ${project.name}`, 'success')
      showCatalog = false
    } catch (e) { addToast('Start failed', 'error') }
    working = false
  }

  async function handleCancel(id: string) {
    if (working) return
    if (!confirm('Cancel this R&D project? Partial refund only.')) return
    working = true
    try {
      await cancelRDProject(id)
      await refreshAfterCommand()
      addToast('R&D project cancelled', 'success')
    } catch (e) { addToast('Cancel failed', 'error') }
    working = false
  }

  async function handleUpgrade(facility: string) {
    if (working) return
    working = true
    try {
      await upgradeInfrastructure(facility, 10)
      await refreshAfterCommand()
      addToast(`Upgraded ${facilityNames[facility] || facility}`, 'success')
    } catch (e) { addToast('Upgrade failed', 'error') }
    working = false
  }

  async function handleSell(facility: string) {
    if (working) return
    if (!confirm(`Sell ${facilityNames[facility] || facility}? You'll receive a partial refund.`)) return
    working = true
    try {
      await sellInfrastructure(facility)
      await refreshAfterCommand()
      addToast(`Sold ${facilityNames[facility] || facility}`, 'success')
    } catch (e) { addToast('Sell failed', 'error') }
    working = false
  }

  function qualityColor(q: number): string {
    if (q >= 80) return 'var(--c-success)'
    if (q >= 50) return 'var(--c-warning)'
    return 'var(--c-danger)'
  }
</script>

<div class="dev-view">
  <!-- Active R&D -->
  <div class="card">
    <div class="section-header">
      <div class="section-title">� R&D Projects ({activeProjects.length})</div>
      <button class="btn btn-primary btn-sm" disabled={working} on:click={openCatalog}>+ New Project</button>
    </div>
    <div class="rd-list">
      {#each activeProjects as proj}
        <div class="rd-item">
          <div class="rd-info">
            <div class="rd-name">{proj.name || proj.id}</div>
            <div class="rd-meta">
              <span class="rd-risk" style="color: {riskColors[proj.risk_level] || 'var(--c-text-muted)'}">
                {proj.risk_level} risk
              </span>
              <span>·</span>
              <span>{Math.round((proj.success_rate || 0.7) * 100)}% success</span>
              <span>·</span>
              <span>{formatCurrency(proj.budget || 0)}</span>
            </div>
            {#if proj.target_stat}
              <div class="rd-target">Target: {proj.target_stat.replace(/_/g, ' ')} +{proj.target_improvement}</div>
            {/if}
            <div class="rd-bar">
              <div class="rd-fill" style="width: {Math.round((proj.progress || 0) * 100)}%"></div>
            </div>
            <div class="rd-progress">
              {Math.round((proj.progress || 0) * 100)}%
              ({proj.progress_ticks || 0}/{proj.duration_ticks || '?'} ticks)
            </div>
          </div>
          <button class="btn btn-danger btn-sm" disabled={working} on:click={() => handleCancel(proj.id)}>Cancel</button>
        </div>
      {:else}
        <div class="empty-state">No active projects — start one to improve your car</div>
      {/each}
    </div>
  </div>

  <!-- Infrastructure -->
  <div class="card">
    <div class="section-title">🏭 Infrastructure</div>
    <div class="infra-grid">
      {#each Object.entries(infra) as [facility, quality]}
        <div class="infra-item">
          <div class="infra-header">
            <span class="infra-icon">{facilityIcons[facility] || '🏗️'}</span>
            <div class="infra-label">
              <span class="infra-name">{facilityNames[facility] || facility.replace(/_/g, ' ')}</span>
              <span class="infra-quality" style="color: {qualityColor(Number(quality))}">
                Q{Math.round(Number(quality))}
              </span>
            </div>
          </div>
          <StatBar label="" value={Number(quality)} max={100} size="sm" />
          <div class="infra-actions">
            <button class="btn btn-primary btn-sm" disabled={working} on:click={() => handleUpgrade(facility)}>
              ⬆️ +10
            </button>
            <button class="btn btn-ghost btn-sm" disabled={working} on:click={() => handleSell(facility)}>
              Sell
            </button>
          </div>
        </div>
      {:else}
        <div class="empty-state">No facilities</div>
      {/each}
    </div>
  </div>
</div>

<!-- R&D Catalog Modal -->
<Modal bind:show={showCatalog} title="🔬 R&D Project Catalog" size="lg">
  <div class="catalog-content">
    {#if catalogLoading}
      <div class="empty-state">Loading catalog…</div>
    {:else if catalog.length === 0}
      <div class="empty-state">No R&D projects available</div>
    {:else}
      <div class="catalog-info">
        Available cash: <strong>{formatCurrency(cash)}</strong>
        · Active projects: {activeProjects.length}
      </div>
      <div class="catalog-grid">
        {#each catalog as project}
          {@const alreadyRunning = activeProjects.some((p) => p.id === project.id)}
          {@const canAfford = cash >= project.cost}
          <div class="catalog-card" class:disabled={alreadyRunning || !canAfford}>
            <div class="cat-header">
              <div class="cat-name">{project.name}</div>
              <span class="cat-risk" style="color: {riskColors[project.risk_level] || 'var(--c-text-muted)'}">
                {project.risk_level}
              </span>
            </div>
            <div class="cat-desc">{project.description}</div>
            {#if project.min_tier > 1}
              <div class="cat-tier">Requires Tier {project.min_tier}+</div>
            {/if}
            <div class="cat-stats">
              <div class="cat-stat">
                <span class="cat-label">Cost</span>
                <span class="cat-value">{formatCurrency(project.cost)}</span>
              </div>
              <div class="cat-stat">
                <span class="cat-label">Duration</span>
                <span class="cat-value">{project.duration_ticks} ticks</span>
              </div>
              <div class="cat-stat">
                <span class="cat-label">Success</span>
                <span class="cat-value">{Math.round(project.base_success_rate * 100)}%</span>
              </div>
              {#if project.target_stat}
                <div class="cat-stat">
                  <span class="cat-label">Target</span>
                  <span class="cat-value">{project.target_stat.replace(/_/g, ' ')} +{project.target_improvement}</span>
                </div>
              {/if}
              {#if project.generates_part}
                <div class="cat-stat">
                  <span class="cat-label">Generates</span>
                  <span class="cat-value">{project.part_type} part</span>
                </div>
              {/if}
            </div>
            <button
              class="btn btn-primary btn-sm cat-start"
              disabled={working || alreadyRunning || !canAfford}
              on:click={() => handleStartProject(project)}
            >
              {#if alreadyRunning}Already Running
              {:else if !canAfford}Can't Afford
              {:else}Start Project{/if}
            </button>
          </div>
        {/each}
      </div>
    {/if}
  </div>
</Modal>

<style>
  .dev-view { display: flex; flex-direction: column; gap: 12px; padding: 12px; }
  .section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
  .rd-list { display: flex; flex-direction: column; gap: 8px; }
  .rd-item {
    display: flex; justify-content: space-between; align-items: center;
    padding: 10px; background: var(--c-bg-tertiary); border-radius: var(--radius);
  }
  .rd-info { flex: 1; min-width: 0; }
  .rd-name { font-size: 13px; font-weight: 600; }
  .rd-meta { font-size: 11px; color: var(--c-text-muted); margin: 2px 0; display: flex; gap: 4px; flex-wrap: wrap; }
  .rd-risk { font-weight: 500; text-transform: capitalize; }
  .rd-target { font-size: 11px; color: var(--c-accent); margin-bottom: 4px; text-transform: capitalize; }
  .rd-bar { height: 4px; background: var(--c-bg-input); border-radius: 2px; overflow: hidden; margin-top: 4px; }
  .rd-fill { height: 100%; background: var(--c-accent); border-radius: 2px; transition: width 0.3s; }
  .rd-progress { font-size: 11px; color: var(--c-accent); font-family: var(--font-mono); margin-top: 2px; }

  .infra-grid { display: flex; flex-direction: column; gap: 8px; }
  .infra-item {
    padding: 10px; background: var(--c-bg-tertiary); border-radius: var(--radius);
  }
  .infra-header { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
  .infra-icon { font-size: 18px; }
  .infra-label { display: flex; justify-content: space-between; flex: 1; align-items: baseline; }
  .infra-name { font-size: 13px; font-weight: 500; text-transform: capitalize; }
  .infra-quality { font-size: 12px; font-family: var(--font-mono); font-weight: 600; }
  .infra-actions { display: flex; gap: 4px; margin-top: 6px; justify-content: flex-end; }

  /* Catalog modal */
  .catalog-content { display: flex; flex-direction: column; gap: 12px; }
  .catalog-info { font-size: 12px; color: var(--c-text-muted); padding: 4px 0; }
  .catalog-grid { display: flex; flex-direction: column; gap: 8px; max-height: 60vh; overflow-y: auto; }
  .catalog-card {
    padding: 12px; background: var(--c-bg-tertiary); border-radius: var(--radius);
    border: 1px solid var(--c-border); transition: border-color 0.15s;
  }
  .catalog-card:not(.disabled):hover { border-color: var(--c-accent); }
  .catalog-card.disabled { opacity: 0.5; }
  .cat-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
  .cat-name { font-size: 14px; font-weight: 600; }
  .cat-risk { font-size: 11px; font-weight: 500; text-transform: capitalize; padding: 2px 6px; background: var(--c-bg-input); border-radius: var(--radius-sm); }
  .cat-desc { font-size: 12px; color: var(--c-text-muted); margin-bottom: 4px; }
  .cat-tier { font-size: 11px; color: var(--c-warning); margin-bottom: 8px; font-weight: 500; }
  .cat-stats { display: grid; grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); gap: 4px; margin-bottom: 8px; }
  .cat-stat { display: flex; justify-content: space-between; font-size: 11px; padding: 2px 0; }
  .cat-label { color: var(--c-text-muted); }
  .cat-value { font-family: var(--font-mono); }
  .cat-start { width: 100%; }

  .empty-state { text-align: center; color: var(--c-text-muted); padding: 20px; font-size: 13px; }
</style>
