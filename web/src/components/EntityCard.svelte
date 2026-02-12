<script lang="ts">
  import StatBar from './StatBar.svelte'

  export let entity: any = null
  export let compact: boolean = false
  export let onFire: (() => void) | null = null

  $: name = entity?.name || 'Unknown'
  $: type = entity?.type || entity?.entity_type || ''
  $: age = entity?.age || 0
  $: overall = entity?.overall || 0
  $: stats = entity?.stats || {}
  $: contract = entity?.contract || null

  const typeIcons: Record<string, string> = {
    Driver: '🏎️',
    Engineer: '🔧',
    Mechanic: '🔩',
    Strategist: '📊',
    Principal: '👔',
  }
</script>

<div class="entity-card" class:compact>
  <div class="entity-header">
    <span class="entity-icon">{typeIcons[type] || '👤'}</span>
    <div class="entity-info">
      <div class="entity-name">{name}</div>
      <div class="entity-meta">{type} · Age {age}</div>
    </div>
    <div class="entity-overall" class:high={overall >= 80} class:mid={overall >= 50 && overall < 80} class:low={overall < 50}>
      {Math.round(overall)}
    </div>
  </div>

  {#if !compact && Object.keys(stats).length > 0}
    <div class="entity-stats">
      {#each Object.entries(stats).slice(0, 6) as [key, val]}
        <StatBar label={key.replace(/_/g, ' ')} value={Number(val)} size="sm" />
      {/each}
    </div>
  {/if}

  {#if contract && !compact}
    <div class="entity-contract">
      💰 ${Math.round(contract.salary || 0).toLocaleString()}/yr
      · {contract.seasons_remaining || '?'} seasons
    </div>
  {/if}

  {#if onFire}
    <button class="btn btn-danger btn-sm fire-btn" on:click={onFire}>Fire</button>
  {/if}
</div>

<style>
  .entity-card {
    background: var(--c-bg-card);
    border: 1px solid var(--c-border);
    border-radius: var(--radius);
    padding: 10px;
    position: relative;
  }
  .entity-card.compact { padding: 8px; }
  .entity-header {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .entity-icon { font-size: 20px; }
  .entity-card.compact .entity-icon { font-size: 16px; }
  .entity-info { flex: 1; min-width: 0; }
  .entity-name {
    font-size: 13px;
    font-weight: 600;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .entity-card.compact .entity-name { font-size: 12px; }
  .entity-meta { font-size: 11px; color: var(--c-text-muted); }
  .entity-overall {
    width: 36px;
    height: 36px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    font-weight: 700;
    font-size: 14px;
    font-family: var(--font-mono);
    flex-shrink: 0;
  }
  .entity-overall.high { background: var(--c-success); color: #000; }
  .entity-overall.mid { background: var(--c-warning); color: #000; }
  .entity-overall.low { background: var(--c-danger); color: #fff; }
  .entity-card.compact .entity-overall { width: 28px; height: 28px; font-size: 12px; }
  .entity-stats {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 4px;
    margin-top: 8px;
  }
  .entity-contract {
    margin-top: 6px;
    font-size: 11px;
    color: var(--c-text-muted);
    padding-top: 6px;
    border-top: 1px solid var(--c-border);
  }
  .fire-btn {
    position: absolute;
    top: 8px;
    right: 8px;
  }
</style>
