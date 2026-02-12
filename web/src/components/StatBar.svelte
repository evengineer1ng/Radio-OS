<script lang="ts">
  export let label: string = ''
  export let value: number = 0
  export let max: number = 100
  export let showValue: boolean = true
  export let size: 'sm' | 'md' = 'md'

  $: pct = Math.min(Math.max((value / max) * 100, 0), 100)
  $: color = pct >= 80 ? 'var(--c-success)' : pct >= 50 ? 'var(--c-warning)' : 'var(--c-danger)'
</script>

<div class="stat-bar {size}">
  {#if label}
    <div class="stat-label">
      <span>{label}</span>
      {#if showValue}<span class="stat-value">{Math.round(value)}/{max}</span>{/if}
    </div>
  {/if}
  <div class="bar-track">
    <div class="bar-fill" style="width: {pct}%; background: {color}"></div>
  </div>
</div>

<style>
  .stat-bar { width: 100%; }
  .stat-label {
    display: flex;
    justify-content: space-between;
    font-size: 11px;
    color: var(--c-text-secondary);
    margin-bottom: 3px;
  }
  .stat-value { font-family: var(--font-mono); font-size: 10px; color: var(--c-text-muted); }
  .bar-track {
    width: 100%;
    height: 6px;
    background: var(--c-bg-input);
    border-radius: 3px;
    overflow: hidden;
  }
  .stat-bar.sm .bar-track { height: 4px; }
  .bar-fill {
    height: 100%;
    border-radius: 3px;
    transition: width 0.3s ease;
  }
</style>
