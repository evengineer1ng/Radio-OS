# FTB Data Explorer — Quick Summary

## What Was Built
A new **Data Explorer tab** in the web UI that allows users to query and explore historical game statistics without loading all that data into the main game state (which would slow down the UI).

## Files Created

### 1. Backend Query Plugin
**`/plugins/ftb_data_explorer.py`** (156 lines)
- 7 query functions that read from SQLite database
- Query seasons, races, finances, careers, team outcomes, championships, and table metadata
- All queries support optional filters (team name, season, role, entity) and limit parameters

### 2. Svelte Frontend Component
**`/web/src/tabs/FTBData.svelte`** (482 lines)
- 7 category tabs: Seasons, Races, Finances, Careers, Outcomes, Championships, Database
- Context-aware filter UI (filters adapt based on selected category)
- Lazy loading (data only fetched when Query button clicked)
- CSV export functionality
- Responsive table display with number formatting
- Empty states and error handling

### 3. Documentation
**`/FTB_DATA_EXPLORER.md`** (comprehensive guide)
- Architecture overview
- API documentation
- Usage examples
- Performance considerations
- Troubleshooting guide

## Files Modified

### 1. Web Server API
**`/plugins/ftb_web_server.py`** (added 100 lines)
- Added 7 new POST endpoints: `/api/ftb_data/query_*`
- Each endpoint calls corresponding function from `ftb_data_explorer.py`
- Returns JSON responses with error handling

### 2. Main App Component
**`/web/src/App.svelte`** (added 3 lines)
- Imported `FTBData.svelte` component
- Added Data tab to tabs array (`{ id: 'data', label: '🗄️', name: 'Data' }`)
- Added tab route handler for data tab

## How It Works

### Data Flow
```
User clicks "Query" button
    ↓
Svelte component sends POST to /api/ftb_data/query_*
    ↓
FastAPI endpoint receives request
    ↓
Calls ftb_data_explorer.query_* function
    ↓
Function queries SQLite database directly
    ↓
Returns list of dicts as JSON
    ↓
Svelte component displays data in table
```

### Key Features
1. **Lazy Loading**: Data only loaded on-demand, not kept in memory
2. **Filtering**: Team, season, role, entity filters per category
3. **Export**: CSV download of query results
4. **No Performance Impact**: Separate from main game state stores
5. **Database Overview**: View record counts for all tables

## Usage Example

### Query Recent Races for Your Team
1. Open web UI (http://localhost:8000 or device IP)
2. Click **🗄️ Data** tab at bottom
3. Click **🏁 Races** category tab
4. (Team filter auto-populated with your team)
5. Enter season number (e.g., 3)
6. Set limit (e.g., 50)
7. Click **Query**
8. Results appear in scrollable table
9. Click **📥 Export CSV** to save

### View Driver Career Stats
1. Open Data tab
2. Click **👤 Careers** category
3. Select Role: "Driver"
4. (Optional) Enter driver name in Entity filter
5. Click **Query**
6. See all driver career totals

### Check Database Health
1. Open Data tab
2. Click **🗄️ Database** category
3. Click **Load Table Counts**
4. See record counts for all tables

## API Endpoints Added

All endpoints accept POST with JSON payload:

```json
{
  "db_path": "/path/to/ftb_state.db",
  "team_name": "optional",
  "season": 5,
  "role": "Driver",
  "entity_name": "John Doe",
  "limit": 50
}
```

### Endpoints
- `/api/ftb_data/query_season_summaries` — Season end results
- `/api/ftb_data/query_race_history` — Race results with positions
- `/api/ftb_data/query_financial_history` — Transaction logs
- `/api/ftb_data/query_career_stats` — Driver/engineer career totals
- `/api/ftb_data/query_team_outcomes` — ML training data outcomes
- `/api/ftb_data/query_championship_history` — Championship standings
- `/api/ftb_data/query_all_tables` — Database table metadata

## Next Steps

### To Test
1. **Rebuild Svelte frontend**:
   ```bash
   cd web
   npm run build
   ```

2. **Restart Radio OS** (or just the FTB station):
   ```bash
   python shell.py
   ```

3. **Open web UI** in browser:
   - Desktop: http://localhost:8000
   - Phone: http://<your-ip>:8000

4. **Test the Data tab**:
   - Try each category
   - Apply filters
   - Export CSV
   - Verify data accuracy

### Potential Issues
- **Tab not showing**: Rebuild frontend with `npm run build`
- **Query errors**: Check that database path is set (game must be loaded)
- **Empty results**: Try removing filters, check Database tab for record counts
- **CSV not downloading**: Check browser download settings

## Why This Design?

### Problem
Loading all historical data into the main game state would:
- Increase memory usage significantly
- Slow down reactive store updates
- Impact UI responsiveness
- Make WebSocket messages huge

### Solution
- Data queried **on-demand** from database
- **Not stored** in Svelte stores
- **Separate tab** isolated from main UI
- **Direct database queries** via backend plugin
- **No caching** to avoid stale data

### Benefits
✅ Main UI stays fast  
✅ Access to all historical data  
✅ Flexible filtering and exploration  
✅ Export capabilities  
✅ No impact on existing systems  

## Integration Status

### No Changes Required
- Game simulation loop
- State persistence logic
- WebSocket streaming
- Other UI tabs
- Game state stores

### New Components
- ✅ Backend plugin (`ftb_data_explorer.py`)
- ✅ API endpoints in `ftb_web_server.py`
- ✅ Svelte component (`FTBData.svelte`)
- ✅ Tab registration in `App.svelte`
- ✅ Documentation (`FTB_DATA_EXPLORER.md`)

### Code Quality
- ✅ No syntax errors detected
- ✅ Follows existing patterns
- ✅ Error handling implemented
- ✅ TypeScript types used
- ✅ Responsive design
- ✅ Documented

## Database Tables Available

The queries access these tables in `ftb_state.db`:

| Table Name | Content | Typical Record Count |
|------------|---------|---------------------|
| `season_summary` | Season end results per team | ~60 per season |
| `race_results` | Individual race results | ~1,200 per season |
| `financial_transactions` | All money movements | ~100-500 per season |
| `career_stats` | Cumulative entity stats | ~200 total |
| `team_outcomes` | ML training data | ~50-100 per season |
| `championship_standings` | Periodic standings snapshots | ~300-600 per season |

## Testing Checklist

- [ ] Rebuild Svelte: `cd web && npm run build`
- [ ] Restart Radio OS / FTB station
- [ ] Open web UI in browser
- [ ] Verify Data tab appears with 🗄️ icon
- [ ] Test Seasons query with team filter
- [ ] Test Races query with season filter
- [ ] Test Finances query
- [ ] Test Careers query with role filter
- [ ] Test Championships query
- [ ] Test Database tab (table counts)
- [ ] Test CSV export functionality
- [ ] Test Clear filters button
- [ ] Test empty state (before querying)
- [ ] Test error handling (invalid filters)

## Future Enhancements

Potential additions if needed:
- Column sorting (click headers)
- Column filtering (search per column)
- Pagination for large result sets
- Charts/graphs for trends
- Saved queries / bookmarks
- Compare multiple teams side-by-side
- Advanced date range filters
- PDF report generation
- League tier filtering

---

**Status**: ✅ Implementation Complete  
**Files Changed**: 2 created, 2 modified, 1 documented  
**Lines Added**: ~850 total  
**Ready For Testing**: Yes  
**Breaking Changes**: None  

**See Full Documentation**: `FTB_DATA_EXPLORER.md`
