<script lang="ts">
  import { newGame, fetchState } from '../lib/api'
  import { gameState } from '../lib/stores'
  import { createEventDispatcher } from 'svelte'

  const dispatch = createEventDispatcher()

  // Wizard state
  let step = 1

  // Fields
  let saveMode = 'replayable'
  let seed = String(Math.floor(Math.random() * 999999))
  let tier = 'grassroots'
  let origin = 'grassroots_hustler'
  let playerIdentity = ''
  let managerFirst = ''
  let managerLast = ''
  let managerAge = 32
  let teamName = ''
  let ownership = 'self_owned'

  const tiers = [
    { value: 'grassroots', label: 'Grassroots', desc: 'The very bottom. Tiny budgets, volunteer crews.' },
    { value: 'formula_v', label: 'Formula V', desc: 'Regional racing. Proper teams, modest budgets.' },
    { value: 'formula_x', label: 'Formula X', desc: 'National level. Professional teams, growing budgets.' },
    { value: 'formula_y', label: 'Formula Y', desc: 'International. Large budgets, factory support.' },
    { value: 'formula_z', label: 'Formula Z', desc: 'The pinnacle. Massive budgets, global stage.' },
  ]

  const origins = [
    { value: 'game_show_winner', label: '🎲 Game Show Winner', desc: 'Won a reality TV competition. Cash-rich, reputation-poor.' },
    { value: 'grassroots_hustler', label: '🔧 Grassroots Hustler', desc: 'Built up from nothing. Street-smart, budget-savvy.' },
    { value: 'former_driver', label: '🏎️ Former Driver', desc: 'Retired racer. Deep race knowledge, media connections.' },
    { value: 'corporate_spinout', label: '💼 Corporate Spinout', desc: 'Left a big team. Well-funded, corporate contacts.' },
    { value: 'engineering_savant', label: '🔬 Engineering Savant', desc: 'Technical genius. R&D bonus, people skills lacking.' },
  ]

  function randomizeSeed() {
    seed = String(Math.floor(Math.random() * 999999))
  }

  let starting = false

  async function startGame() {
    if (!confirm('Start this new game?')) return
    if (starting) return
    starting = true

    try {
      await newGame({
        origin,
        identity: playerIdentity.split(',').map(s => s.trim()).filter(Boolean),
        save_mode: saveMode,
        tier,
        seed: parseInt(seed) || 42,
        team_name: teamName || '',
        ownership,
        manager_age: managerAge,
        manager_first_name: managerFirst || 'Manager',
        manager_last_name: managerLast || 'Unknown',
      })

      // Wait a moment for the backend to process, then fetch fresh state
      await new Promise(r => setTimeout(r, 1500))
      const state = await fetchState()
      gameState.set(state)

      dispatch('start')
    } catch (e) {
      console.error('new game error', e)
      alert('Failed to start new game. Check console.')
    }
    starting = false
  }
</script>

