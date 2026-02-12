<script lang="ts">
  import { toasts } from '../lib/stores'
</script>

<div class="toast-container">
  {#each $toasts as toast (toast.id)}
    <div class="toast toast-{toast.type} fade-in">
      <span class="toast-text">{toast.text}</span>
    </div>
  {/each}
</div>

<style>
  .toast-container {
    position: fixed;
    top: 56px;
    right: 12px;
    z-index: 900;
    display: flex;
    flex-direction: column;
    gap: 6px;
    max-width: 320px;
    pointer-events: none;
  }
  .toast {
    padding: 10px 14px;
    border-radius: var(--radius);
    font-size: 12px;
    pointer-events: auto;
    border-left: 3px solid;
    background: var(--c-bg-card);
    box-shadow: 0 4px 12px rgba(0,0,0,0.4);
  }
  .toast-info { border-color: var(--c-info); }
  .toast-success { border-color: var(--c-success); }
  .toast-warning { border-color: var(--c-warning); }
  .toast-danger { border-color: var(--c-danger); }
</style>
