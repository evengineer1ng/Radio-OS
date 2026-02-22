<script lang="ts">
  import { gameState, addToast } from '../lib/stores'
  import { buyPart, sellPart, equipPart, safeRefreshState } from '../lib/api'
  import { formatCurrency } from '../lib/utils'
  import StatBar from '../components/StatBar.svelte'
  import PartDetail from '../components/PartDetail.svelte'

  $: team = $gameState.player_team
  $: car = team?.car || null
  $: equipped = car?.equipped_parts || []
  $: inventory = car?.parts_inventory || []
  $: marketplace = $gameState.parts_marketplace || []

  let marketFilter = 'All Types'
  let partSortBy: 'overall' | 'age' = 'overall'
  let partSortDir: 'desc' | 'asc' = 'desc'
  $: filteredMarket = marketFilter === 'All Types'
    ? marketplace
    : marketplace.filter((p: any) => p.type === marketFilter)

  $: partTypes = ['All Types', ...new Set(marketplace.map((p: any) => p.type).filter(Boolean))]

  function toNumber(value: any, fallback = 0): number {
    const n = Number(value)
    return Number.isFinite(n) ? n : fallback
  }

  function currentInventoryRows(state: any): any[] {
    const rows = state?.player_team?.car?.parts_inventory
    return Array.isArray(rows) ? rows : []
  }

  function countInventoryPartById(state: any, partId: string): number {
    return currentInventoryRows(state).filter((part: any) => String(part?.id || '') === partId).length
  }

  function findPurchaseRejectionReason(state: any, partId: string, minTick: number): string {
    const events = Array.isArray(state?.recent_events) ? state.recent_events : []
    for (let i = events.length - 1; i >= 0; i -= 1) {
      const evt = events[i] || {}
      const category = String(evt?.category || evt?.type || '').toLowerCase()
      if (category !== 'purchase_rejected') continue
      if (toNumber(evt?.tick, 0) < minTick) continue
      const evtPartId = String(evt?.data?.part_id || '')
      if (evtPartId && evtPartId !== partId) continue
      return String(evt?.data?.reason || evt?.description || 'Purchase rejected')
    }
    return ''
  }

  function getPartMetric(part: any): number {
    if (partSortBy === 'age') return toNumber(part?.age, 0)
    return toNumber(part?.quality ?? 0, 0)
  }

  function compareParts(a: any, b: any): number {
    const dir = partSortDir === 'asc' ? 1 : -1
    const delta = (getPartMetric(a) - getPartMetric(b)) * dir
    if (delta !== 0) return delta
    return String(a?.name || '').localeCompare(String(b?.name || ''))
  }

  $: sortedEquipped = [...equipped].sort(compareParts)
  $: sortedInventory = [...inventory].sort(compareParts)
  $: sortedMarketplace = [...filteredMarket].sort(compareParts)

  let working = false

  // Detail modal state
  let selectedPart: any = null
  let showPartDetail = false
  let partDetailMode: 'equipped' | 'inventory' | 'marketplace' = 'marketplace'

  function openPartDetail(part: any, mode: 'equipped' | 'inventory' | 'marketplace') {
    selectedPart = part
    partDetailMode = mode
    showPartDetail = true
  }

  async function refreshAfterCommand(retries = 2, delayMs = 350) {
    for (let i = 0; i < retries; i += 1) {
      await new Promise(r => setTimeout(r, delayMs))
      await safeRefreshState()
    }
  }

  async function waitForBuyResolution(partId: string, previousCount: number, minTick: number): Promise<{ status: 'purchased' | 'rejected' | 'pending'; reason?: string }> {
    const attempts = 14
    for (let i = 0; i < attempts; i += 1) {
      await new Promise(r => setTimeout(r, 250))
      await safeRefreshState()
      if (countInventoryPartById($gameState, partId) > previousCount) {
        return { status: 'purchased' }
      }
      const reason = findPurchaseRejectionReason($gameState, partId, minTick)
      if (reason) {
        return { status: 'rejected', reason }
      }
    }
    return { status: 'pending' }
  }

  async function handleEquip(id: string) {
    if (working) return; working = true
    try { await equipPart(id); await refreshAfterCommand(); addToast('Part equipped', 'success') } catch (e) { console.error('equip', e); addToast('Equip failed', 'error') }
    working = false
  }
  async function handleSell(id: string) {
    if (working) return; working = true
    try { await sellPart(id); await refreshAfterCommand(); addToast('Part sold', 'success') } catch (e) { console.error('sell', e); addToast('Sell failed', 'error') }
    working = false
  }
  async function handleBuy(id: string, cost: number) {
    if (working) return; working = true
    try {
      const previousCount = countInventoryPartById($gameState, id)
      const minTick = toNumber($gameState?.tick, 0)
      await buyPart(id, cost)
      const resolution = await waitForBuyResolution(id, previousCount, minTick)
      if (resolution.status === 'rejected') {
        throw new Error(resolution.reason || 'Purchase rejected')
      }
      if (resolution.status === 'purchased') {
        addToast('Part purchased', 'success')
      } else {
        await refreshAfterCommand(2, 400)
        addToast('Purchase queued; refreshing inventory', 'info')
      }
    } catch (e: any) {
      console.error('buy', e)
      addToast(e?.message || 'Buy failed', 'error')
    }
    working = false
  }
</script>