<div class="wizard">
  <div class="wizard-header">
    <h1>🏎️ FROM THE BACKMARKER</h1>
    <p class="subtitle">Racing Management Simulation</p>
    <div class="step-indicator">Step {step} of 4</div>
  </div>

  <div class="wizard-body scroll-y">
    {#if step === 1}
      <!-- Save Mode + Seed -->
      <div class="wizard-section">
        <h3>Save Mode</h3>
        <div class="radio-group">
          <label class:selected={saveMode === 'replayable'}>
            <input type="radio" bind:group={saveMode} value="replayable" />
            <strong>Replayable</strong> — Deterministic seed, same world every time
          </label>
          <label class:selected={saveMode === 'permanent'}>
            <input type="radio" bind:group={saveMode} value="permanent" />
            <strong>Permanent</strong> — Extra entropy, unique every playthrough
          </label>
        </div>
      </div>

      <div class="wizard-section">
        <h3>World Seed</h3>
        <div class="seed-row">
          <input type="text" bind:value={seed} placeholder="Enter seed..." />
          <button class="btn btn-ghost btn-sm" on:click={randomizeSeed}>🎲 Random</button>
        </div>
      </div>

    {:else if step === 2}
      <!-- Starting Tier -->
      <div class="wizard-section">
        <h3>Starting Tier</h3>
        <div class="tier-list">
          {#each tiers as t}
            <label class="tier-option" class:selected={tier === t.value}>
              <input type="radio" bind:group={tier} value={t.value} />
              <strong>{t.label}</strong>
              <span class="tier-desc">{t.desc}</span>
            </label>
          {/each}
        </div>
      </div>

    {:else if step === 3}
      <!-- Who Are You -->
      <div class="wizard-section">
        <h3>Origin Story</h3>
        <div class="origin-list">
          {#each origins as o}
            <label class="origin-option" class:selected={origin === o.value}>
              <input type="radio" bind:group={origin} value={o.value} />
              <strong>{o.label}</strong>
              <span class="origin-desc">{o.desc}</span>
            </label>
          {/each}
        </div>
      </div>

      <div class="wizard-section">
        <h3>Manager Identity</h3>
        <div class="form-grid">
          <div class="form-field">
            <label>First Name</label>
            <input type="text" bind:value={managerFirst} placeholder="First name" />
          </div>
          <div class="form-field">
            <label>Last Name</label>
            <input type="text" bind:value={managerLast} placeholder="Last name" />
          </div>
          <div class="form-field full">
            <label>Age: {managerAge}</label>
            <input type="range" min="22" max="70" bind:value={managerAge} />
          </div>
          <div class="form-field full">
            <label>Player Tags (comma-separated)</label>
            <input type="text" bind:value={playerIdentity} placeholder="e.g. aggressive, technical, charismatic" />
          </div>
        </div>
      </div>

    {:else if step === 4}
      <!-- Team & Confirm -->
      <div class="wizard-section">
        <h3>Team Setup</h3>
        <div class="form-grid">
          <div class="form-field full">
            <label>Team Name (leave blank for random)</label>
            <input type="text" bind:value={teamName} placeholder="Enter team name..." />
          </div>
        </div>
        <div class="radio-group">
          <label class:selected={ownership === 'self_owned'}>
            <input type="radio" bind:group={ownership} value="self_owned" />
            <strong>Self-Owned</strong> — You own the team
          </label>
          <label class:selected={ownership === 'hired_manager'}>
            <input type="radio" bind:group={ownership} value="hired_manager" />
            <strong>Hired Manager</strong> — Working for someone else
          </label>
        </div>
      </div>

      <div class="wizard-section summary">
        <h3>Summary</h3>
        <div class="summary-grid">
          <div><span class="lbl">Mode:</span> {saveMode}</div>
          <div><span class="lbl">Seed:</span> {seed}</div>
          <div><span class="lbl">Tier:</span> {tier}</div>
          <div><span class="lbl">Origin:</span> {origin}</div>
          <div><span class="lbl">Manager:</span> {managerFirst || '?'} {managerLast || '?'}, age {managerAge}</div>
          <div><span class="lbl">Team:</span> {teamName || '(random)'}</div>
        </div>
      </div>
    {/if}
  </div>

  <div class="wizard-footer">
    {#if step > 1}
      <button class="btn btn-ghost" on:click={() => step--}>← Back</button>
    {:else}
      <div></div>
    {/if}
    {#if step < 4}
      <button class="btn btn-primary" on:click={() => step++}>Next →</button>
    {:else}
      <button class="btn btn-success btn-lg" disabled={starting} on:click={startGame}>
        {starting ? '⏳ Creating...' : '🏁 START NEW GAME'}
      </button>
    {/if}
  </div>
</div>

<style>
  .wizard {
    display: flex;
    flex-direction: column;
    height: 100%;
    background: var(--c-bg-primary);
  }
  .wizard-header {
    text-align: center;
    padding: 24px 16px 12px;
    border-bottom: 1px solid var(--c-border);
  }
  .wizard-header h1 {
    font-size: 22px;
    font-weight: 800;
    letter-spacing: 1px;
  }
  .subtitle {
    font-size: 13px;
    color: var(--c-text-muted);
    margin-top: 4px;
  }
  .step-indicator {
    margin-top: 8px;
    font-size: 12px;
    color: var(--c-accent);
    font-family: var(--font-mono);
  }
  .wizard-body {
    flex: 1;
    padding: 16px;
    overflow-y: auto;
  }
  .wizard-section {
    margin-bottom: 20px;
  }
  .wizard-section h3 {
    font-size: 14px;
    font-weight: 600;
    margin-bottom: 10px;
    color: var(--c-text-secondary);
  }
  .radio-group {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .radio-group label, .tier-option, .origin-option {
    display: block;
    padding: 10px 12px;
    background: var(--c-bg-card);
    border: 1px solid var(--c-border);
    border-radius: var(--radius);
    cursor: pointer;
    font-size: 13px;
    transition: all 0.15s;
  }
  .radio-group label.selected, .tier-option.selected, .origin-option.selected {
    border-color: var(--c-accent);
    background: rgba(76, 201, 240, 0.08);
  }
  .radio-group input, .tier-option input, .origin-option input {
    display: none;
  }
  .tier-list, .origin-list {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .tier-desc, .origin-desc {
    display: block;
    font-size: 11px;
    color: var(--c-text-muted);
    margin-top: 2px;
  }
  .seed-row {
    display: flex;
    gap: 8px;
  }
  .seed-row input {
    flex: 1;
    padding: 8px 12px;
    border: 1px solid var(--c-border);
    border-radius: var(--radius);
    background: var(--c-bg-input);
    color: var(--c-text-primary);
    font-family: var(--font-mono);
    font-size: 14px;
  }
  .form-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }
  .form-field.full { grid-column: 1 / -1; }
  .form-field label {
    display: block;
    font-size: 11px;
    color: var(--c-text-muted);
    margin-bottom: 4px;
  }
  .form-field input[type="text"], .form-field input[type="number"] {
    width: 100%;
    padding: 8px 10px;
    border: 1px solid var(--c-border);
    border-radius: var(--radius-sm);
    background: var(--c-bg-input);
    color: var(--c-text-primary);
    font-size: 13px;
  }
  .form-field input[type="range"] {
    width: 100%;
    accent-color: var(--c-accent);
  }
  .summary-grid {
    font-size: 13px;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .summary-grid .lbl { color: var(--c-text-muted); }
  .wizard-footer {
    display: flex;
    justify-content: space-between;
    padding: 12px 16px;
    border-top: 1px solid var(--c-border);
    background: var(--c-bg-secondary);
  }
  @media (max-width: 480px) {
    .form-grid { grid-template-columns: 1fr; }
  }
</style>
