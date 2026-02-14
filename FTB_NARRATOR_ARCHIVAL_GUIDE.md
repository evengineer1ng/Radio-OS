# Narrator Hot/Cold Database Usage Examples

## Overview

The narrator queries the hot database by default (fast, recent data). For special commentary types that need deep historical context, the narrator can optionally query the cold database too.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    FTB NARRATOR                         │
│                                                         │
│  Most queries → ftb_state_db (HOT DB only)             │
│  Historical   → ftb_db_archival (HOT + COLD optional)  │
└─────────────────────────────────────────────────────────┘
                            ↓
        ┌───────────────────┴───────────────────┐
        ↓                                       ↓
  ┌────────────┐                        ┌──────────────┐
  │  HOT DB    │                        │   COLD DB    │
  │ (150-250MB)│                        │  (600+ MB)   │
  │            │                        │              │
  │ • Current  │                        │ • Old races  │
  │ • Last 3   │                        │ • Old trans. │
  │   seasons  │                        │ • Old events │
  │ • Careers  │                        │              │
  └────────────┘                        └──────────────┘
     (Always)                           (When needed)
```

## Default Behavior (Current)

The narrator currently queries hot DB only through `ftb_state_db`:

```python
# plugins/meta/ftb_narrator_plugin.py

# Current queries (hot DB only - no changes needed)
game_state = ftb_state_db.query_game_state(self.db_path)
player_state = ftb_state_db.query_player_state(self.db_path)
unseen_events = ftb_state_db.query_unseen_events(self.db_path)
```

**This works perfectly for 95% of narrator commentary:**
- Recent events ✓
- Current season ✓
- Last 3 seasons ✓
- Career totals ✓ (never archived)
- Championship history ✓ (never archived)

## Optional Cold DB Access (New)

For commentary types that need **deep historical context**, the narrator can now optionally query cold database:

### Example 1: Historical Comparison

```python
# plugins/meta/ftb_narrator_plugin.py

def _generate_historical_comparison_segment(self):
    """Generate commentary comparing current performance to past eras."""
    
    # Import archival helper
    try:
        from plugins import ftb_db_archival
    except ImportError:
        # Fallback to hot DB only
        return self._generate_fallback_comparison()
    
    # Check if cold DB available
    has_cold = ftb_db_archival.has_cold_database(self.db_path)
    
    # Query race results with optional cold access
    race_results = ftb_db_archival.query_race_results_extended(
        self.db_path,
        team_name=self.context.player_team,
        limit=200,  # More results since we might go deep
        include_cold=has_cold  # Include cold if available
    )
    
    # Now can reference races from 10+ seasons ago if cold DB exists
    if len(race_results) > 50:
        prompt = f"""
        Our team has a long history. Looking back across {len(race_results)} races,
        how does our current performance compare to our golden era?
        
        Recent results: {race_results[:10]}
        Historical peak: {race_results[-10:]}
        """
    else:
        # Limited history (hot DB only)
        prompt = f"Analyzing our recent {len(race_results)} race history..."
    
    return self.call_llm(prompt)
