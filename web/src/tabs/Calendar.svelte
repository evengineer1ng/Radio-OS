<script lang="ts">
  import { gameState } from '../lib/stores'
  import { sendCommand } from '../lib/api'

  $: calendar = $gameState?.calendar || {}
  $: days = calendar.days || []
  $: currentDay = calendar.current_day || 0
  $: month = calendar.month_label || ''
  $: year = calendar.year || ''

  let filterCategory = 'all'

  const categories = [
    { value: 'all', label: 'All' },
    { value: 'race', label: '🏁 Races' },
    { value: 'deadline', label: '⏰ Deadlines' },
    { value: 'transfer', label: '🔄 Transfers' },
    { value: 'contract', label: '📝 Contracts' },
    { value: 'development', label: '🔧 Development' },
  ]

  $: filteredDays = filterCategory === 'all'
    ? days
    : days.filter((d: any) => d.events?.some((e: any) => e.category === filterCategory))

  function prevMonth() { sendCommand({ cmd: 'ftb_calendar_nav', direction: 'prev' }) }
  function nextMonth() { sendCommand({ cmd: 'ftb_calendar_nav', direction: 'next' }) }
</script>

<div class="tab-content scroll-y">
  <div class="calendar-header">
    <button class="btn btn-ghost btn-sm" on:click={prevMonth}>←</button>
    <h3>{month} {year}</h3>
    <button class="btn btn-ghost btn-sm" on:click={nextMonth}>→</button>
  </div>

  <div class="filter-bar">
    {#each categories as cat}
      <button class="filter-chip" class:active={filterCategory === cat.value}
              on:click={() => filterCategory = cat.value}>
        {cat.label}
      </button>
    {/each}
  </div>

  {#if filteredDays.length > 0}
    <div class="day-list">
      {#each filteredDays as day}
        <div class="day-card" class:today={day.day === currentDay}>
          <div class="day-number">{day.day}</div>
          <div class="day-events">
            {#each (day.events || []) as evt}
              <div class="calendar-event cat-{evt.category || 'other'}">
                <span class="event-name">{evt.name || evt.label || evt}</span>
                {#if evt.detail}
                  <span class="event-detail">{evt.detail}</span>
                {/if}
              </div>
            {/each}
            {#if !day.events || day.events.length === 0}
              <span class="muted no-events">—</span>
            {/if}
          </div>
        </div>
      {/each}
    </div>
  {:else}
    <p class="muted" style="text-align: center; padding: 32px;">No events for this period.</p>
  {/if}
</div>

<style>
  .calendar-header {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 16px;
    padding: 12px 0;
  }
  .calendar-header h3 {
    font-size: 16px;
    font-weight: 700;
    min-width: 140px;
    text-align: center;
  }
  .filter-bar {
    display: flex;
    gap: 6px;
    padding: 0 0 12px;
    flex-wrap: wrap;
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
  .day-list {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .day-card {
    display: flex;
    gap: 12px;
    padding: 8px 10px;
    border-left: 3px solid transparent;
    border-radius: var(--radius-sm);
  }
  .day-card.today {
    border-left-color: var(--c-accent);
    background: rgba(76, 201, 240, 0.06);
  }
  .day-number {
    font-family: var(--font-mono);
    font-weight: 700;
    font-size: 14px;
    min-width: 28px;
    color: var(--c-text-secondary);
  }
  .day-events {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 3px;
  }
  .calendar-event {
    font-size: 12px;
    padding: 3px 6px;
    border-radius: 4px;
  }
  .cat-race { background: rgba(231, 76, 60, 0.1); color: #e74c3c; }
  .cat-deadline { background: rgba(255, 183, 77, 0.1); color: #ffb74d; }
  .cat-transfer { background: rgba(76, 201, 240, 0.1); color: #4cc9f0; }
  .cat-contract { background: rgba(168, 130, 255, 0.1); color: #a882ff; }
  .cat-development { background: rgba(129, 199, 132, 0.1); color: #81c784; }
  .cat-other { background: var(--c-bg-card); }
  .event-name { font-weight: 500; }
  .event-detail { font-size: 11px; color: var(--c-text-muted); margin-left: 4px; }
  .no-events { font-size: 11px; }
</style>
