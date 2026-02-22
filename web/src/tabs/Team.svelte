<script lang="ts">
  import { gameState, addToast } from '../lib/stores'
  import {
    hireFreeAgent,
    fireStaff,
    applyForJob,
    submitStaffContractOffer,
    finalizeStaffContract,
    safeRefreshState,
  } from '../lib/api'
  import EntityCard from '../components/EntityCard.svelte'
  import Modal from '../components/Modal.svelte'
  import { formatCurrency } from '../lib/utils'

  $: team = $gameState.player_team
  $: roster = team?.roster || {}
  $: budget = team?.budget || {}
  $: freeAgents = $gameState.free_agents || []
  $: jobBoard = $gameState.job_board || []
  $: aiTeams = $gameState.ai_teams || []

  let marketTab: string = 'free_drivers'
  let marketSortBy: 'overall' | 'age' = 'overall'
  let marketSortDir: 'desc' | 'asc' = 'desc'
  let working = false
  let showContractModal = false
  let contractEntity: any = null
  let contractSeasons = 2
  let contractSalaryAnnual = 0
  let contractSigningBonusAnnual = 0
  let contractRound = 0
  let contractOfferAccepted = false
  let contractResponseMessage = ''
  let contractResponseTone: 'success' | 'warning' | 'error' | '' = ''

  function toNumber(value: any, fallback = 0): number {
    const n = Number(value)
    return Number.isFinite(n) ? n : fallback
  }

  function inferAnnualFromContract(rawSalary: any): number {
    const salary = toNumber(rawSalary, 0)
    if (salary <= 0) return 0
    // Existing serialized contract salary can be per-tick or annual depending on save lineage.
    return salary < 10000 ? Math.round(salary * 365) : Math.round(salary)
  }

  function openContractNegotiation(member: any) {
    if (!member?.entity_id) {
      addToast('Unable to negotiate: missing entity id', 'error')
      return
    }
    contractEntity = member
    contractSeasons = Math.max(1, Math.min(5, Math.round(toNumber(member?.contract?.seasons_remaining, 2))))
    const inferredSalary = inferAnnualFromContract(member?.contract?.salary)
    const fallbackSalary = Math.round(Math.max(10000, toNumber(member?.overall, 50) * 2500))
    contractSalaryAnnual = Math.max(10000, inferredSalary || fallbackSalary)
    contractSigningBonusAnnual = 0
    contractRound = 0
    contractOfferAccepted = false
    contractResponseMessage = ''
    contractResponseTone = ''
    showContractModal = true
  }

  function closeContractNegotiation() {
    showContractModal = false
    contractEntity = null
    contractOfferAccepted = false
    contractResponseMessage = ''
    contractResponseTone = ''
  }

  async function handleFire(name: string) {
    if (working) return
    if (!confirm(`Fire ${name}? This cannot be undone.`)) return
    working = true
    try {
      await fireStaff(name)
      await new Promise(r => setTimeout(r, 500))
      await safeRefreshState()
      addToast(`Fired ${name}`, 'success')
    } catch (e) { console.error('fire', e); addToast('Fire failed', 'error') }
    working = false
  }

  async function handleHire(name: string, agentId: number) {
    if (working) return
    working = true
    try {
      await hireFreeAgent(name, agentId)
      await new Promise(r => setTimeout(r, 500))
      await safeRefreshState()
      addToast(`Hired ${name}`, 'success')
    } catch (e) { console.error('hire', e); addToast('Hire failed', 'error') }
    working = false
  }

  async function handleApply(listingId: number) {
    if (working) return
    working = true
    try {
      await applyForJob(listingId)
      await new Promise(r => setTimeout(r, 500))
      await safeRefreshState()
      addToast('Application submitted', 'success')
    } catch (e) { console.error('apply', e); addToast('Application failed', 'error') }
    working = false
  }

  async function handleContractOffer() {
    if (working || !contractEntity?.entity_id) return

    const role = String(
      contractEntity?.contract?.role ||
      contractEntity?.type ||
      contractEntity?.entity_type ||
      ''
    ).toLowerCase()

    working = true
    try {
      const result = await submitStaffContractOffer({
        entity_id: Number(contractEntity.entity_id),
        seasons_duration: Math.max(1, Math.min(5, Math.round(toNumber(contractSeasons, 2)))),
        salary_annual: Math.max(0, Math.round(toNumber(contractSalaryAnnual, 0))),
        signing_bonus_annual: Math.max(0, Math.round(toNumber(contractSigningBonusAnnual, 0))),
        negotiation_round: Math.max(0, Math.round(toNumber(contractRound, 0))),
        role,
      })

      if (result?.error) throw new Error(result.error)

      const offerResult = result?.result || {}
      const counter = result?.counter_offer_annual || offerResult?.counter_offer || null

      contractOfferAccepted = Boolean(offerResult?.accepted)
      contractResponseMessage = offerResult?.message || (contractOfferAccepted ? 'Offer accepted.' : 'Offer rejected.')
      contractResponseTone = contractOfferAccepted ? 'success' : (counter ? 'warning' : 'error')

      if (counter) {
        contractSeasons = Math.max(1, Math.min(5, Math.round(toNumber(counter?.seasons_duration, contractSeasons))))

        const salaryAnnualFromCounter = counter?.base_salary_annual
        if (Number.isFinite(Number(salaryAnnualFromCounter))) {
          contractSalaryAnnual = Math.max(0, Math.round(Number(salaryAnnualFromCounter)))
        } else {
          contractSalaryAnnual = Math.max(0, Math.round(toNumber(counter?.base_salary, contractSalaryAnnual / 365) * 365))
        }

        const bonusAnnualFromCounter = counter?.signing_bonus_annual
        if (Number.isFinite(Number(bonusAnnualFromCounter))) {
          contractSigningBonusAnnual = Math.max(0, Math.round(Number(bonusAnnualFromCounter)))
        } else {
          contractSigningBonusAnnual = Math.max(0, Math.round(toNumber(counter?.signing_bonus, contractSigningBonusAnnual / 365) * 365))
        }

        contractRound = Math.max(0, Math.round(toNumber(counter?.negotiation_round, contractRound + 1)))
      }
    } catch (e: any) {
      console.error('contract offer', e)
      contractOfferAccepted = false
      contractResponseTone = 'error'
      contractResponseMessage = e?.message || 'Offer failed'
      addToast(contractResponseMessage, 'error')
    }
    working = false
  }

  async function handleContractFinalize() {
    if (working || !contractOfferAccepted || !contractEntity?.entity_id) return

    const role = String(
      contractEntity?.contract?.role ||
      contractEntity?.type ||
      contractEntity?.entity_type ||
      ''
    ).toLowerCase()

    working = true
    try {
      const result = await finalizeStaffContract({
        entity_id: Number(contractEntity.entity_id),
        seasons_duration: Math.max(1, Math.min(5, Math.round(toNumber(contractSeasons, 2)))),
        salary_annual: Math.max(0, Math.round(toNumber(contractSalaryAnnual, 0))),
        signing_bonus_annual: Math.max(0, Math.round(toNumber(contractSigningBonusAnnual, 0))),
        role,
      })
      if (result?.error || result?.success === false) {
        throw new Error(result?.error || 'Could not finalize contract')
      }

      addToast(`Contract signed with ${contractEntity.name}`, 'success')
      closeContractNegotiation()
      await new Promise(r => setTimeout(r, 500))
      await safeRefreshState()
    } catch (e: any) {
      console.error('contract finalize', e)
      addToast(e?.message || 'Contract signing failed', 'error')
    }
    working = false
  }

  $: contractTotalAnnual = Math.max(0, Math.round(toNumber(contractSalaryAnnual, 0) * Math.max(1, Math.round(toNumber(contractSeasons, 1))) + toNumber(contractSigningBonusAnnual, 0)))

  // Split free agents by type
  $: faDrivers = freeAgents.filter((e: any) => (e.type || '').includes('Driver'))
  $: faEngineers = freeAgents.filter((e: any) => (e.type || '').includes('Engineer'))
  $: faMechanics = freeAgents.filter((e: any) => (e.type || '').includes('Mechanic'))
  $: faStrategists = freeAgents.filter((e: any) => (e.type || '').includes('Strategist'))
  $: faPrincipals = freeAgents.filter((e: any) => (e.type || '').includes('Principal'))

  function compareNumericMetric(
    aValue: number,
    bValue: number,
    aName: string,
    bName: string
  ): number {
    const dir = marketSortDir === 'asc' ? 1 : -1
    if (aValue !== bValue) return (aValue - bValue) * dir
    return aName.localeCompare(bName)
  }

  function sortAgents(agents: any[]): any[] {
    return [...agents].sort((a: any, b: any) => {
      const aMetric = marketSortBy === 'overall'
        ? toNumber(a?.overall ?? 0, 0)
        : toNumber(a?.age ?? 0, 0)
      const bMetric = marketSortBy === 'overall'
        ? toNumber(b?.overall ?? 0, 0)
        : toNumber(b?.age ?? 0, 0)
      const aName = String(a?.name || '')
      const bName = String(b?.name || '')
      return compareNumericMetric(aMetric, bMetric, aName, bName)
    })
  }

  function sortJobListings(listings: any[]): any[] {
    return [...listings].sort((a: any, b: any) => {
      const aMetric = marketSortBy === 'overall'
        ? toNumber(a?.overall ?? 0, 0)
        : toNumber(a?.age ?? 0, 0)
      const bMetric = marketSortBy === 'overall'
        ? toNumber(b?.overall ?? 0, 0)
        : toNumber(b?.age ?? 0, 0)
      const aName = String(a?.team_name || '')
      const bName = String(b?.team_name || '')
      return compareNumericMetric(aMetric, bMetric, aName, bName)
    })
  }

  $: sortedJobBoard = sortJobListings(jobBoard)
  $: sortedFaDrivers = sortAgents(faDrivers)
  $: sortedFaEngineers = sortAgents(faEngineers)
  $: sortedFaMechanics = sortAgents(faMechanics)
  $: sortedFaStrategists = sortAgents(faStrategists)
  $: sortedFaPrincipals = sortAgents(faPrincipals)