<div class="car-view">
  <div class="parts-sort-controls">
    <label class="parts-sort-label">
      Sort
      <select bind:value={partSortBy}>
        <option value="overall">Overall</option>
        <option value="age">Age</option>
      </select>
    </label>
    <label class="parts-sort-label">
      Order
      <select bind:value={partSortDir}>
        <option value="desc">High → Low</option>
        <option value="asc">Low → High</option>
      </select>
    </label>
  </div>

  {#if car}
    <div class="card">
      <div class="section-title">🏎️ {car.name || 'Car'}</div>
      <div class="car-overall">Overall: <strong>{Math.round(car.overall || 0)}</strong></div>
      {#if car.stats}
        <div class="car-stats">
          {#each Object.entries(car.stats) as [key, val]}
            <StatBar label={key.replace(/_/g, ' ')} value={Number(val)} />
          {/each}
        </div>
      {/if}
    </div>

    <!-- Equipped Parts -->
    <div class="card">
      <div class="section-title">⚙️ Equipped Parts ({equipped.length})</div>
      <div class="parts-list">
        {#each sortedEquipped as part}
          <!-- svelte-ignore a11y-click-events-have-key-events -->
          <div class="part-item clickable" on:click={() => openPartDetail(part, 'equipped')} role="button" tabindex="0">
            <span class="part-name">{part.name || part.type}</span>
            <span class="part-quality">Q{Math.round(part.quality)}</span>
          </div>
        {:else}
          <div class="empty-state">No parts equipped</div>
        {/each}
      </div>
    </div>

    <!-- Inventory -->
    <div class="card">
      <div class="section-title">📦 Parts Inventory ({inventory.length})</div>
      <div class="parts-list scroll-y">
        {#each sortedInventory as part}
          <!-- svelte-ignore a11y-click-events-have-key-events -->
          <div class="part-item clickable" on:click={() => openPartDetail(part, 'inventory')} role="button" tabindex="0">
            <div>
              <span class="part-name">{part.name || part.type}</span>
              <span class="part-type">
                {part.type}
                {#if toNumber(part.age, 0) > 0}
                  · Age {Math.round(toNumber(part.age, 0))}
                {/if}
              </span>
            </div>
            <div class="part-actions">
              <span class="part-quality">Q{Math.round(part.quality)}</span>
              <button class="btn btn-primary btn-sm" disabled={working} on:click|stopPropagation={() => handleEquip(part.id)}>Equip</button>
              <button class="btn btn-ghost btn-sm" disabled={working} on:click|stopPropagation={() => handleSell(part.id)}>Sell</button>
            </div>
          </div>
        {:else}
          <div class="empty-state">Inventory empty</div>
        {/each}
      </div>
    </div>
  {:else}
    <div class="empty-state">No car data</div>
  {/if}

  <!-- Marketplace -->
  <div class="card">
    <div class="section-title">🛒 Parts Marketplace</div>
    <select class="filter-select" bind:value={marketFilter}>
      {#each partTypes as t}
        <option>{t}</option>
      {/each}
    </select>
    <div class="parts-list scroll-y marketplace">
      {#each sortedMarketplace as part}
        <!-- svelte-ignore a11y-click-events-have-key-events -->
        <div class="part-item clickable" on:click={() => openPartDetail(part, 'marketplace')} role="button" tabindex="0">
          <div>
            <span class="part-name">{part.name}</span>
            <span class="part-type">
              {part.type} · Q{Math.round(part.quality)}
              {#if toNumber(part.age, 0) > 0}
                · Age {Math.round(toNumber(part.age, 0))}
              {/if}
            </span>
          </div>
          <div class="part-actions">
            <span class="part-cost">{formatCurrency(part.cost)}</span>
            <button class="btn btn-primary btn-sm" disabled={working} on:click|stopPropagation={() => handleBuy(part.id, part.cost)}>Buy</button>
          </div>
        </div>
      {:else}
        <div class="empty-state">No parts available</div>
      {/each}
    </div>
  </div>
</div>

<PartDetail
  part={selectedPart}
  bind:show={showPartDetail}
  mode={partDetailMode}
  onEquip={handleEquip}
  onSell={handleSell}
  onBuy={handleBuy}
/>

<style>
  .car-view { display: flex; flex-direction: column; gap: 12px; padding: 12px; }
  .car-overall { font-size: 16px; margin-bottom: 8px; }
  .car-stats { display: flex; flex-direction: column; gap: 4px; }
  .parts-sort-controls {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }
  .parts-sort-label {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 11px;
    color: var(--c-text-muted);
  }
  .parts-sort-label select {
    border: 1px solid var(--c-border);
    background: var(--c-bg-input);
    color: var(--c-text-primary);
    border-radius: var(--radius-sm);
    font-size: 12px;
    padding: 4px 8px;
  }
  .parts-list { display: flex; flex-direction: column; gap: 4px; max-height: 300px; }
  .part-item {
    display: flex; justify-content: space-between; align-items: center;
    padding: 8px; background: var(--c-bg-tertiary); border-radius: var(--radius-sm); font-size: 12px;
  }
  .part-item.clickable {
    cursor: pointer;
    transition: border-color 0.15s, background 0.15s;
    border: 1px solid transparent;
  }
  .part-item.clickable:hover, .part-item.clickable:active {
    border-color: var(--c-accent);
    background: var(--c-bg-hover, var(--c-bg-tertiary));
  }
  .part-name { font-weight: 500; display: block; }
  .part-type { font-size: 11px; color: var(--c-text-muted); }
  .part-quality { color: var(--c-accent); font-family: var(--font-mono); font-weight: 600; }
  .part-actions { display: flex; align-items: center; gap: 6px; }
  .part-cost { color: var(--c-warning); font-family: var(--font-mono); font-size: 12px; }
  .filter-select {
    padding: 6px 10px; border: 1px solid var(--c-border); border-radius: var(--radius-sm);
    background: var(--c-bg-input); color: var(--c-text-primary); font-size: 12px; margin-bottom: 8px;
  }
  .marketplace { max-height: 350px; }
  .empty-state { text-align: center; color: var(--c-text-muted); padding: 20px; font-size: 13px; }
</style>
