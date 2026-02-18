# Stuck Race Detection and Auto-Reset Fix

## Problem
Game was completely frozen with these symptoms:
- Ticks appeared to advance but stayed at tick=1
- Budget never changed
- Races never happened (no qualifying, no race)
- Console showed: `[FTB CONTROLLER] ⏸️ TICK BLOCKED - race day active (phase=race_running)`

## Root Cause
The `race_day_state` was stuck in `RACE_RUNNING` phase, but the race never actually started:
- No qualifying ever showed
- No race data was loaded
- No PBP (play-by-play) widget was active
- The race state blocked ALL tick advancement forever

This created a deadlock:
1. Race state = RACE_RUNNING
2. Controller blocks ticks while race is "running"
3. But race never actually runs (no data, no UI)
4. Simulation frozen permanently

## The Fix
Added **automatic stuck race detection** in the controller's tick check logic.

**Location**: `plugins/ftb_game.py`, lines ~30765-30810

### Detection Logic
When race_day_state phase is `RACE_RUNNING`, the system now checks:
1. Does `_live_race_result` exist with actual race data?
2. Is `PBP_ACTIVE` flag set (meaning PBP widget is running)?

If BOTH are false, the race is **stuck** (phase says running, but nothing is actually happening).

### Auto-Reset Actions
When a stuck race is detected:

```python
# Reset race day state to IDLE
self.state.race_day_state.phase = RaceDayPhase.IDLE
self.state.race_day_state.race_tick = None
self.state.race_day_state.league_id = None
self.state.race_day_state.track_id = None

# Clear race flags
self.state.race_day_active = False
self.state.race_day_started_ts = None

# Clean up stale race data
if hasattr(self.state, '_live_race_result'):
    self.state._live_race_result = None
if hasattr(self.state, '_live_pbp_mode'):
    self.state._live_pbp_mode = False
```

### Console Output
When a stuck race is detected, you'll see:

```
[FTB CONTROLLER] ⚠️  STUCK RACE DETECTED!
[FTB CONTROLLER] ⚠️  Race phase=RACE_RUNNING but no race data exists
[FTB CONTROLLER] ⚠️  Auto-resetting race_day_state to IDLE to unblock simulation
[FTB CONTROLLER] ✅ Race state reset complete - simulation unblocked
```

After reset, the simulation can continue normally.

## What This Fixes
1. ✅ **Unfreezes stuck simulations** - ticks can advance again
2. ✅ **Budget updates** - with ticks working, income/expenses flow
3. ✅ **Races can happen** - race system reset to clean state
4. ✅ **No manual intervention** - detects and fixes automatically
5. ✅ **Non-destructive** - only resets if truly stuck

## What This Doesn't Fix (Yet)
- ❌ **Why races get stuck** - underlying cause unknown
  - Possibly: race starts but PBP widget fails to initialize
  - Possibly: race data fails to load
  - Possibly: save/load corruption of race state

- ❌ **Qualifying/race never showing** - separate issue
  - Need to investigate why pre-race prompt doesn't appear
  - Need to check if schedule is correct
  - Need to verify race trigger logic

## Testing
1. **Immediate test**: Restart your game with the stuck save
   - Should see "STUCK RACE DETECTED" message
   - Should auto-reset to IDLE
   - Should be able to advance ticks

2. **Future monitoring**: Watch for any new stuck races
   - If they still occur, we know the auto-reset works
   - But we need to fix the underlying race start logic

## Next Steps to Fully Fix Racing

### Issue #1: Why do races get stuck?
Need to investigate:
- Race start sequence in `ftb_race_day`
- PBP widget initialization
- Race data loading
- Save/load of race state

### Issue #2: Why doesn't qualifying show?
Need to check:
- Pre-race prompt logic
- Schedule timing (is race scheduled at right tick?)
- Completed race tracking
- Prompted race tracking

### Issue #3: Budget still not updating?
After this fix:
- Ticks should work → budget should update
- If budget still frozen, need separate fix
- May need to add `state.mark_dirty('all')` after tick

## Files Modified
- `plugins/ftb_game.py` (lines ~30765-30810): Added stuck race detection

## Estimated Impact
- **Immediate**: Unfreezes your current save ✅
- **Preventive**: Catches future stuck races ✅  
- **Diagnostic**: Logs when races get stuck (helps debug) ✅
- **Root cause**: Not fixed yet (need more investigation) ⏳
