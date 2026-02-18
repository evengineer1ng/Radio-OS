# FTB Data Explorer Implementation

## Overview
The FTB Data Explorer is a dedicated tab in the web UI that provides access to historical game data without loading it into the main game state. This prevents performance degradation while allowing deep exploration of past seasons, races, finances, and career statistics.

## Architecture

### Backend Plugin: `ftb_data_explorer.py`
**Location**: `/plugins/ftb_data_explorer.py`

**Purpose**: Provides query functions for on-demand data retrieval from the SQLite database.

**Query Functions**:
1. **`query_season_summaries(db_path, team_name=None, limit=50)`**
   - Retrieves season records with team standings
   - Optional filter by team name
   - Returns: List of season summary dicts

2. **`query_race_history(db_path, team_name=None, season=None, limit=50)`**
   - Fetches race results with details
   - Filter by team and/or season
   - Returns: List of race result dicts

3. **`query_financial_history(db_path, team_name=None, season=None, limit=50)`**
   - Gets financial transaction logs
   - Filter by team and/or season
   - Returns: List of transaction dicts

4. **`query_career_stats(db_path, entity_name=None, role=None, limit=50)`**
   - Retrieves career statistics for drivers/engineers
   - Filter by entity name and/or role
   - Returns: List of career stat dicts

5. **`query_team_outcomes(db_path, team_name=None, season=None, limit=50)`**
   - Gets ML training data (team decision outcomes)
   - Filter by team and/or season
   - Returns: List of outcome dicts

6. **`query_championship_history(db_path, limit=50)`**
   - Fetches championship standings history
   - Returns: List of championship dicts

7. **`query_all_tables(db_path)`**
   - Returns record counts for all database tables
   - Returns: Dict mapping table names to counts

### API Endpoints: `ftb_web_server.py`
**Added Routes**:
- `POST /api/ftb_data/query_season_summaries`
- `POST /api/ftb_data/query_race_history`
- `POST /api/ftb_data/query_financial_history`
- `POST /api/ftb_data/query_career_stats`
- `POST /api/ftb_data/query_team_outcomes`
- `POST /api/ftb_data/query_championship_history`
- `POST /api/ftb_data/query_all_tables`

**Request Format**:
```json
{
  "db_path": "/path/to/ftb_state.db",
  "team_name": "optional filter",
  "season": 5,
  "role": "Driver",
  "entity_name": "John Smith",
  "limit": 50
}
```

**Response Format**:
```json
[
  {
    "column1": "value1",
    "column2": 123,
    ...
  },
  ...
]
```

### Frontend Component: `FTBData.svelte`
**Location**: `/web/src/tabs/FTBData.svelte`

**Features**:
- **Category Tabs**: Switch between data types (Seasons, Races, Finances, Careers, Outcomes, Championships, Database)
- **Smart Filters**: Context-aware filters based on selected category
- **Auto-population**: Team filter defaults to player's team
- **Lazy Loading**: Data only fetched when "Query" button is clicked
- **CSV Export**: Export query results to CSV file
- **Responsive Table**: Scrollable table with sticky headers
- **Empty States**: Clear prompts when no data loaded

**UI Components**:
1. **Category Tabs** (7 tabs):
   - 📊 Seasons
   - 🏁 Races
   - 💰 Finances
   - 👤 Careers
   - 📈 Outcomes
   - 🏆 Championships
   - 🗄️ Database

2. **Filters** (context-sensitive):
   - Team name input (for seasons, races, finances, outcomes)
   - Season number input (for races, finances, outcomes)
   - Entity name input (for careers)
   - Role dropdown (for careers: Driver, Engineer, Mechanic, Strategist)
   - Limit input (10-1000 records)

3. **Action Buttons**:
   - **Query**: Fetch data from backend
   - **Clear**: Reset all filters
   - **Export CSV**: Download results as CSV

4. **Data Display**:
   - Responsive table with column headers
   - Number formatting (thousands separators)
   - JSON truncation (shows first 50 chars)
   - Hover highlighting
   - Empty state prompts

## Usage

### From Web UI
1. Navigate to the **🗄️ Data** tab in the bottom navigation
2. Select a data category (Seasons, Races, etc.)
3. Apply optional filters
4. Click **Query** to fetch data
5. Review results in table
6. Click **Export CSV** to save data

### Example Queries

**All seasons for player's team**:
- Tab: Seasons
- Team: Auto-filled with player team
- Click Query

**Recent races in Season 3**:
- Tab: Races
- Season: 3
- Team: (optional)
- Click Query

**Driver career stats**:
- Tab: Careers
- Role: Driver
- Entity: (optional for specific driver)
- Click Query

**Database overview**:
- Tab: Database
- Click "Load Table Counts"

## Performance Considerations

