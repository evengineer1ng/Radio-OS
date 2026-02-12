<script lang="ts">
  import { gameState } from '../lib/stores'

  $: career = $gameState.manager_career || {}
  $: firstName = $gameState.manager_first_name || ''
  $: lastName = $gameState.manager_last_name || ''
  $: age = $gameState.player_age || 0
</script>

<div class="career-view">
  <div class="card profile-card">
    <div class="profile-icon">👔</div>
    <div class="profile-name">{firstName} {lastName}</div>
    <div class="profile-meta">Age {age}</div>
  </div>

  <div class="card">
    <div class="section-title">📊 Career Statistics</div>
    <div class="stats-grid">
      {#each [
        ['Wins', career.wins || 0],
        ['Podiums', career.podiums || 0],
        ['Championships', career.championships || 0],
        ['Total Races', career.total_races || 0],
        ['Best Finish', career.best_finish || '—'],
        ['Seasons', career.seasons_completed || 0],
      ] as [label, val]}
        <div class="stat-item">
          <div class="stat-val">{val}</div>
          <div class="stat-lbl">{label}</div>
        </div>
      {/each}
    </div>
  </div>

  {#if career.employment_history?.length}
    <div class="card">
      <div class="section-title">📋 Employment History</div>
      {#each career.employment_history as job}
        <div class="history-item">{typeof job === 'string' ? job : JSON.stringify(job)}</div>
      {/each}
    </div>
  {/if}
</div>

<style>
  .career-view { display: flex; flex-direction: column; gap: 12px; padding: 12px; }
  .profile-card { text-align: center; padding: 20px; }
  .profile-icon { font-size: 40px; margin-bottom: 8px; }
  .profile-name { font-size: 18px; font-weight: 700; }
  .profile-meta { font-size: 13px; color: var(--c-text-muted); margin-top: 4px; }
  .stats-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
  .stat-item { text-align: center; padding: 10px; background: var(--c-bg-tertiary); border-radius: var(--radius); }
  .stat-val { font-size: 20px; font-weight: 700; color: var(--c-accent); font-family: var(--font-mono); }
  .stat-lbl { font-size: 11px; color: var(--c-text-muted); margin-top: 2px; }
  .history-item { font-size: 12px; padding: 6px 0; border-bottom: 1px solid var(--c-border); color: var(--c-text-secondary); }
</style>
