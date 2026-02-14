<script lang="ts">
  import { gameState } from '../lib/stores'
  import { buyPart, sellPart, equipPart, fetchState } from '../lib/api'
  import { formatCurrency } from '../lib/utils'
  import StatBar from '../components/StatBar.svelte'

  $: team = $gameState.player_team
  $: car = team?.car || null
  $: equipped = car?.equipped_parts || []
  $: inventory = car?.parts_inventory || []
  $: marketplace = $gameState.parts_marketplace || []

  let marketFilter = 'All Types'
  $: filteredMarket = marketFilter === 'All Types'
    ? marketplace
    : marketplace.filter((p: any) => p.type === marketFilter)

  $: partTypes = ['All Types', ...new Set(marketplace.map((p: any) => p.type).filter(Boolean))]

  let working = false
  async function handleEquip(id: string) {
    if (working) return; working = true
    try { await equipPart(id); gameState.set(await fetchState()) } catch (e) { console.error('equip', e) }
    working = false
  }
  async function handleSell(id: string) {
    if (working) return; working = true
    try { await sellPart(id); gameState.set(await fetchState()) } catch (e) { console.error('sell', e) }
    working = false
  }
  async function handleBuy(id: string, cost: number) {
    if (working) return; working = true
    try { await buyPart(id, cost); gameState.set(await fetchState()) } catch (e) { console.error('buy', e) }
    working = false
  }
</script>

<div class="car-view">
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
        {#each equipped as part}
          <div class="part-item">
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
        {#each inventory as part}
          <div class="part-item">
            <div>
              <span class="part-name">{part.name || part.type}</span>
              <span class="part-type">{part.type}</span>
            </div>
            <div class="part-actions">
              <span class="part-quality">Q{Math.round(part.quality)}</span>
              <button class="btn btn-primary btn-sm" disabled={working} on:click={() => handleEquip(part.id)}>Equip</button>
              <button class="btn btn-ghost btn-sm" disabled={working} on:click={() => handleSell(part.id)}>Sell</button>
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
      {#each filteredMarket as part}
        <div class="part-item">
          <div>
            <span class="part-name">{part.name}</span>
            <span class="part-type">{part.type} · Q{Math.round(part.quality)}</span>
          </div>
          <div class="part-actions">
            <span class="part-cost">{formatCurrency(part.cost)}</span>
            <button class="btn btn-primary btn-sm" disabled={working} on:click={() => handleBuy(part.id, part.cost)}>Buy</button>
          </div>
        </div>
      {:else}
        <div class="empty-state">No parts available</div>
      {/each}
    </div>
  </div>
</div>

<style>
  .car-view { display: flex; flex-direction: column; gap: 12px; padding: 12px; }
  .car-overall { font-size: 16px; margin-bottom: 8px; }
  .car-stats { display: flex; flex-direction: column; gap: 4px; }
  .parts-list { display: flex; flex-direction: column; gap: 4px; max-height: 300px; }
  .part-item {
    display: flex; justify-content: space-between; align-items: center;
    padding: 8px; background: var(--c-bg-tertiary); border-radius: var(--radius-sm); font-size: 12px;
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