### Why This Design?
The main game state is loaded into memory and kept in reactive Svelte stores. Loading all historical data would:
- Increase memory usage significantly
- Slow down reactive updates
- Impact UI responsiveness
- Make serialization/deserialization expensive

### Solution Benefits
✅ **On-demand loading**: Data only fetched when needed  
✅ **Separate from game state**: No impact on main UI performance  
✅ **Filtered queries**: Limit result set size  
✅ **Lazy tab loading**: Only loads when Data tab is opened  
✅ **No caching**: Fresh data on every query (avoids stale state)

## Database Tables Queried

### `season_summary`
- Records: Season end results for all teams/leagues
- Columns: season_number, tick, league_id, team_name, final_position, points, prize_money

### `race_results`
- Records: Individual race results
- Columns: season, race_number, tick, track_name, team_name, driver_name, grid_position, finish_position, points_earned

### `financial_transactions`
- Records: All team financial activities
- Columns: tick, season, team_name, transaction_type, amount, balance_after, description

### `career_stats`
- Records: Cumulative career statistics for entities
- Columns: entity_name, role, races_participated, wins, podiums, points_total, championships

### `team_outcomes`
- Records: ML training data for team decisions
- Columns: tick, season, team_name, decision_type, outcome_data, result_score

### `championship_standings`
- Records: Periodic championship table snapshots
- Columns: tick, season, league_id, team_name, position, points, races_completed

## Integration with Existing Systems

### No Changes Required To:
- Main game loop (`ftb_game.py`)
- State persistence (`ftb_state_db.py`)
- WebSocket streaming
- Other UI tabs
- Game state stores

### New Dependencies:
- `ftb_data_explorer.py` plugin (backend queries)
- 7 new API endpoints in `ftb_web_server.py`
- `FTBData.svelte` component
- Tab registration in `App.svelte`

## Future Enhancements

### Potential Additions:
- **Advanced Filters**: Date ranges, league tier filters, multi-team comparison
- **Visualizations**: Charts and graphs for trends (line charts, bar charts)
- **Saved Queries**: Bookmark frequently used queries
- **Export Formats**: PDF reports, JSON, Excel
- **Search**: Full-text search across all data
- **Comparisons**: Side-by-side team/driver comparisons
- **Statistics**: Aggregations (averages, totals, trends)

### UI Improvements:
- Column sorting (click headers to sort)
- Column filtering (per-column search)
- Pagination (for very large result sets)
- Copy to clipboard functionality
- Expandable rows for detailed views

## Testing

### Verify Installation:
1. Backend plugin exists: `plugins/ftb_data_explorer.py`
2. API endpoints registered: Check `/api/ftb_data/*` routes
3. Svelte component exists: `web/src/tabs/FTBData.svelte`
4. Tab appears in navigation: Look for 🗄️ Data tab

### Test Queries:
1. Open Data tab
2. Try each category
3. Apply filters
4. Verify results display correctly
5. Test CSV export
6. Check Database tab for table counts

### Error Handling:
- Missing database path: Shows error message
- Query failure: Displays error details
- Empty results: Shows "Click Query to load data" prompt
- Network errors: Caught and displayed to user

## Troubleshooting

### "No database path available"
- Ensure game is loaded (not on landing screen)
- Check that `state_db_path` exists in gameState store
- Verify database file exists at path

### "Query failed: 500"
- Check browser console for error details
- Verify `ftb_data_explorer.py` is in plugins folder
- Ensure database file is not corrupted
- Check server logs for Python exceptions

### Empty results
- Verify filters match existing data
- Try removing filters and querying again
- Check Database tab to see if tables have records
- Ensure season/team names match exactly

### Tab not appearing
- Verify `FTBData.svelte` exists in `web/src/tabs/`
- Check that import statement is in `App.svelte`
- Ensure tab object is in tabs array with `id: 'data'`
- Rebuild Svelte app: `cd web && npm run build`

## Implementation Status

✅ Backend plugin created (`ftb_data_explorer.py`)  
✅ API endpoints added to `ftb_web_server.py`  
✅ Svelte component created (`FTBData.svelte`)  
✅ Tab registered in `App.svelte`  
✅ No syntax errors detected  
✅ Ready for testing  

**Next Steps**:
1. Rebuild Svelte frontend: `cd web && npm run build`
2. Start game with web server enabled
3. Open browser to web UI
4. Test Data tab functionality
5. Verify CSV export works
6. Document any issues found

---

**Created**: During implementation of historical data exploration feature  
**Related Systems**: `ftb_state_db.py`, `ftb_web_server.py`, Svelte Web UI  
**Documentation**: See also `PROMOTION_RELEGATION_SYSTEM.md`, `SEASON_ROLLOVER_AND_PAYOUTS.md`
