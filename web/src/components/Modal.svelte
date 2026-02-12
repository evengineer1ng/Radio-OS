<script lang="ts">
  import { createEventDispatcher } from 'svelte'

  export let show: boolean = false
  export let title: string = ''
  export let size: 'sm' | 'md' | 'lg' = 'md'

  const dispatch = createEventDispatcher()

  function close() {
    show = false
    dispatch('close')
  }

  function handleBackdrop(e: MouseEvent) {
    if ((e.target as HTMLElement).classList.contains('modal-backdrop')) close()
  }
</script>

{#if show}
  <!-- svelte-ignore a11y-click-events-have-key-events -->
  <div class="modal-backdrop" on:click={handleBackdrop} role="dialog">
    <div class="modal-content {size}">
      {#if title}
        <div class="modal-header">
          <h3>{title}</h3>
          <button class="modal-close" on:click={close}>✕</button>
        </div>
      {/if}
      <div class="modal-body">
        <slot />
      </div>
    </div>
  </div>
{/if}

<style>
  .modal-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.7);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    padding: 16px;
    animation: fadeIn 0.15s ease-out;
  }
  .modal-content {
    background: var(--c-bg-secondary);
    border: 1px solid var(--c-border);
    border-radius: var(--radius-lg);
    max-height: 90vh;
    overflow-y: auto;
    width: 100%;
  }
  .modal-content.sm { max-width: 360px; }
  .modal-content.md { max-width: 520px; }
  .modal-content.lg { max-width: 720px; }
  .modal-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 14px 16px;
    border-bottom: 1px solid var(--c-border);
  }
  .modal-header h3 {
    font-size: 15px;
    font-weight: 600;
  }
  .modal-close {
    background: none;
    border: none;
    color: var(--c-text-muted);
    font-size: 18px;
    cursor: pointer;
    padding: 4px 8px;
    border-radius: 4px;
  }
  .modal-close:hover { color: var(--c-text-primary); background: var(--c-bg-hover); }
  .modal-body { padding: 16px; }

  @keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
  }
</style>
