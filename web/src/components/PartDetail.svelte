<script lang="ts">
  import Modal from './Modal.svelte'
  import StatBar from './StatBar.svelte'
  import { formatCurrency } from '../lib/utils'

  export let part: any = null
  export let show: boolean = false
  export let mode: 'equipped' | 'inventory' | 'marketplace' = 'marketplace'

  export let onEquip: ((id: string) => void) | null = null
  export let onSell: ((id: string) => void) | null = null
  export let onBuy: ((id: string, cost: number) => void) | null = null

  $: name = part?.name || 'Unknown Part'
  $: type = part?.type || part?.part_type || ''
  $: quality = part?.quality || 0
  $: cost = part?.cost || 0
  $: partId = part?.id || part?.part_id || ''
  $: stats = part?.stats || {}
  $: generation = part?.generation || 1
  $: manufacturer = part?.manufacturer_id || ''
  $: effectiveness = part?.effectiveness ?? 1.0

  function qualityClass(q: number): string {
    if (q >= 80) return 'high'
    if (q >= 50) return 'mid'
    return 'low'
  }

  const typeIcons: Record<string, string> = {
    engine: '🔥',
    chassis: '🛡️',
    aero: '💨',
    aero_package: '💨',
    suspension: '🔧',
    gearbox: '⚙️',
    brakes: '🛑',
    tires: '🛞',
    electronics: '⚡',
    cooling: '❄️',
    transmission: '🔗',
  }
</script>

<Modal bind:show title="⚙️ {name}" size="md" on:close>
  <div class="detail-content">
    <!-- Header -->
    <div class="part-header">
      <div class="part-icon-badge {qualityClass(quality)}">
        <span class="part-icon-lg">{typeIcons[type.toLowerCase()] || '⚙️'}</span>
        <span class="part-q-lg">Q{Math.round(quality)}</span>
      </div>
      <div class="part-header-info">
        <h2 class="part-detail-name">{name}</h2>
        <div class="part-detail-type">{type}</div>
        <div class="part-detail-quality">
          Quality: <strong class="{qualityClass(quality)}-text">{Math.round(quality)}</strong>
        </div>
      </div>
    </div>

    <!-- Key Info -->
    <div class="detail-section">
      <div class="detail-section-title">ℹ️ Info</div>
      <div class="info-grid">
        <div class="info-row">
          <span class="info-label">Generation</span>
          <span class="info-value">Mk{generation}</span>
        </div>
        {#if manufacturer}
          <div class="info-row">
            <span class="info-label">Manufacturer</span>
            <span class="info-value">{manufacturer.replace(/_/g, ' ')}</span>
          </div>
        {/if}
        <div class="info-row">
          <span class="info-label">Effectiveness</span>
          <span class="info-value" class:warn={effectiveness < 0.8}>{Math.round(effectiveness * 100)}%</span>
        </div>
        {#if cost > 0}
          <div class="info-row">
            <span class="info-label">{mode === 'marketplace' ? 'Market Price' : 'Estimated Value'}</span>
            <span class="info-value cost">{formatCurrency(cost)}</span>
          </div>
        {/if}
      </div>
    </div>

    <!-- Quality Bar -->
    <div class="detail-section">
      <div class="detail-section-title">📊 Overall Quality</div>
      <StatBar label="Quality" value={quality} max={100} />
    </div>

    <!-- Part Stats -->
    {#if Object.keys(stats).length > 0}
      <div class="detail-section">
        <div class="detail-section-title">🔬 Part Statistics</div>
        <div class="stats-grid">
          {#each Object.entries(stats) as [key, val]}
            <StatBar label={key.replace(/_/g, ' ')} value={Number(val)} />
          {/each}
        </div>
      </div>
    {/if}

    <!-- Actions -->
    <div class="detail-actions">
      {#if mode === 'marketplace' && onBuy}
        <button class="btn btn-primary" on:click={() => { onBuy?.(partId, cost); show = false }}>
          🛒 Buy for {formatCurrency(cost)}
        </button>
      {/if}
      {#if mode === 'inventory' && onEquip}
        <button class="btn btn-primary" on:click={() => { onEquip?.(partId); show = false }}>
          ⚙️ Equip
        </button>
      {/if}
      {#if (mode === 'inventory' || mode === 'equipped') && onSell}
        <button class="btn btn-danger" on:click={() => { onSell?.(partId); show = false }}>
          💸 Sell
        </button>
      {/if}
    </div>
  </div>
</Modal>

<style>
  .detail-content {
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  /* Header */
  .part-header {
    display: flex;
    align-items: center;
    gap: 16px;
  }
  .part-icon-badge {
    width: 64px;
    height: 64px;
    border-radius: 12px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }
  .part-icon-badge.high { background: var(--c-success); color: #000; }
  .part-icon-badge.mid { background: var(--c-warning); color: #000; }
  .part-icon-badge.low { background: var(--c-danger); color: #fff; }
  .part-icon-lg { font-size: 22px; line-height: 1; }
  .part-q-lg { font-size: 13px; font-weight: 800; font-family: var(--font-mono); }
  .part-header-info { flex: 1; min-width: 0; }
  .part-detail-name {
    font-size: 18px;
    font-weight: 700;
    margin: 0;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .part-detail-type {
    font-size: 13px;
    color: var(--c-text-muted);
    margin-top: 2px;
    text-transform: capitalize;
  }
  .part-detail-quality {
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

  /* Info grid */
  .info-grid {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .info-row {
    display: flex;
    justify-content: space-between;
    font-size: 13px;
    padding: 3px 0;
  }
  .info-label { color: var(--c-text-muted); }
  .info-value { font-weight: 600; font-family: var(--font-mono); }
  .info-value.cost { color: var(--c-warning); }
  .info-value.warn { color: var(--c-danger); }

  /* Stats grid */
  .stats-grid {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  /* Actions */
  .detail-actions {
    border-top: 1px solid var(--c-border);
    padding-top: 12px;
    display: flex;
    gap: 8px;
    justify-content: flex-end;
  }
</style>