</script>

<div class="team-view">
  <!-- Financial Overview -->
  {#if team}
    <div class="card">
      <div class="section-title">💰 Financial Overview</div>
      <div class="finance-grid">
        <div><span class="label">Cash</span> <span class="val">{formatCurrency(budget.cash || 0)}</span></div>
        <div><span class="label">Weekly Expenses</span> <span class="val">{formatCurrency(budget.weekly_expenses || 0)}</span></div>
        <div><span class="label">Weekly Income</span> <span class="val">{formatCurrency(budget.weekly_income || 0)}</span></div>
      </div>
    </div>
  {/if}

  <!-- Current Roster -->
  <div class="card">
    <div class="section-title">👥 Current Roster</div>
    <div class="roster-grid">
      {#if roster.drivers}
        {#each (Array.isArray(roster.drivers) ? roster.drivers : [roster.drivers]) as driver}
          {#if driver}
            <EntityCard
              entity={driver}
              onNegotiate={() => openContractNegotiation(driver)}
              onFire={() => handleFire(driver.name)}
            />
          {/if}
        {/each}
      {/if}
      {#if roster.engineers}
        {#each (Array.isArray(roster.engineers) ? roster.engineers : [roster.engineers]) as eng}
          {#if eng}
            <EntityCard
              entity={eng}
              onNegotiate={() => openContractNegotiation(eng)}
              onFire={() => handleFire(eng.name)}
            />
          {/if}
        {/each}
      {/if}
      {#if roster.mechanics}
        {#each (Array.isArray(roster.mechanics) ? roster.mechanics : [roster.mechanics]) as mech}
          {#if mech}
            <EntityCard
              entity={mech}
              compact
              onNegotiate={() => openContractNegotiation(mech)}
              onFire={() => handleFire(mech.name)}
            />
          {/if}
        {/each}
      {/if}
      {#if roster.strategist}
        <EntityCard
          entity={roster.strategist}
          compact
          onNegotiate={() => openContractNegotiation(roster.strategist)}
          onFire={() => handleFire(roster.strategist.name)}
        />
      {/if}
      {#if roster.principal}
        <EntityCard
          entity={roster.principal}
          compact
          onNegotiate={() => openContractNegotiation(roster.principal)}
          onFire={() => handleFire(roster.principal.name)}
        />
      {/if}
    </div>
  </div>

  <!-- Job Market -->
  <div class="card">
    <div class="section-title">📋 Job Market</div>
    <div class="tab-bar">
      <button class="tab-btn" class:active={marketTab === 'jobs'} on:click={() => marketTab = 'jobs'}>Openings ({jobBoard.length})</button>
      <button class="tab-btn" class:active={marketTab === 'free_drivers'} on:click={() => marketTab = 'free_drivers'}>Drivers ({faDrivers.length})</button>
      <button class="tab-btn" class:active={marketTab === 'free_engineers'} on:click={() => marketTab = 'free_engineers'}>Engineers ({faEngineers.length})</button>
      <button class="tab-btn" class:active={marketTab === 'free_mechanics'} on:click={() => marketTab = 'free_mechanics'}>Mechanics ({faMechanics.length})</button>
      <button class="tab-btn" class:active={marketTab === 'free_strategists'} on:click={() => marketTab = 'free_strategists'}>Strategists ({faStrategists.length})</button>
    </div>
    <div class="market-controls">
      <label class="market-sort-label">
        Sort
        <select bind:value={marketSortBy}>
          <option value="overall">Overall</option>
          <option value="age">Age</option>
        </select>
      </label>
      <label class="market-sort-label">
        Order
        <select bind:value={marketSortDir}>
          <option value="desc">High → Low</option>
          <option value="asc">Low → High</option>
        </select>
      </label>
    </div>
    <div class="market-list scroll-y">
      {#if marketTab === 'jobs'}
        {#each sortedJobBoard as job}
          <div class="market-item">
            <div class="market-info">
              <div class="market-name">{job.team_name}</div>
              <div class="market-meta">
                {job.role}
                {#if toNumber(job.overall, 0) > 0}
                  · OVR {Math.round(toNumber(job.overall, 0))}
                {/if}
                {#if toNumber(job.age, 0) > 0}
                  · Age {Math.round(toNumber(job.age, 0))}
                {/if}
              </div>
            </div>
            <button class="btn btn-primary btn-sm" disabled={working} on:click={() => handleApply(job.id)}>Apply</button>
          </div>
        {:else}
          <div class="empty-state">No openings</div>
        {/each}
      {:else}
        {@const agents = marketTab === 'free_drivers' ? sortedFaDrivers :
                         marketTab === 'free_engineers' ? sortedFaEngineers :
                         marketTab === 'free_mechanics' ? sortedFaMechanics :
                         marketTab === 'free_strategists' ? sortedFaStrategists : sortedFaPrincipals}
        {#each agents.slice(0, 30) as agent}
          <div class="agent-row">
            <EntityCard entity={agent} compact />
            <button class="btn btn-primary btn-sm hire-btn" disabled={working}
              on:click={() => handleHire(agent.name, agent.id)}>Hire</button>
          </div>
        {:else}
          <div class="empty-state">No free agents</div>
        {/each}
      {/if}
    </div>
  </div>

  <!-- Browse Teams -->
  <div class="card">
    <div class="section-title">🏁 Browse Teams ({aiTeams.length})</div>
    <div class="teams-list scroll-y">
      {#each aiTeams as t}
        <details class="team-item">
          <summary>{t.name} — {formatCurrency(t.budget?.cash || 0)}</summary>
          <div class="team-details">
            {#if t.roster?.drivers}
              {#each (Array.isArray(t.roster.drivers) ? t.roster.drivers : [t.roster.drivers]) as d}
                {#if d}
                  <EntityCard entity={d} compact />
                {/if}
              {/each}
            {/if}
          </div>
        </details>
      {/each}
    </div>
  </div>

  <Modal
    bind:show={showContractModal}
    title={contractEntity ? `📝 Contract Negotiation: ${contractEntity.name}` : '📝 Contract Negotiation'}
    size="md"
    on:close={closeContractNegotiation}
  >
    <div class="contract-modal">
      <div class="contract-meta">
        <div><span class="label">Role</span> <span class="val">{contractEntity?.type || contractEntity?.entity_type || 'Staff'}</span></div>
        <div><span class="label">Current Salary</span> <span class="val">{formatCurrency(inferAnnualFromContract(contractEntity?.contract?.salary || 0))}/yr</span></div>
        <div><span class="label">Current Seasons Left</span> <span class="val">{Math.max(0, Math.round(toNumber(contractEntity?.contract?.seasons_remaining, 0) * 10) / 10)}</span></div>
      </div>

      <div class="contract-form-grid">
        <label>
          <span>Contract Seasons</span>
          <input type="number" min="1" max="5" step="1" bind:value={contractSeasons} />
        </label>
        <label>
          <span>Annual Salary</span>
          <input type="number" min="0" step="1000" bind:value={contractSalaryAnnual} />
        </label>
        <label>
          <span>Signing Bonus</span>
          <input type="number" min="0" step="1000" bind:value={contractSigningBonusAnnual} />
        </label>
        <label>
          <span>Round</span>
          <input type="number" min="0" max="5" step="1" bind:value={contractRound} />
        </label>
      </div>

      <div class="contract-total">
        <span class="label">Total Contract Value</span>
        <span class="val">{formatCurrency(contractTotalAnnual)}</span>
      </div>

      {#if contractResponseMessage}
        <div class="contract-response {contractResponseTone}">
          {contractResponseMessage}
        </div>
      {/if}

      <div class="contract-actions">
        <button class="btn btn-primary" disabled={working || !contractEntity} on:click={handleContractOffer}>Make Offer</button>
        <button class="btn btn-success" disabled={working || !contractOfferAccepted || !contractEntity} on:click={handleContractFinalize}>Sign Contract</button>
        <button class="btn btn-ghost" disabled={working} on:click={closeContractNegotiation}>Close</button>
      </div>
    </div>
  </Modal>
</div>

<style>
  .team-view { display: flex; flex-direction: column; gap: 12px; padding: 12px; }
  .finance-grid { display: flex; flex-direction: column; gap: 4px; }
  .finance-grid div { display: flex; justify-content: space-between; font-size: 12px; padding: 3px 0; }
  .label { color: var(--c-text-muted); }
  .val { color: var(--c-text-primary); font-weight: 500; font-family: var(--font-mono); }
  .roster-grid { display: flex; flex-direction: column; gap: 8px; }
  .market-list { max-height: 400px; }
  .market-controls {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    margin: 8px 0;
  }
  .market-sort-label {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 11px;
    color: var(--c-text-muted);
  }
  .market-sort-label select {
    border: 1px solid var(--c-border);
    background: var(--c-bg-input);
    color: var(--c-text-primary);
    border-radius: var(--radius-sm);
    font-size: 12px;
    padding: 4px 8px;
  }
  .market-item {
    display: flex; align-items: center; justify-content: space-between;
    padding: 8px; border-bottom: 1px solid var(--c-border);
  }
  .market-name { font-size: 13px; font-weight: 500; }
  .market-meta { font-size: 11px; color: var(--c-text-muted); }
  .teams-list { max-height: 400px; }
  .team-item { padding: 6px 0; border-bottom: 1px solid var(--c-border); }
  .team-item summary { font-size: 13px; cursor: pointer; padding: 4px; }
  .team-details { padding: 8px 0; display: flex; flex-direction: column; gap: 6px; }
  .empty-state { text-align: center; color: var(--c-text-muted); padding: 20px; font-size: 13px; }
  .agent-row { display: flex; align-items: center; gap: 8px; }
  .agent-row :global(.entity-card) { flex: 1; }
  .hire-btn { flex-shrink: 0; }

  .contract-modal { display: flex; flex-direction: column; gap: 12px; }
  .contract-meta {
    display: grid;
    grid-template-columns: 1fr;
    gap: 6px;
    padding: 10px;
    border: 1px solid var(--c-border);
    border-radius: var(--radius);
    background: var(--c-bg-tertiary);
  }
  .contract-meta div {
    display: flex;
    justify-content: space-between;
    font-size: 12px;
  }
  .contract-form-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
  }
  .contract-form-grid label {
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 12px;
    color: var(--c-text-secondary);
  }
  .contract-form-grid input {
    width: 100%;
    border: 1px solid var(--c-border);
    border-radius: var(--radius-sm);
    background: var(--c-bg-input);
    color: var(--c-text-primary);
    padding: 8px;
    font-size: 13px;
    font-family: var(--font-mono);
  }
  .contract-form-grid input:focus {
    outline: none;
    border-color: var(--c-accent);
  }
  .contract-total {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-top: 1px solid var(--c-border);
    padding-top: 10px;
  }
  .contract-response {
    font-size: 12px;
    line-height: 1.4;
    padding: 10px;
    border-radius: var(--radius-sm);
    border: 1px solid transparent;
    background: var(--c-bg-tertiary);
    color: var(--c-text-secondary);
  }
  .contract-response.success {
    border-color: color-mix(in srgb, var(--c-success) 55%, transparent);
    color: var(--c-success);
  }
  .contract-response.warning {
    border-color: color-mix(in srgb, var(--c-warning) 55%, transparent);
    color: var(--c-warning);
  }
  .contract-response.error {
    border-color: color-mix(in srgb, var(--c-danger) 55%, transparent);
    color: var(--c-danger);
  }
  .contract-actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
    flex-wrap: wrap;
  }

  @media (max-width: 640px) {
    .contract-form-grid { grid-template-columns: 1fr; }
  }
</style>
