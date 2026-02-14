# Race Day Timing Fix - February 13, 2026

## Issues Fixed

### 1. **Race Day Prompt Appearing AFTER Races** ✅

**Problem**: The pre-race prompt was appearing one day AFTER the race instead of one day BEFORE.

**Root Cause**: The logic in `should_show_pre_race_prompt()` was checking correctly (tick N checks if tick N+1 has a race), BUT there was a critical issue on game load: the `race_day_state` was persisting from saved games with stale data (old race_tick values from previous sessions).

**Fixes Applied**:

1. **`plugins/ftb_race_day.py` lines 70-108**: Clarified the docstring to make the timing logic crystal clear:
   - At tick N, we check if tick N+1 has a race
   - If yes, show prompt at tick N (day BEFORE race)
   - This prevents tick from advancing until player responds
   - When player responds, tick advances to N+1 where race happens

2. **`plugins/ftb_game.py` lines ~29538**: Added critical reset logic after loading saved games:
   ```python
   # CRITICAL: Reset race_day_state to IDLE after loading to avoid stale race data
   if ftb_race_day and hasattr(self.state, 'race_day_state') and self.state.race_day_state:
       from plugins.ftb_race_day import RaceDayPhase
       self.state.race_day_state.phase = RaceDayPhase.IDLE
       self.state.race_day_state.race_tick = None
       self.state.race_day_state.league_id = None
       self.state.race_day_state.track_id = None
       self.state.race_day_state.player_wants_live_race = False
   ```

**Why This Fixes It**:
- The log showed pre-race prompts triggering for tick 2 even when the game was at tick 99+
- This was stale `race_day_state` data persisting across save/load cycles
- Now when a game is loaded, `race_day_state` is reset to IDLE with cleared race info
- The next time a race approaches, the prompt will trigger at the correct time (day before)

### 2. **CustomTkinter Mouse Wheel Error** ⚠️ 

**Problem**: 
```
AttributeError: 'str' object has no attribute 'master'
Exception in Tkinter callback at ctk_scrollable_frame.py line 280
```

**Root Cause**: This is a known bug in the CustomTkinter library where `event.widget` is sometimes a string instead of a widget object during mouse wheel events.

**Status**: This is a third-party library issue, not our code. The error is non-fatal (doesn't break functionality) and occurs in the CustomTkinter package's internal scrolling code.

**Workaround**: The error can be safely ignored as it doesn't affect game functionality. If it becomes problematic, we could:
- Add try/except wrappers around scrollable widget creation
- Update to a newer version of CustomTkinter if/when they fix it
- Disable mouse wheel events on problematic widgets

## Testing Checklist

To verify the fix works:

1. ✅ Load a saved game
2. ✅ Check that `race_day_state.phase` is IDLE in logs
3. ✅ Advance ticks until one day before a scheduled race
4. ✅ Verify pre-race prompt appears at tick N for a race scheduled at tick N+1
5. ✅ Choose "Yes" to watch live
6. ✅ Verify qualifying runs
7. ✅ Verify tick advances to N+1 where race actually happens
8. ✅ Verify race executes correctly

## Log Markers to Watch

Good behavior:
```
[FTB RACE DAY] 🏁 Pre-race prompt triggered for tick N+1: [league] at [track]
[FTB RACE DAY] ⏸️  PAUSING tick advance - waiting for player response
[FTB RACE DAY] ✅ Player chose LIVE RACE mode
[FTB RACE DAY] 🏁 Qualifying complete: X drivers, Y events
[FTB] RACE_START: Tick N+1 - [league] Round X at [track]
```

Bad behavior (FIXED):
```
[FTB RACE DAY] 🏁 Pre-race prompt triggered for tick 2: [league] at [track]
[FTB] RACE_START: Tick 2 - [league] Round 1 at [track]
```
(This was happening because stale race_day_state had race_tick=2 from an old session)

## Code Locations

- **Pre-race check logic**: `plugins/ftb_race_day.py` lines 70-108
- **Tick simulation**: `plugins/ftb_game.py` lines 8244-8300
- **Save/load handler**: `plugins/ftb_game.py` lines 29525-29550
- **Race execution**: `plugins/ftb_game.py` lines 8550-8700

## Notes

- The PBP (play-by-play) system was never the issue - it works correctly when races execute
- The real issue was stale state data causing prompts to trigger at wrong times
- Always reset transient/session-specific state on game load to avoid these issues
