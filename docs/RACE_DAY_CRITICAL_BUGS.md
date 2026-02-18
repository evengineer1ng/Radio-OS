# Race Day Critical Bugs - Analysis & Fixes

## 🚨 **Bug #1: Old Saves Don't Trigger Races**

### Problem
When loading an old save file, races don't occur when advancing ticks. Instant replay and watch race live buttons do nothing.

### Root Cause
Old save files are missing key fields that the race day system expects:
- `completed_race_ticks` (set)
- `prompted_race_ticks` (set)
- `race_day_state` structure

When these are missing, the race detection logic fails silently or gets into an inconsistent state.

### Specific Issues

1. **Missing `completed_race_ticks` in old saves**
   - Lines 5700-5701 in `ftb_game.py` load these from save data
   - If missing, defaults to empty set
   - BUT: Old saves that had races run via the old system don't have these marked
   - Result: System tries to re-run already completed races or skips races entirely

2. **Race day state not properly initialized**
   - Old saves don't have `race_day_state` field
   - Loading logic may not properly initialize `RaceDayState()` object
   - Result: Race prompt logic thinks race day is active when it's not

3. **Schedule format mismatch**
   - Old saves may have schedule as `[tick1, tick2, tick3]`
   - New code expects `[(tick1, track_id1), (tick2, track_id2)]`
   - Code has compatibility, but may fail edge cases

### Fix Strategy

**Option A: Migration Script (Safest)**
Create `migrate_old_saves.py` that:
1. Detects save version
2. Adds missing fields with correct defaults
3. Infers `completed_race_ticks` from `races_completed_this_season`
4. Initializes proper `race_day_state`

**Option B: Defensive Load Logic (Quick Fix)**
Strengthen `from_dict()` to handle missing fields:
```python
# Ensure race tracking fields exist
if not hasattr(state, 'completed_race_ticks'):
    state.completed_race_ticks = set()
if not hasattr(state, 'prompted_race_ticks'):
    state.prompted_race_ticks = set()

# Initialize race_day_state if missing
if not hasattr(state, 'race_day_state'):
    from plugins.ftb_race_day import RaceDayState, RaceDayPhase
    state.race_day_state = RaceDayState()
    state.race_day_state.phase = RaceDayPhase.IDLE
```

---

## 🚨 **Bug #2: PBP Widget Overwritten By Other Races**

### Problem
After watching your first race in PBP mode, every subsequent race in the world (including AI-only races) overwrites the `CURRENT_RACE` global, making it impossible to ever view your own race again.

### Root Cause
The PBP widget uses a **global variable** `CURRENT_RACE` that is shared across ALL races:

```python
# plugins/ftb_pbp.py line 49
CURRENT_RACE: Optional[Dict[str, Any]] = None
```

Every time ANY race completes (including 20+ AI league races), it calls:
```python
update_race_data(race_result, state)  # Line 65+
```

Which overwrites:
```python
CURRENT_RACE = race_data  # Line 86
```

**Flow:**
1. Player race completes → `CURRENT_RACE` = player race ✅
2. AI league 1 completes → `CURRENT_RACE` = AI race ❌ (overwrites)
3. AI league 2 completes → `CURRENT_RACE` = AI race ❌ (overwrites)
4. ... 18 more AI races overwrite...
5. Player tries to view PBP → sees random AI race ❌

### Fix Strategy

**Solution: Filter to Only Track Player Races**

Modify `update_race_data()` and `start_live_feed()` to ONLY cache player races:

