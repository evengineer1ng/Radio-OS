<script lang="ts">
  import Modal from './Modal.svelte'
  import StatBar from './StatBar.svelte'
  import { formatCurrency } from '../lib/utils'

  export let entity: any = null
  export let show: boolean = false

  $: name = entity?.name || 'Unknown'
  $: type = entity?.type || entity?.entity_type || ''
  $: age = entity?.age || 0
  $: overall = entity?.overall || 0
  $: stats = entity?.stats || {}
  $: contract = entity?.contract || null
  $: potential = entity?.potential_ceiling || entity?.potential_rating || null
  $: form = entity?.form_momentum ?? null
  $: morale = entity?.morale_baseline ?? null

  const typeIcons: Record<string, string> = {
    Driver: '🏎️',
    Engineer: '🔧',
    Mechanic: '🔩',
    Strategist: '📊',
    Principal: '👔',
  }

  function ratingClass(val: number): string {
    if (val >= 80) return 'high'
    if (val >= 50) return 'mid'
    return 'low'
  }
</script>

<Modal bind:show title="{typeIcons[type] || '👤'} {name}" size="md" on:close>
  <div class="detail-content">
    <!-- Header Badge -->
    <div class="detail-header">
      <div class="avatar {ratingClass(overall)}">
        <span class="avatar-icon">{typeIcons[type] || '👤'}</span>
        <span class="avatar-rating">{Math.round(overall)}</span>
      </div>
      <div class="header-info">
        <h2 class="detail-name">{name}</h2>
        <div class="detail-meta">{type} · Age {age}</div>
        <div class="overall-label">Overall: <strong class="{ratingClass(overall)}-text">{Math.round(overall)}</strong></div>
      </div>
    </div>

    <!-- Key Metrics -->
    {#if potential !== null || form !== null || morale !== null}
      <div class="detail-section">
        <div class="detail-section-title">⚡ Key Metrics</div>
        <div class="metrics-grid">
          <div class="metric-item">
            <span class="metric-label">Overall</span>
            <span class="metric-value {ratingClass(overall)}-text">{Math.round(overall)}</span>
          </div>
          {#if potential !== null}
            <div class="metric-item">
              <span class="metric-label">Potential</span>
              <span class="metric-value">{Math.round(potential)}</span>
            </div>
          {/if}
          {#if form !== null}
            <div class="metric-item">
              <span class="metric-label">Form</span>
              <span class="metric-value" class:positive={form > 0} class:negative={form < 0}>
                {form > 0 ? '+' : ''}{Number(form).toFixed(1)}
              </span>
            </div>
          {/if}
          {#if morale !== null}
            <div class="metric-item">
              <span class="metric-label">Morale</span>
              <span class="metric-value">{Math.round(morale)}</span>
            </div>
          {/if}
        </div>
      </div>
    {/if}

    <!-- All Stats -->
    {#if Object.keys(stats).length > 0}
      <div class="detail-section">
        <div class="detail-section-title">📊 Attributes</div>
        <div class="stats-grid">
          {#each Object.entries(stats) as [key, val]}
            <StatBar label={key.replace(/_/g, ' ')} value={Number(val)} />
          {/each}
        </div>
      </div>
    {/if}

    <!-- Contract Info -->
    {#if contract}
      <div class="detail-section">
        <div class="detail-section-title">📄 Contract</div>
        <div class="contract-grid">
          <div class="contract-row">
            <span class="contract-label">Salary</span>
            <span class="contract-value">{formatCurrency(contract.salary || 0)}/yr</span>
          </div>
          <div class="contract-row">
            <span class="contract-label">Seasons Remaining</span>
            <span class="contract-value">{contract.seasons_remaining ?? '—'}</span>
          </div>
          {#if contract.buyout}
            <div class="contract-row">
              <span class="contract-label">Buyout Clause</span>
              <span class="contract-value">{formatCurrency(contract.buyout)}</span>
            </div>
          {/if}
        </div>
      </div>
    {/if}

    <!-- Raw Data Fallback (if entity has extra fields) -->
    {#if entity}
      {@const extraKeys = Object.keys(entity).filter(k => !['name','type','entity_type','age','overall','stats','contract','overall_rating','potential_ceiling','potential_rating','form_momentum','morale_baseline','display_name','entity_id'].includes(k))}
      {#if extraKeys.length > 0}
        <div class="detail-section">
          <div class="detail-section-title">ℹ️ Additional Info</div>
          <div class="extra-grid">
            {#each extraKeys as key}
              {#if typeof entity[key] !== 'object' || entity[key] === null}
                <div class="extra-row">
                  <span class="extra-label">{key.replace(/_/g, ' ')}</span>
                  <span class="extra-value">{entity[key] ?? '—'}</span>
                </div>
              {/if}
            {/each}
          </div>
        </div>
      {/if}
    {/if}
  </div>
</Modal>

<style>
  .detail-content {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  /* Header */
  .detail-header {
    display: flex;
    align-items: center;
    gap: 16px;
  }
  .avatar {
    width: 64px;
    height: 64px;
    border-radius: 50%;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }
  .avatar.high { background: var(--c-success); color: #000; }
  .avatar.mid { background: var(--c-warning); color: #000; }
  .avatar.low { background: var(--c-danger); color: #fff; }
  .avatar-icon { font-size: 22px; line-height: 1; }
  .avatar-rating { font-size: 14px; font-weight: 800; font-family: var(--font-mono); }
  .header-info { flex: 1; min-width: 0; }
  .detail-name {
    font-size: 18px;
    font-weight: 700;
    margin: 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .detail-meta {
    font-size: 13px;
    color: var(--c-text-muted);
    margin-top: 2px;
  }
  .overall-label {
    font-size: 13px;
    margin-top: 4px;
  }
  .high-text { color: var(--c-success); }
  .mid-text { color: var(--c-warning); }
  .low-text { color: var(--c-danger); }

  /* Sections */
  .detail-section {
    border-top: 1px solid var(--c-border);
    padding-top: 12px;
  }
  .detail-section-title {
    font-size: 13px;
    font-weight: 600;
    margin-bottom: 8px;
    color: var(--c-text-secondary);
  }

  /* Key Metrics */
  .metrics-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 8px;
  }
  .metric-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 6px 10px;
    background: var(--c-bg-tertiary);
    border-radius: var(--radius-sm);
    font-size: 13px;
  }
  .metric-label { color: var(--c-text-muted); }
  .metric-value { font-weight: 600; font-family: var(--font-mono); }
  .metric-value.positive { color: var(--c-success); }
  .metric-value.negative { color: var(--c-danger); }

  /* Stats */
  .stats-grid {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  /* Contract */
  .contract-grid {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .contract-row {
    display: flex;
    justify-content: space-between;
    font-size: 13px;
    padding: 4px 0;
  }
  .contract-label { color: var(--c-text-muted); }
  .contract-value { font-weight: 500; font-family: var(--font-mono); }

  /* Extra info */
  .extra-grid {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .extra-row {
    display: flex;
    justify-content: space-between;
    font-size: 12px;
    padding: 3px 0;
  }
  .extra-label { color: var(--c-text-muted); text-transform: capitalize; }
  .extra-value { font-weight: 500; font-family: var(--font-mono); }
</style>
