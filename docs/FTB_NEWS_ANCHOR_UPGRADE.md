# Formula Z News Anchor Upgrade

## Problem Solved
The Formula Z news anchor was hallucinating driver and team names because it lacked access to real data from the game database.

## Solution Implemented

### 1. **Data Enrichment** (`_generate_news_broadcast()`)
The news anchor now queries comprehensive Formula Z data:

#### Real Data Now Available:
- **Formula Z Team Standings** - Top 8 teams with points and budgets
- **Complete Driver Rosters** - All drivers for each team with names and ratings
- **Recent Race Results** - Last 3 races with:
  - Track names and round numbers
  - Top 5 finishers per race (driver names, teams, positions)
  - Fastest lap holders
- **Podium Spotlight** - Recent podium finishers across all races
- **Recent Events** - Team activity, incidents, and news

#### Data Sources Used:
```python
ftb_state_db.query_league_standings()   # Championship standings
ftb_state_db.query_all_teams()          # Team details & budgets
ftb_state_db.query_entities_by_team()   # Driver rosters
ftb_state_db.query_race_results()       # Race history with driver positions
ftb_state_db.query_tier_events()        # Recent Formula Z activity
```

### 2. **Validation System** (`_validate_news_broadcast()`)
Added post-generation validation to catch any remaining hallucinations:

#### Checks Performed:
- **Entity Name Validation**: Compares mentioned names against database entity allowlist
- **Proper Noun Detection**: Extracts capitalized words that look like names
- **Placeholder Detection**: Flags generic terms like "driver X" or initials
- **Fuzzy Tolerance**: Allows 1 minor violation for legitimate but unusual names

#### Validation Flow:
```
Generate News → Validate Names → Enqueue if Valid → Reject if Hallucinated
```

Rejected broadcasts are logged but don't spam (broadcast timer still advances).

### 3. **Enhanced LLM Prompt**
The prompt now:
- Explicitly provides REAL driver and team names
- Shows recent race results with actual positions
- Lists podium performers by name
- Emphasizes: "ALL names above are REAL - do NOT make up names"
- Reduced temperature (0.75 → more factual)

### 4. **Voice System** (Already Working)
News broadcasts already use dedicated news anchor voice with newsflash sound effect:
- Voice: `cfg.voices.formula_z_news` or `cfg.voices.news_anchor`
- SFX: `audio/ui/newsflash.wav` (if exists)

## Example Data Flow

**Before Upgrade:**
```
LLM Prompt: "Championship standings: [5 teams with points]"
News Anchor: "Breaking: Driver Martinez takes pole at Monaco..."
             ↑ Made up name     ↑ Made up race
```

**After Upgrade:**
```
LLM Prompt: """
Championship Standings:
1. Phoenix Racing: 156 pts (Drivers: Elena Rodriguez, Marcus Chen) [$780,000]
2. Velocity Team: 142 pts (Drivers: Sarah Kim, James Wilson) [$650,000]

Recent Race Results:
Round 5 (Silverstone Circuit):
  P1: Elena Rodriguez (Phoenix Racing)
  P2: Marcus Chen (Phoenix Racing)
  P3: Sarah Kim (Velocity Team)
  Fastest Lap: Elena Rodriguez
"""

News Anchor: "Breaking from Formula Z: Phoenix Racing extends their lead with 
              a 1-2 finish at Silverstone! Elena Rodriguez dominates with both 
              the win and fastest lap..."
              ↑ All real names and real results
```

## Configuration Requirements

### Manifest YAML:
```yaml
voices:
  narrator: "voices/ftb_narrator.onnx"
  formula_z_news: "voices/news_anchor.onnx"  # Optional separate voice
  news_anchor: "voices/news_anchor.onnx"     # Fallback
```

### Database Schema:
The upgrade uses existing database tables:
- `league_standings` - Championship data
- `entities` - Drivers and staff
- `teams` - Team details
- `race_results_archive` - Race history

## Testing Checklist

1. ✅ **Syntax Valid**: Code compiles without errors
2. ⏳ **Driver Names**: Verify news broadcasts mention real drivers
3. ⏳ **Race Results**: Check broadcasts reference actual race outcomes
4. ⏳ **Validation**: Confirm hallucinated names are rejected (check logs)
5. ⏳ **Voice**: Ensure news anchor voice is used (not narrator voice)
6. ⏳ **SFX**: Check for newsflash sound effect before broadcast

## Monitoring

### Success Indicators:
- Log message: `"Formula Z broadcast generated with N drivers across M teams, X recent races"`
- No validation rejections in logs
- Broadcasts reference specific driver names from database

### Failure Indicators:
- Log message: `"News broadcast rejected (hallucinations detected): [violations]"`
- Generic placeholder names ("driver X", "team Y")
- Made-up driver names not in database

## Future Improvements
- Add driver championship standings (individual points)
- Include qualifying results and grid positions
- Add driver statistics (career wins, podiums, DNFs)
- Track driver rivalries and team mate battles
- Include technical regulations and car performance data

## Files Modified
- `plugins/meta/ftb_narrator_plugin.py`
  - `_generate_news_broadcast()` - Data enrichment
  - `_validate_news_broadcast()` - Validation system
  - `_run_loop()` - Validation integration
  - Imports - Added `re`, `sqlite3`
