<script lang="ts">
  import { gameState } from '../lib/stores'
  
  // Data categories
  type DataCategory = 'seasons' | 'races' | 'finances' | 'careers' | 'outcomes' | 'championships' | 'tables'
  
  let currentCategory: DataCategory = 'seasons'
  let loading = false
  let data: any[] = []
  let tableCounts: Record<string, number> = {}
  let error: string = ''
  
  // Filters
  let teamFilter = ''
  let seasonFilter: number | null = null
  let roleFilter = ''
  let entityFilter = ''
  let limit = 50
  
  $: dbPath = $gameState.state_db_path || ''
  $: playerTeamName = $gameState.player_team?.name || ''
  
  // Auto-set team filter to player team
  $: if (playerTeamName && !teamFilter) {
    teamFilter = playerTeamName
  }
  
  async function loadData() {
    if (!dbPath) {
      error = 'No database path available'
      return
    }
    
    loading = true
    error = ''
    data = []
    
    try {
      const payload: any = { db_path: dbPath, limit }
      
      // Add filters based on category
      if (teamFilter && (currentCategory === 'seasons' || currentCategory === 'races' || currentCategory === 'finances' || currentCategory === 'outcomes')) {
        payload.team_name = teamFilter
      }
      
      if (seasonFilter !== null && (currentCategory === 'races' || currentCategory === 'finances' || currentCategory === 'outcomes')) {
        payload.season = seasonFilter
      }
      
      if (roleFilter && currentCategory === 'careers') {
        payload.role = roleFilter
      }
      
      if (entityFilter && currentCategory === 'careers') {
        payload.entity_name = entityFilter
      }
      
      // Map category to query function
      const queryMap: Record<DataCategory, string> = {
        seasons: 'query_season_summaries',
        races: 'query_race_history',
        finances: 'query_financial_history',
        careers: 'query_career_stats',
        outcomes: 'query_team_outcomes',
        championships: 'query_championship_history',
        tables: 'query_all_tables'
      }
      
      const queryFunc = queryMap[currentCategory]
      
      const response = await fetch(`/api/ftb_data/${queryFunc}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
      
      if (!response.ok) {
        throw new Error(`Query failed: ${response.statusText}`)
      }
      
      const result = await response.json()
      
      if (currentCategory === 'tables') {
        tableCounts = result
      } else {
        data = result || []
      }
    } catch (err: any) {
      error = err.message || 'Failed to load data'
      console.error('[FTB Data]', err)
    } finally {
      loading = false
    }
  }
  
  function changeCategory(cat: DataCategory) {
    currentCategory = cat
    data = []
    tableCounts = {}
    error = ''
  }
  
  function clearFilters() {
    teamFilter = playerTeamName
    seasonFilter = null
    roleFilter = ''
    entityFilter = ''
  }
  
  function exportToCSV() {
    if (data.length === 0) return
    
    // Convert data to CSV
    const headers = Object.keys(data[0])
    const csvRows = [
      headers.join(','),
      ...data.map(row => 
        headers.map(h => {
          const val = row[h]
          // Escape commas and quotes
          if (typeof val === 'string' && (val.includes(',') || val.includes('"'))) {
            return `"${val.replace(/"/g, '""')}"`
          }
          return val ?? ''
        }).join(',')
      )
    ]
    
    const csvContent = csvRows.join('\n')
    const blob = new Blob([csvContent], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `ftb_${currentCategory}_${Date.now()}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }
</script>

<div class="data-explorer">
  <!-- Category Tabs -->
  <div class="card tabs-card">
    <div class="tab-bar">
      <button class="tab-btn" class:active={currentCategory === 'seasons'} on:click={() => changeCategory('seasons')}>
        📊 Seasons
      </button>
      <button class="tab-btn" class:active={currentCategory === 'races'} on:click={() => changeCategory('races')}>
        🏁 Races
      </button>
      <button class="tab-btn" class:active={currentCategory === 'finances'} on:click={() => changeCategory('finances')}>
        💰 Finances
      </button>
      <button class="tab-btn" class:active={currentCategory === 'careers'} on:click={() => changeCategory('careers')}>
        👤 Careers
      </button>
      <button class="tab-btn" class:active={currentCategory === 'outcomes'} on:click={() => changeCategory('outcomes')}>
        📈 Outcomes
      </button>
      <button class="tab-btn" class:active={currentCategory === 'championships'} on:click={() => changeCategory('championships')}>
        🏆 Championships
      </button>
      <button class="tab-btn" class:active={currentCategory === 'tables'} on:click={() => changeCategory('tables')}>
        🗄️ Database
      </button>
    </div>
  </div>
  
  <!-- Filters -->
  {#if currentCategory !== 'tables'}
    <div class="card filters-card">
      <div class="filters-row">
        {#if currentCategory === 'seasons' || currentCategory === 'races' || currentCategory === 'finances' || currentCategory === 'outcomes'}
          <label>
            <span>Team:</span>
            <input type="text" bind:value={teamFilter} placeholder="Team name" />
          </label>
        {/if}
        
        {#if currentCategory === 'races' || currentCategory === 'finances' || currentCategory === 'outcomes'}
          <label>
            <span>Season:</span>
            <input type="number" bind:value={seasonFilter} placeholder="All seasons" />
          </label>
        {/if}
        
        {#if currentCategory === 'careers'}
          <label>
            <span>Entity:</span>
            <input type="text" bind:value={entityFilter} placeholder="Driver/Engineer name" />
          </label>
          <label>
            <span>Role:</span>
            <select bind:value={roleFilter}>
              <option value="">All Roles</option>
              <option value="Driver">Driver</option>
              <option value="Engineer">Engineer</option>
              <option value="Mechanic">Mechanic</option>
              <option value="Strategist">Strategist</option>
            </select>
          </label>
        {/if}
        
        <label>
          <span>Limit:</span>
          <input type="number" bind:value={limit} min="10" max="1000" step="10" />
        </label>
        
        <button class="btn-primary" on:click={loadData} disabled={loading || !dbPath}>
          {loading ? 'Loading...' : 'Query'}
        </button>
        <button class="btn-secondary" on:click={clearFilters}>
          Clear
        </button>
        {#if data.length > 0}
          <button class="btn-secondary" on:click={exportToCSV}>
            📥 Export CSV
          </button>
        {/if}
      </div>
    </div>
  {:else}
    <div class="card filters-card">
      <button class="btn-primary" on:click={loadData} disabled={loading || !dbPath}>
        {loading ? 'Loading...' : 'Load Table Counts'}
      </button>
    </div>
  {/if}
  
  <!-- Error Display -->
  {#if error}
    <div class="card error-card">
      <div class="error-message">❌ {error}</div>
    </div>
  {/if}
  
  <!-- Data Display -->
  {#if currentCategory === 'tables'}
    {#if Object.keys(tableCounts).length > 0}
      <div class="card data-card">
        <div class="section-title">Database Table Counts</div>
        <div class="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Table Name</th>
                <th>Record Count</th>
              </tr>
            </thead>
            <tbody>
              {#each Object.entries(tableCounts) as [table, count]}
                <tr>
                  <td class="mono">{table}</td>
                  <td class="number">{count.toLocaleString()}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </div>
    {/if}
  {:else if data.length > 0}
    <div class="card data-card">
      <div class="section-title">
        {currentCategory.charAt(0).toUpperCase() + currentCategory.slice(1)} Data ({data.length} records)
      </div>
      <div class="table-scroll">
        <table>
          <thead>
            <tr>
              {#each Object.keys(data[0]) as key}
                <th>{key}</th>
              {/each}
            </tr>
          </thead>
          <tbody>
            {#each data as row}
              <tr>
                {#each Object.values(row) as val}
                  <td>
                    {#if typeof val === 'number'}
                      <span class="number">{val.toLocaleString()}</span>
                    {:else if typeof val === 'string' && val.startsWith('{')}
                      <span class="json">{val.slice(0, 50)}{val.length > 50 ? '...' : ''}</span>
                    {:else}
                      {val ?? '-'}
                    {/if}
                  </td>
                {/each}
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </div>
  {:else if !loading && !error}
    <div class="card empty-card">
      <div class="empty-state">
        <div class="empty-icon">📊</div>
        <div class="empty-text">Click "Query" to load {currentCategory} data</div>
      </div>
    </div>
  {/if}
</div>

<style>
  .data-explorer {
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding: 12px;
    height: 100%;
    overflow: hidden;
  }
  
  .tabs-card {
    flex-shrink: 0;
  }
  
  .tab-bar {
    display: flex;
    gap: 4px;
    flex-wrap: wrap;
  }
  
  .tab-btn {
    padding: 8px 16px;
    background: var(--c-bg-secondary);
    border: 1px solid var(--c-border);
    border-radius: var(--radius-sm);
    color: var(--c-text-secondary);
    cursor: pointer;
    font-size: 13px;
    transition: all 0.2s;
  }
  
  .tab-btn:hover {
    background: var(--c-bg-tertiary);
    color: var(--c-text-primary);
  }
  
  .tab-btn.active {
    background: var(--c-accent);
    color: white;
    border-color: var(--c-accent);
    font-weight: 600;
  }
  
  .filters-card {
    flex-shrink: 0;
  }
  
  .filters-row {
    display: flex;
    gap: 12px;
    align-items: flex-end;
    flex-wrap: wrap;
  }
  
  .filters-row label {
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 12px;
  }
  
  .filters-row label span {
    color: var(--c-text-muted);
    font-weight: 500;
  }
  
  .filters-row input, .filters-row select {
    padding: 6px 10px;
    border: 1px solid var(--c-border);
    border-radius: var(--radius-sm);
    background: var(--c-bg-input);
    color: var(--c-text-primary);
    font-size: 13px;
    min-width: 150px;
  }
  
  .btn-primary, .btn-secondary {
    padding: 8px 16px;
    border: none;
    border-radius: var(--radius-sm);
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
  }
  
  .btn-primary {
    background: var(--c-accent);
    color: white;
  }
  
  .btn-primary:hover:not(:disabled) {
    background: var(--c-accent-hover);
  }
  
  .btn-primary:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  
  .btn-secondary {
    background: var(--c-bg-secondary);
    color: var(--c-text-primary);
    border: 1px solid var(--c-border);
  }
  
  .btn-secondary:hover {
    background: var(--c-bg-tertiary);
  }
  
  .error-card {
    flex-shrink: 0;
  }
  
  .error-message {
    color: var(--c-danger);
    font-weight: 500;
  }
  
  .data-card {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
  }
  
  .section-title {
    font-size: 14px;
    font-weight: 600;
    color: var(--c-text-primary);
    padding-bottom: 8px;
    border-bottom: 2px solid var(--c-border);
    margin-bottom: 12px;
  }
  
  .table-scroll {
    flex: 1;
    overflow: auto;
    min-height: 200px;
  }
  
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
  }
  
  th {
    position: sticky;
    top: 0;
    background: var(--c-bg-secondary);
    color: var(--c-text-muted);
    font-weight: 600;
    text-align: left;
    padding: 8px;
    border-bottom: 2px solid var(--c-border);
    text-transform: uppercase;
    font-size: 11px;
    white-space: nowrap;
  }
  
  td {
    padding: 6px 8px;
    border-bottom: 1px solid var(--c-border);
    max-width: 300px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  
  tbody tr:hover {
    background: var(--c-bg-secondary);
  }
  
  .number {
    font-family: 'SF Mono', 'Monaco', 'Courier New', monospace;
    color: var(--c-accent);
  }
  
  .mono {
    font-family: 'SF Mono', 'Monaco', 'Courier New', monospace;
    font-size: 11px;
  }
  
  .json {
    font-family: 'SF Mono', 'Monaco', 'Courier New', monospace;
    font-size: 10px;
    color: var(--c-text-muted);
  }
  
  .empty-card {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  
  .empty-state {
    text-align: center;
    color: var(--c-text-muted);
  }
  
  .empty-icon {
    font-size: 48px;
    margin-bottom: 12px;
    opacity: 0.5;
  }
  
  .empty-text {
    font-size: 14px;
  }
</style>
