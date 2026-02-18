# Narrator Database Access - Hot vs Cold

## Quick Answer

**The narrator queries the HOT database by default.** This works perfectly for 95% of commentary since:

- ✅ Current state always in hot
- ✅ Last 3 seasons in hot (recent history)
- ✅ Career totals NEVER archived (always hot)
- ✅ Championship history NEVER archived (always hot)

**For special historical commentary**, the narrator can optionally query cold database too.

## Current Behavior (No Changes)

```python
# plugins/meta/ftb_narrator_plugin.py
# These query hot DB only (current behavior)

game_state = ftb_state_db.query_game_state(self.db_path)
player_state = ftb_state_db.query_player_state(self.db_path)
unseen_events = ftb_state_db.query_unseen_events(self.db_path)
teams = ftb_state_db.query_all_teams(self.db_path)
```

**Result:** Fast queries, recent data, no changes needed.

## Optional Enhancement (New)

For commentary types that need deep historical context:

```python
# plugins/meta/ftb_narrator_plugin.py

try:
    from plugins import ftb_db_archival
except ImportError:
    ftb_db_archival = None

def _generate_historical_comparison(self):
    """Generate commentary comparing to distant past."""
    
    # Check if cold DB available
    if ftb_db_archival and ftb_db_archival.has_cold_database(self.db_path):
        # Can query deep history (10+ seasons ago)
        race_results = ftb_db_archival.query_race_results_extended(
            self.db_path,
            team_name=self.player_team,
            limit=200,
            include_cold=True  # Include archived data
        )
        context = "across our entire history"
    else:
        # Query hot DB only (last 3 seasons)
        with ftb_state_db.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM race_results_archive 
                WHERE player_team_name = ?
                ORDER BY season DESC LIMIT 50
            """, (self.player_team,))
            race_results = cursor.fetchall()
        context = "in recent seasons"
    
    prompt = f"Comparing our current performance {context}..."
    return self.call_llm(prompt)
```

## What's Always in Hot DB (Never Archived)

These are ALWAYS available to the narrator, always fast:

```python
# Career totals - NEVER archived
team_career_totals      # All-time wins, championships, podiums
driver_career_stats     # Driver career records
team_prestige           # Prestige scores
driver_legacy           # Legacy scores

# Championship history - NEVER archived
championship_history    # Season-by-season champions (compact)
team_tier_history       # Tier movement over time

# Season summaries - NEVER archived
season_summaries        # One row per season (very compact)

# Current state - NEVER archived
teams                   # Current teams
entities                # Current drivers, engineers
game_state_snapshot     # Current tick, season
league_standings        # Current championship positions
```

## What Might Be in Cold DB

These details get archived after 3 seasons:

```python
# Detailed records - Archived after 3 seasons
race_results_archive    # Race-by-race details (grid, incidents, etc.)
financial_transactions  # Individual income/expense records
decision_history        # Individual decisions made
events_buffer          # Old event notifications
```

## When Narrator Should Use Cold DB

| Commentary Type | Use Cold DB? | Reason |
|----------------|--------------|---------|
| Event commentary | ❌ No | Recent events in hot DB |
| Current season | ❌ No | Current data in hot DB |
| Trend analysis | ❌ No | Last 3 seasons in hot DB |
| Career milestones | ❌ No | Career totals in hot DB |
| Championship review | ❌ No | History in hot DB |
| **Historical comparison** | ✅ Optional | Deep past context |
| **Legacy narrative** | ✅ Optional | Reference distant events |
| **Era analysis** | ✅ Optional | Compare across eras |

## Implementation Examples

### Example 1: Regular Commentary (Hot Only)

```python
# 95% of narrator queries - no changes needed
def _generate_race_recap(self):
    """Recap recent race."""
    events = ftb_state_db.query_unseen_events(self.db_path, limit=100)
    prompt = f"Recent events: {events}"
    return self.call_llm(prompt)
```

### Example 2: Career Reference (Hot Only)

```python
# Career stats are NEVER archived - always fast
def _reference_career_milestone(self, driver_name):
    """Reference driver's career achievements."""
    with ftb_state_db.get_connection(self.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT career_wins, championships_won 
            FROM driver_career_stats 
            WHERE driver_name = ?
        """, (driver_name,))
        stats = cursor.fetchone()
    
    prompt = f"{driver_name} now has {stats['career_wins']} career wins..."
    return self.call_llm(prompt)
```

### Example 3: Historical Comparison (Optional Cold)

```python
# Special case - can optionally use cold DB
def _generate_historical_comparison(self):
    """Compare current to historical performance."""
    
    # Check if deep history available
    if ftb_db_archival and ftb_db_archival.has_cold_database(self.db_path):
        # Query all-time race history
        all_races = ftb_db_archival.query_race_results_extended(
            self.db_path,
            team_name=self.player_team,
            limit=500,
            include_cold=True
        )
        
        if len(all_races) > 100:
            # Have deep history - compare to golden era
            prompt = f"""
            Our performance now vs our golden era {len(all_races)} races ago.
            Recent: {all_races[:10]}
            Peak era: {all_races[-20:]}
            """
        else:
            # Limited history
            prompt = f"Recent performance trend across {len(all_races)} races..."
    else:
        # No cold DB - use recent history only
        with ftb_state_db.get_connection(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM race_results_archive
                WHERE player_team_name = ?
                ORDER BY season DESC LIMIT 50
            """, (self.player_team,))
            recent_races = cursor.fetchall()
        
        prompt = f"Recent performance shows {recent_races}..."
    
    return self.call_llm(prompt)
```

## Helper Functions for Narrator

```python
from plugins import ftb_db_archival

# Check if cold DB exists
has_cold = ftb_db_archival.has_cold_database(db_path)

# Query race results (optional cold)
races = ftb_db_archival.query_race_results_extended(
    db_path,
    season=None,           # Optional filter
    team_name=None,        # Optional filter
    limit=50,              # Max results
    include_cold=False     # Set True for deep history
)

# Query financial history (optional cold)
finances = ftb_db_archival.query_financial_history_extended(
    db_path,
    season=None,
    category=None,
    limit=100,
    include_cold=False
)

# Query decision history (optional cold)
decisions = ftb_db_archival.query_decision_history_extended(
    db_path,
    season=None,
    category=None,
    limit=50,
    include_cold=False
)
```

## Decision Tree for Narrator

```
Commentary needed?
├─ Recent event/trend? → Query hot DB (ftb_state_db)
├─ Career milestone? → Query hot DB (career totals never archived)
├─ Championship history? → Query hot DB (never archived)
└─ Deep historical comparison?
   ├─ Cold DB available? → Query with include_cold=True
   └─ No cold DB? → Query hot DB only (last 3 seasons)
```

## Summary

**Default:** Narrator queries **hot DB only** via `ftb_state_db` module
- ✅ Fast
- ✅ Recent data (last 3 seasons)
- ✅ Career totals always available
- ✅ No code changes needed

**Optional:** For deep historical commentary, narrator can query **hot + cold**
- ✅ Access to 10+ seasons ago
- ✅ Deep comparisons possible
- ✅ Graceful fallback if cold DB unavailable
- ✅ Only for special commentary types

**In practice:**
- 95% of queries: Hot DB only
- 5% of queries: Optional cold DB for historical depth
- 100% of career stats: Always hot, never archived

**No breaking changes:** Narrator works exactly as before. Cold DB access is purely additive for enhanced historical context when available.