```

### Example 2: Career Turning Point

```python
def _generate_career_turning_point_segment(self, driver_name: str):
    """Reference a driver's career history for narrative context."""
    
    try:
        from plugins import ftb_db_archival
    except ImportError:
        # Career totals are always in hot DB anyway
        return self._generate_from_career_totals(driver_name)
    
    # Career totals always in hot DB (never archived)
    with ftb_state_db.get_connection(self.db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM driver_career_stats WHERE driver_name = ?
        """, (driver_name,))
        career = cursor.fetchone()
    
    # For detailed stint history, might need cold DB
    has_cold = ftb_db_archival.has_cold_database(self.db_path)
    
    # Query driver's team stints (always in hot DB - never archived)
    cursor.execute("""
        SELECT * FROM driver_team_stints WHERE driver_name = ?
        ORDER BY start_season DESC
    """, (driver_name,))
    stints = cursor.fetchall()
    
    # Could also query specific races from their history
    if has_cold:
        old_races = ftb_db_archival.query_race_results_extended(
            self.db_path,
            season=career['debut_season'],  # Their first season
            include_cold=True
        )
    
    prompt = f"""
    {driver_name} has come a long way. Career wins: {career['career_wins']}.
    Their journey began in season {career['debut_season']}...
    """
    
    return self.call_llm(prompt)
```

### Example 3: Financial Trend Analysis

```python
def _analyze_financial_trends(self):
    """Analyze spending patterns over team's history."""
    
    try:
        from plugins import ftb_db_archival
    except ImportError:
        # Use hot DB only
        return self._analyze_recent_finances()
    
    has_cold = ftb_db_archival.has_cold_database(self.db_path)
    
    # Query financial history
    transactions = ftb_db_archival.query_financial_history_extended(
        self.db_path,
        category='development',
        limit=500,
        include_cold=has_cold
    )
    
    if len(transactions) > 100:
        # Have deep financial history
        prompt = f"""
        Analyzing our development spending across {len(transactions)} transactions.
        Early years: cautious. Recent years: aggressive investment.
        """
    else:
        # Recent history only
        prompt = f"Recent development spending shows..."
    
    return self.call_llm(prompt)
```

## Best Practices for Narrator

### ✅ DO Use Hot DB Only For:

- **Event commentary** - Recent crashes, overtakes, retirements
- **Current season analysis** - Championship positions, points
- **Recent trends** - Last 3 seasons of data
- **Career totals** - Win counts, championships (never archived)
- **Active state** - Current team roster, contracts, standings

```python
# These always use hot DB (fast, no changes needed)
events = ftb_state_db.query_unseen_events(self.db_path)
player = ftb_state_db.query_player_state(self.db_path)
teams = ftb_state_db.query_all_teams(self.db_path)
```

### ✅ DO Use Cold DB (Optional) For:

- **Historical comparisons** - "Best performance since Season 12"
- **Legacy narratives** - "First win was 20 seasons ago"
- **Era analysis** - "During the turbocharged era..."
- **Long-term patterns** - "Spending habits over entire history"

```python
# These can optionally use cold DB
from plugins import ftb_db_archival

# Check availability first
if ftb_db_archival.has_cold_database(self.db_path):
    results = ftb_db_archival.query_race_results_extended(
        self.db_path,
        include_cold=True  # Deep history
    )
```

### ❌ DON'T Need Cold DB For:

- **Career statistics** - Always in hot DB (team_career_totals, driver_career_stats)
- **Championship history** - Always in hot DB (championship_history)
- **Prestige scores** - Always in hot DB (team_prestige, driver_legacy)
- **Season summaries** - Always in hot DB (one row per season, compact)

```python
# These are NEVER archived, always fast
with ftb_state_db.get_connection(self.db_path) as conn:
    cursor = conn.cursor()
    
    # Always in hot DB
    cursor.execute("SELECT * FROM team_career_totals WHERE team_name = ?", (team,))
    cursor.execute("SELECT * FROM championship_history ORDER BY season DESC")
    cursor.execute("SELECT * FROM season_summaries WHERE season >= ?", (season - 10,))
```

## Implementation Pattern

```python
# plugins/meta/ftb_narrator_plugin.py

class FTBNarrator:
    def __init__(self, ...):
        # Check if archival system available
        try:
            from plugins import ftb_db_archival
            self.has_archival = True
        except ImportError:
            self.has_archival = False
    
    def _can_use_cold_db(self) -> bool:
        """Check if cold database queries are available."""
        if not self.has_archival:
            return False
        
        from plugins import ftb_db_archival
        return ftb_db_archival.has_cold_database(self.db_path)
    
    def _choose_segment_type(self, observations):
        """Choose commentary type based on available data."""
        
        # For deep historical types, check cold DB availability
        if observations.has_historical_significance:
            if self._can_use_cold_db():
                # Can do deep historical comparison
                return CommentaryType.HISTORICAL_COMPARISON
            else:
                # Fall back to recent comparison
                return CommentaryType.TREND_ANALYSIS
```

## Migration Path

**Phase 1: Current (No Changes Needed)**
- Narrator uses hot DB only
- Works perfectly for current/recent commentary
- No code changes required

**Phase 2: Optional Enhancement**
- Add cold DB queries for specific commentary types
- Only when deep history needed
- Graceful fallback if cold DB not available

**Phase 3: Intelligent Selection**
- Narrator checks cold DB availability
- Chooses commentary type based on data depth
- More sophisticated historical narratives when possible

## Summary

**The narrator queries HOT database by default** (current behavior, no changes needed).

**For special commentary requiring deep history** (HISTORICAL_COMPARISON, LEGACY_SEED), the narrator can optionally query cold database using:

```python
from plugins import ftb_db_archival

# Check availability
if ftb_db_archival.has_cold_database(db_path):
    # Query with cold DB included
    results = ftb_db_archival.query_race_results_extended(
        db_path,
        include_cold=True
    )
```

**Key points:**
- 🔥 Hot DB: 95% of queries (fast, recent data)
- ❄️ Cold DB: 5% of queries (optional, deep history)
- 📊 Career stats: Always hot (never archived)
- 🎯 Default behavior: No changes needed
- 🚀 Enhancement: Optional deeper context