```python
def update_race_data(race_result: Any, state: Any):
    """Only cache player races"""
    global CURRENT_RACE, RACE_HISTORY
    
    if not race_result or not state:
        return
    
    # CRITICAL FIX: Only track player's races
    if not _is_player_race(race_result, state):
        print(f"[FTB PBP] Skipping non-player race: {race_result.league_name}")
        return
    
    print(f"[FTB PBP] ✅ Caching player race: {race_result.league_name} at {race_result.track_name}")
    
    # Package race data
    race_data = {
        'race_id': race_result.race_id,
        'league_name': race_result.league_name,
        'track_name': race_result.track_name,
        # ... rest of data ...
    }
    
    CURRENT_RACE = race_data
    RACE_HISTORY.insert(0, race_data)
    
    if len(RACE_HISTORY) > MAX_HISTORY:
        RACE_HISTORY.pop()

def _is_player_race(race_result: Any, state: Any) -> bool:
    """Check if race is from player's league"""
    if not state or not state.player_team:
        return False
    
    player_league_id = state.player_team.league_id
    if not player_league_id:
        return False
    
    # Check if race's league matches player's league
    for league in state.leagues.values():
        if league.league_id == player_league_id and league.name == race_result.league_name:
            return True
    
    return False
```

---

## 🚨 **Bug #3: Race Day State Persistence Issues**

### Problem
Related to Bug #1 - race day state persists across save/load in inconsistent ways.

### Issues

1. **Stale phase values**
   - Save file has `race_day_state.phase = "RACE_RUNNING"`
   - On load, this isn't reset to IDLE
   - Next tick thinks race is still active
   - Blocks normal tick advancement

2. **Stale race_tick values**
   - Save file has `race_day_state.race_tick = 42`
   - On load, system thinks tick 42 is still upcoming
   - Actually tick 42 already happened
   - Prompts for race that's already done

### Current "Fix" (Incomplete)
Lines 5698-5699 try to reset:
```python
if state.race_day_active:
    state.race_day_active = False
```

But this doesn't reset `race_day_state.phase` or clear other stale fields.

### Proper Fix
```python
# After loading all data
state.race_day_active = False
state.race_day_started_ts = None
state._live_pbp_interval = None

# Reset race day state to clean IDLE
if hasattr(state, 'race_day_state') and state.race_day_state:
    from plugins.ftb_race_day import RaceDayPhase
    state.race_day_state.phase = RaceDayPhase.IDLE
    state.race_day_state.race_tick = None
    state.race_day_state.league_id = None
    state.race_day_state.track_id = None
    state.race_day_state.race_result = None
    # Keep completed_race_ticks and prompted_race_ticks - they're valid
```

---

## Implementation Plan

### Priority 1: Fix PBP Overwrite (Highest Impact)
**File:** `plugins/ftb_pbp.py`
**Lines:** 65-87, 96-118
**Action:**
1. Add `_is_player_race()` helper function
2. Modify `update_race_data()` to filter non-player races
3. Modify `start_live_feed()` to filter non-player races

### Priority 2: Fix Save Loading
**File:** `plugins/ftb_game.py`
**Lines:** 5690-5720
**Action:**
1. Strengthen `from_dict()` to ensure all race tracking fields exist
2. Force reset `race_day_state` to IDLE on load
3. Clear all transient race day fields

### Priority 3: Create Migration Script
**File:** `migrate_old_saves.py` (new)
**Action:**
1. Detect old save format
2. Add missing fields
3. Reconstruct completed_race_ticks from race counter

---

## Testing Checklist

### Old Save Loading
- [ ] Load old save (pre-race-day-system)
- [ ] Advance to race day
- [ ] Verify race prompt appears
- [ ] Choose instant replay
- [ ] Verify race runs and completes
- [ ] Verify results appear in standings

### PBP Widget Persistence
- [ ] Start new game
- [ ] Run first race with PBP mode
- [ ] Verify PBP shows your race
- [ ] Advance 1 full tick (all AI races run)
- [ ] Re-open PBP widget
- [ ] Verify it STILL shows your race (not AI race)
- [ ] Run second player race with PBP
- [ ] Verify PBP now shows second race
- [ ] Verify history shows both races

### Multi-Race Day
- [ ] Run race in PBP mode
- [ ] Immediately advance to next race day
- [ ] Watch second race
- [ ] Verify both races tracked correctly
- [ ] Verify no overwrites from AI races

---

## Quick Test Commands

```bash
# Test old save loading
python3 shell.py
# Load old save
# Advance tick
# Check console for errors

# Test PBP persistence
python3 shell.py  
# New game
# Run first race with PBP
# Print CURRENT_RACE in console
# Advance full tick
# Print CURRENT_RACE again (should be same)
```
