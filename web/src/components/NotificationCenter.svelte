<script lang="ts">
  import { notifications } from '../lib/stores'
  import { sendCommand } from '../lib/ws'
  import { timeAgo } from '../lib/utils'

  let filter: 'all' | 'unread' | 'read' = 'all'

  $: items = $notifications || []
  $: filtered = filter === 'all' ? items
    : filter === 'unread' ? items.filter((n: any) => !n.read)
    : items.filter((n: any) => n.read)

  function markRead(id: string) {
    sendCommand({ cmd: 'ftb_notif_read', notification_id: id })
  }
  function markAllRead() {
    sendCommand({ cmd: 'ftb_notif_read_all' })
  }
  function dismiss(id: string) {
    sendCommand({ cmd: 'ftb_notif_dismiss', notification_id: id })
  }

  function iconFor(type: string): string {
    const icons: Record<string, string> = {
      race: '🏁', contract: '📝', finance: '💰', transfer: '🔄',
      development: '🔧', penalty: '⚠️', sponsor: '🤝', career: '🏆',
      calendar: '📅', alert: '🔔'
    }
    return icons[type] || '📌'
  }
</script>

<div class="tab-content scroll-y">
  <div class="notif-header">
    <h3>Notifications</h3>
    <button class="btn btn-ghost btn-sm" on:click={markAllRead}>Mark all read</button>
  </div>

  <div class="filter-bar">
    <button class="filter-chip" class:active={filter === 'all'} on:click={() => filter = 'all'}>All ({items.length})</button>
    <button class="filter-chip" class:active={filter === 'unread'} on:click={() => filter = 'unread'}>
      Unread ({items.filter((n) => !n.read).length})
    </button>
    <button class="filter-chip" class:active={filter === 'read'} on:click={() => filter = 'read'}>Read</button>
  </div>

  {#if filtered.length === 0}
    <div class="empty-state">
      <p>No {filter === 'all' ? '' : filter} notifications.</p>
    </div>
  {:else}
    <div class="notif-list">
      {#each filtered as notif}
        <div class="notif-item" class:unread={!notif.read}>
          <span class="notif-icon">{iconFor(notif.type)}</span>
          <div class="notif-body">
            <div class="notif-title">{notif.title || notif.text || 'Notification'}</div>
            {#if notif.detail || notif.message}
              <div class="notif-detail">{notif.detail || notif.message}</div>
            {/if}
            {#if notif.tick || notif.timestamp}
              <div class="notif-meta">
                {#if notif.tick}T{notif.tick}{/if}
                {#if notif.timestamp} · {timeAgo(notif.timestamp)}{/if}
              </div>
            {/if}
          </div>
          <div class="notif-actions">
            {#if !notif.read}
              <button class="btn btn-ghost btn-xs" on:click={() => markRead(notif.id)}>✓</button>
            {/if}
            <button class="btn btn-ghost btn-xs" on:click={() => dismiss(notif.id)}>✕</button>
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .notif-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 10px;
  }
  .notif-header h3 { font-size: 16px; }
  .filter-bar {
    display: flex;
    gap: 6px;
    margin-bottom: 12px;
  }
  .filter-chip {
    padding: 4px 10px;
    font-size: 11px;
    background: var(--c-bg-card);
    border: 1px solid var(--c-border);
    border-radius: 12px;
    color: var(--c-text-secondary);
    cursor: pointer;
  }
  .filter-chip.active {
    background: var(--c-accent);
    color: var(--c-bg-primary);
    border-color: var(--c-accent);
  }
  .notif-list {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .notif-item {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 10px;
    background: var(--c-bg-card);
    border-radius: var(--radius-sm);
    border-left: 3px solid transparent;
  }
  .notif-item.unread {
    border-left-color: var(--c-accent);
    background: rgba(76, 201, 240, 0.04);
  }
  .notif-icon { font-size: 18px; flex-shrink: 0; margin-top: 1px; }
  .notif-body { flex: 1; min-width: 0; }
  .notif-title { font-size: 13px; font-weight: 500; }
  .notif-detail { font-size: 12px; color: var(--c-text-secondary); margin-top: 2px; }
  .notif-meta { font-size: 10px; color: var(--c-text-muted); font-family: var(--font-mono); margin-top: 4px; }
  .notif-actions {
    display: flex;
    gap: 4px;
    flex-shrink: 0;
  }
  .btn-xs { padding: 2px 6px; font-size: 11px; }
  .empty-state {
    text-align: center;
    padding: 48px 16px;
    color: var(--c-text-muted);
  }
</style>
