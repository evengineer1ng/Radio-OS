<script lang="ts">
  export let label: string = ''
  export let value: string | number = ''
  export let sublabel: string = ''
  export let color: string = 'var(--c-accent)'
</script>

<div class="metric" style="--metric-color: {color}">
  <div class="metric-value">{value}</div>
  <div class="metric-label">{label}</div>
  {#if sublabel}<div class="metric-sub">{sublabel}</div>{/if}
</div>

<style>
  .metric {
    text-align: center;
    padding: 12px 8px;
    background: var(--c-bg-tertiary);
    border-radius: var(--radius);
    border: 1px solid var(--c-border);
  }
  .metric-value {
    font-size: 22px;
    font-weight: 700;
    color: var(--metric-color);
    font-family: var(--font-mono);
    line-height: 1.2;
  }
  .metric-label {
    font-size: 11px;
    color: var(--c-text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.3px;
    margin-top: 4px;
  }
  .metric-sub {
    font-size: 10px;
    color: var(--c-text-muted);
    margin-top: 2px;
  }
</style>
